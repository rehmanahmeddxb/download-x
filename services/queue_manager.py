"""Download engine: dispatches queued tasks, runs yt-dlp downloads in
background threads, and supports pause / resume / cancel / retry /
re-priority -- all driven from the Download table in SQLite.
"""
import os
import threading
import time

import yt_dlp

from extensions import db
from models.download import Download
from services.settings_service import get_settings
from services.history_service import add_history_entry
from utils.logger import get_logger
from utils.validators import sanitize_filename

PLAYER_CLIENTS = {"youtube": {"player_client": ["android", "ios", "web"]}}


class PauseRequested(Exception):
    pass


class CancelRequested(Exception):
    pass


class QueueManager:
    def __init__(self):
        self.app = None
        self.lock = threading.Lock()
        self.active_count = 0
        self._last_progress_write = {}   # task_id -> last write timestamp (throttling)
        self._dispatcher_started = False

    # ------------------------------------------------------------ startup
    def start(self, app):
        self.app = app
        if self._dispatcher_started:
            return
        self._dispatcher_started = True
        t = threading.Thread(target=self._dispatcher_loop, daemon=True)
        t.start()

    def recover_incomplete_tasks(self):
        """On app restart, any task stuck 'downloading' had its thread die
        with the old process -- put it back in the queue. yt-dlp will
        resume from the .part file thanks to continuedl."""
        stuck = Download.query.filter_by(status="downloading").all()
        for t in stuck:
            t.status = "queued"
            t.pause_flag = False
        db.session.commit()

    # ------------------------------------------------------------ dispatcher
    def _dispatcher_loop(self):
        while True:
            try:
                with self.app.app_context():
                    settings = get_settings()
                    max_concurrent = max(1, settings.max_concurrent)
                    with self.lock:
                        free_slots = max_concurrent - self.active_count
                    if free_slots > 0:
                        tasks = (
                            Download.query.filter_by(status="queued")
                            .order_by(Download.priority.asc(), Download.created_time.asc())
                            .limit(free_slots)
                            .all()
                        )
                        for task in tasks:
                            task.status = "downloading"
                            db.session.commit()
                            with self.lock:
                                self.active_count += 1
                            threading.Thread(
                                target=self._run_download, args=(task.id,), daemon=True
                            ).start()
            except Exception:
                get_logger().exception("Dispatcher loop error")
            time.sleep(1.0)

    # ------------------------------------------------------------ task actions
    def add_task(self, url, format_id="best", quality_label="Best",
                 title="Untitled", thumbnail="", uploader="", session_id=""):
        max_priority = db.session.query(db.func.max(Download.priority)).scalar() or 0
        task = Download(
            url=url, format_id=format_id, quality_label=quality_label,
            title=title, thumbnail=thumbnail, uploader=uploader,
            status="queued", priority=max_priority + 1, session_id=session_id,
        )
        db.session.add(task)
        db.session.commit()
        return task

    def pause(self, task_id):
        task = Download.query.get(task_id)
        if not task:
            return False
        if task.status == "downloading":
            task.pause_flag = True
        elif task.status == "queued":
            task.status = "paused"
        db.session.commit()
        return True

    def resume(self, task_id):
        task = Download.query.get(task_id)
        if not task or task.status != "paused":
            return False
        task.status = "queued"
        task.pause_flag = False
        db.session.commit()
        return True

    def cancel(self, task_id):
        task = Download.query.get(task_id)
        if not task:
            return False
        if task.status == "downloading":
            task.cancel_flag = True
        else:
            task.status = "cancelled"
        db.session.commit()
        return True

    def retry(self, task_id):
        task = Download.query.get(task_id)
        if not task or task.status not in ("failed", "cancelled"):
            return False
        task.status = "queued"
        task.error_message = ""
        task.pause_flag = False
        task.cancel_flag = False
        db.session.commit()
        return True

    def remove(self, task_id):
        task = Download.query.get(task_id)
        if not task or task.status == "downloading":
            return False
        db.session.delete(task)
        db.session.commit()
        return True

    def reprioritize(self, task_id, direction):
        task = Download.query.get(task_id)
        if not task:
            return False
        neighbor_query = Download.query.filter_by(status="queued")
        if direction == "up":
            neighbor = (
                neighbor_query.filter(Download.priority < task.priority)
                .order_by(Download.priority.desc()).first()
            )
        else:
            neighbor = (
                neighbor_query.filter(Download.priority > task.priority)
                .order_by(Download.priority.asc()).first()
            )
        if neighbor:
            task.priority, neighbor.priority = neighbor.priority, task.priority
            db.session.commit()
        return True

    # ------------------------------------------------------------ the actual download
    def _build_opts(self, task, settings):
        out_tmpl = os.path.join(settings.download_folder, settings.filename_template)
        opts = {
            "format": task.format_id or "bestvideo+bestaudio/best",
            "outtmpl": out_tmpl,
            "noplaylist": True,
            "concurrent_fragment_downloads": max(1, settings.concurrent_fragments),
            "quiet": True,
            "no_warnings": True,
            "continuedl": True,
            "ignoreerrors": False,
            "extractor_args": PLAYER_CLIENTS,
            "progress_hooks": [lambda d: self._progress_hook(d, task.id)],
        }
        if settings.speed_limit_kbps and settings.speed_limit_kbps > 0:
            opts["ratelimit"] = settings.speed_limit_kbps * 1024
        if settings.proxy:
            opts["proxy"] = settings.proxy
        if settings.cookies_path and os.path.isfile(settings.cookies_path):
            opts["cookiefile"] = settings.cookies_path
        if settings.ffmpeg_path:
            opts["ffmpeg_location"] = settings.ffmpeg_path

        postprocessors = []
        if task.format_id == "bestaudio/best" or task.quality_label == "Audio Only (MP3)":
            postprocessors.append({
                "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192",
            })
        else:
            opts["merge_output_format"] = "mp4"
        if settings.embed_thumbnail:
            postprocessors.append({"key": "EmbedThumbnail"})
            opts["writethumbnail"] = True
        if settings.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata"})
        if settings.embed_subtitles:
            opts["writesubtitles"] = True
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})
        if settings.sponsorblock:
            postprocessors.append({
                "key": "SponsorBlock", "categories": ["sponsor"], "api": "https://sponsor.ajay.app",
            })
            postprocessors.append({"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]})
        if postprocessors:
            opts["postprocessors"] = postprocessors
        return opts

    def _progress_hook(self, d, task_id):
        with self.app.app_context():
            task = Download.query.get(task_id)
            if not task:
                return
            if task.cancel_flag:
                raise CancelRequested()
            if task.pause_flag:
                raise PauseRequested()

            # Throttle DB writes to ~2/sec -- hooks fire many times/sec.
            now = time.time()
            last = self._last_progress_write.get(task_id, 0)
            if d.get("status") == "downloading" and now - last < 0.4:
                return
            self._last_progress_write[task_id] = now

            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                task.total_bytes = total
                task.downloaded_bytes = downloaded
                task.progress = (downloaded / total * 100) if total else task.progress
                task.speed = d.get("speed") or 0.0
                task.eta_seconds = d.get("eta") or 0
                db.session.commit()
            elif d.get("status") == "finished":
                task.progress = 100.0
                db.session.commit()

    def _run_download(self, task_id):
        try:
            with self.app.app_context():
                task = Download.query.get(task_id)
                if not task:
                    return
                settings = get_settings()
                os.makedirs(settings.download_folder, exist_ok=True)
                opts = self._build_opts(task, settings)
                url = task.url

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                out_file = ydl.prepare_filename(info)

            with self.app.app_context():
                task = Download.query.get(task_id)
                task.status = "completed"
                task.progress = 100.0
                task.output_file = out_file
                task.finished_time = time.time()
                db.session.commit()

                add_history_entry(
                    title=task.title, thumbnail=task.thumbnail, uploader=task.uploader,
                    duration_seconds=0, format_id=task.format_id,
                    quality_label=task.quality_label, size_bytes=task.total_bytes,
                    output_path=out_file, status="completed", session_id=task.session_id,
                )
                get_logger().info(f"Completed: {task.title}")

        except PauseRequested:
            with self.app.app_context():
                task = Download.query.get(task_id)
                if task:
                    task.status = "paused"
                    task.pause_flag = False
                    db.session.commit()

        except CancelRequested:
            with self.app.app_context():
                task = Download.query.get(task_id)
                if task:
                    task.status = "cancelled"
                    task.cancel_flag = False
                    db.session.commit()

        except Exception as ex:
            with self.app.app_context():
                task = Download.query.get(task_id)
                if not task:
                    return
                settings = get_settings()
                task.retry_count += 1
                task.error_message = str(ex)
                if task.retry_count <= settings.max_retries:
                    task.status = "queued"  # automatic retry
                else:
                    task.status = "failed"
                db.session.commit()
                get_logger().warning(f"Download failed ({task.retry_count}x): {task.title} -> {ex}")

        finally:
            with self.lock:
                self.active_count = max(0, self.active_count - 1)


queue_manager = QueueManager()
