"""JSON API + file-serving routes for YT Downloader X Pro.

Wires the existing services (queue manager, yt-dlp metadata helpers,
settings, history) to the endpoints the bundled WebView UI calls:

  * GET  /api/health, /api/stats
  * GET  /api/history[?search=][&scope=session], /api/history/export.csv
  * DELETE /api/history/<id>, POST /api/history/<id>/redownload
  * POST /api/fetch, POST /api/fetch_formats
  * POST /api/queue/add, GET /api/tasks, POST /api/tasks/<id>/<action>
  * GET  /api/tasks/<id>/file
  * GET  /api/direct/download?url=&format_id=&title=
  * GET/POST /api/settings
"""
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from extensions import db
from models.download import Download
from models.history import HistoryEntry
from services.downloader import fetch_formats, fetch_overview, resolve_direct
from services.history_service import (
    delete_history_entry,
    export_history_csv,
    list_history,
)
from services.queue_manager import queue_manager
from services.settings_service import get_settings, update_settings
from utils.helpers import get_disk_usage
from utils.logger import get_logger
from utils.validators import is_valid_youtube_url, sanitize_filename

api_bp = Blueprint("api", __name__)
log = get_logger()


@api_bp.route("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------ stats
@api_bp.route("/stats")
def stats():
    completed = Download.query.filter_by(status="completed").count()
    failed = Download.query.filter_by(status="failed").count()
    finished = completed + failed
    downloaded_bytes = (
        db.session.query(
            db.func.coalesce(db.func.sum(Download.downloaded_bytes), 0)
        ).scalar()
        or 0
    )

    history = HistoryEntry.query.all()
    top_uploader = Counter(h.uploader for h in history if h.uploader).most_common(1)
    top_format = Counter(
        h.quality_label for h in history if h.quality_label
    ).most_common(1)

    labels, counts = [], []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).date()
        labels.append(day.strftime("%a"))
        lo = datetime(day.year, day.month, day.day).timestamp()
        hi = lo + 86400
        counts.append(
            sum(1 for h in history if lo <= (h.date_completed or 0) < hi)
        )

    try:
        disk_used, _disk_total, disk_free = get_disk_usage(
            get_settings().download_folder
        )
    except Exception:
        disk_used, disk_free = 0, 0

    return jsonify(
        {
            "total_downloads": Download.query.count(),
            "completed_downloads": completed,
            "active_downloads": Download.query.filter_by(
                status="downloading"
            ).count(),
            "queued_downloads": Download.query.filter_by(status="queued").count(),
            "downloaded_session_bytes": downloaded_bytes,
            "failed_downloads": failed,
            "total_gb_downloaded": f"{downloaded_bytes / 1024 ** 3:.1f} GB",
            "success_rate": round(completed / finished * 100, 1)
            if finished
            else 100.0,
            "top_uploader": top_uploader[0][0] if top_uploader else "-",
            "top_format": top_format[0][0] if top_format else "-",
            "chart_days_labels": labels,
            "chart_days_counts": counts,
            "disk_used_bytes": disk_used,
            "disk_free_bytes": disk_free,
        }
    )


# ---------------------------------------------------------------- history
@api_bp.route("/history")
def history_list():
    scope = request.args.get("scope", "")
    search = request.args.get("search", "")
    entries = list_history(search=search)
    if scope == "session":
        entries = entries[:10]  # recent activity feed on the dashboard
    return jsonify([e.to_dict() for e in entries])


@api_bp.route("/history/export.csv")
def history_export():
    return Response(
        export_history_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=history.csv"},
    )


@api_bp.route("/history/<int:entry_id>", methods=["DELETE"])
def history_delete(entry_id):
    if not delete_history_entry(entry_id):
        return jsonify({"error": "History entry not found"}), 404
    return jsonify({"ok": True})


@api_bp.route("/history/<int:entry_id>/redownload", methods=["POST"])
def history_redownload(entry_id):
    entry = HistoryEntry.query.get(entry_id)
    if not entry:
        return jsonify({"error": "History entry not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please enter a valid YouTube URL"}), 400
    queue_manager.add_task(
        url=url,
        format_id=entry.format_id or "best",
        quality_label=entry.quality_label or "Best",
        title=entry.title,
        thumbnail=entry.thumbnail,
        uploader=entry.uploader,
    )
    return jsonify({"ok": True})


# --------------------------------------------------------------- metadata
@api_bp.route("/fetch", methods=["POST"])
def fetch():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please paste a valid YouTube link"}), 400
    try:
        return jsonify(fetch_overview(url))
    except Exception as ex:
        log.warning("fetch failed for %s: %s", url, ex)
        return jsonify({"error": str(ex)}), 502


@api_bp.route("/fetch_formats", methods=["POST"])
def fetch_formats_route():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please paste a valid YouTube link"}), 400
    try:
        return jsonify(fetch_formats(url))
    except Exception as ex:
        log.warning("fetch_formats failed for %s: %s", url, ex)
        return jsonify({"error": str(ex)}), 502


# ------------------------------------------------------------------ queue
@api_bp.route("/queue/add", methods=["POST"])
def queue_add():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    count = 0
    for item in items:
        url = ((item or {}).get("url") or "").strip()
        if not is_valid_youtube_url(url):
            continue
        queue_manager.add_task(
            url=url,
            format_id=item.get("format_id") or "best",
            quality_label=item.get("quality_label") or "Best",
            title=item.get("title") or "Untitled",
            thumbnail=item.get("thumbnail") or "",
            uploader=item.get("uploader") or "",
        )
        count += 1
    if not count:
        return jsonify({"error": "No valid items to add"}), 400
    return jsonify({"count": count})


@api_bp.route("/tasks")
def tasks():
    rows = (
        Download.query.order_by(
            Download.priority.asc(), Download.created_time.asc()
        ).all()
    )
    return jsonify([t.to_dict() for t in rows])


@api_bp.route("/tasks/<task_id>/<action>", methods=["POST"])
def task_action(task_id, action):
    if action in ("priority_up", "priority_down"):
        ok = queue_manager.reprioritize(
            task_id, "up" if action == "priority_up" else "down"
        )
    else:
        handler = {
            "pause": queue_manager.pause,
            "resume": queue_manager.resume,
            "cancel": queue_manager.cancel,
            "retry": queue_manager.retry,
            "remove": queue_manager.remove,
        }.get(action)
        if handler is None:
            return jsonify({"error": f"Unknown action: {action}"}), 400
        ok = handler(task_id)
    if not ok:
        return jsonify({"error": "Task not found or action not allowed"}), 404
    return jsonify({"ok": True})


@api_bp.route("/tasks/<task_id>/file")
def task_file(task_id):
    task = Download.query.get(task_id)
    if not task or task.status != "completed" or not task.output_file:
        return jsonify({"error": "File not ready"}), 404
    # yt-dlp sometimes merges to a different container than the filename it
    # predicted, so fall back to an on-disk sibling if the recorded path moved.
    path = task.output_file
    if not os.path.isfile(path):
        base, _ = os.path.splitext(path)
        for ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a"):
            if os.path.isfile(base + ext):
                path = base + ext
                break
    if not os.path.isfile(path):
        return jsonify({"error": "File no longer on server"}), 404
    # Never serve files from outside the configured download folder.
    allowed = os.path.normpath(get_settings().download_folder)
    if not os.path.normpath(path).startswith(allowed):
        return jsonify({"error": "Forbidden"}), 403
    return send_file(path, as_attachment=True)


# ------------------------------------------------- direct browser stream
def _error_page(message: str) -> str:
    # This endpoint is navigated to directly (not fetched via XHR), so
    # failures must render as a readable page, not bare JSON.
    safe = message.replace("&", "&amp;").replace("<", "&lt;")
    return (
        "<!doctype html><title>Download</title>"
        "<body style='font-family:sans-serif;padding:2em'>"
        f"<h3>Download unavailable</h3><p>{safe}</p>"
        "<p><a href='/downloads'>&larr; Back</a></p></body>"
    )


@api_bp.route("/direct/download")
def direct_download():
    """Stream one video straight to the browser; nothing lands on disk."""
    url = (request.args.get("url") or "").strip()
    format_id = request.args.get("format_id") or "best"
    title = request.args.get("title") or "video"
    if not is_valid_youtube_url(url):
        return _error_page("Invalid YouTube URL."), 400
    try:
        resolved = resolve_direct(url, format_id)
    except Exception as ex:
        log.warning("direct resolve failed for %s: %s", url, ex)
        return _error_page(f"Could not resolve this quality: {ex}"), 502
    if resolved.get("mode") == "mux":
        return _error_page(
            "This quality is split into separate video + audio streams and "
            "would need FFmpeg merging, which isn't available on Android. "
            "Please pick a quality marked with "
            "\u27f3 (supports pause/resume)."
        ), 400
    return _proxy_stream(
        resolved["url"],
        resolved.get("headers") or {},
        title,
        resolved.get("ext") or "mp4",
    )


def _proxy_stream(url, headers, title, ext):
    safe_name = sanitize_filename(title) or "video"
    filename = (
        safe_name
        if safe_name.lower().endswith(f".{ext}")
        else f"{safe_name}.{ext}"
    )
    upstream_headers = {"User-Agent": headers.get("User-Agent", "Mozilla/5.0")}
    for key in ("Cookie", "Accept", "Accept-Language"):
        if headers.get(key):
            upstream_headers[key] = headers[key]
    # Forward Range so pause/resume works in the browser.
    if request.headers.get("Range"):
        upstream_headers["Range"] = request.headers["Range"]
    try:
        upstream = urllib.request.urlopen(
            urllib.request.Request(url, headers=upstream_headers), timeout=30
        )
    except urllib.error.HTTPError as ex:
        return _error_page(
            f"Upstream server refused the stream (HTTP {ex.code}). "
            "Try another quality."
        ), 502
    except Exception as ex:
        return _error_page(f"Could not start the stream: {ex}"), 502

    resp_headers = {
        "Content-Disposition": (
            "attachment; filename*=UTF-8''" + urllib.parse.quote(filename)
        ),
        "Accept-Ranges": "bytes",
    }
    for key in ("Content-Type", "Content-Length", "Content-Range"):
        value = upstream.headers.get(key)
        if value:
            resp_headers[key] = value
    resp_headers.setdefault("Content-Type", "application/octet-stream")

    def _generate():
        try:
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                upstream.close()
            except Exception:
                pass

    return Response(
        stream_with_context(_generate()),
        status=getattr(upstream, "status", 200),
        headers=resp_headers,
    )


# --------------------------------------------------------------- settings
@api_bp.route("/settings")
def settings_get():
    return jsonify(get_settings().to_dict())


@api_bp.route("/settings", methods=["POST"])
def settings_update():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(update_settings(data).to_dict())
