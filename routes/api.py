"""
JSON API routes for YT Downloader X Pro.

Endpoints (all under the ``/api`` prefix):

* ``GET  /health``                        liveness probe (also used by the
  Android launcher to detect when the server is up)
* ``GET  /stats``                         dashboard counters + charts data
* ``POST /fetch``            {url}        video/playlist/channel overview
* ``POST /fetch_formats``    {url}        full format list for one video
* ``POST /queue/add``        {items[]}    enqueue downloads
* ``GET  /tasks``                         queue incl. live progress
* ``POST /tasks/<id>/<action>``           pause|resume|cancel|retry|remove|
  priority_up|priority_down
* ``GET  /tasks/<id>/file``               download a finished file
* ``GET  /direct/download?url&format_id&title``
  stream straight to the browser (no server-side file)
* ``GET  /settings`` / ``POST /settings`` settings CRUD
* ``GET  /history?search&scope``          history list (scope=session for
  "this run" activity feed)
* ``DELETE /history/<id>``                delete one history row
* ``POST /history/<id>/redownload`` {url} re-queue a history entry
* ``GET  /history/export.csv``            CSV export
* ``POST /contact``          {name,email,subject,message}
  contact form (validated + logged, no mail server needed)
"""
import os
import time
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, jsonify, request, send_file, stream_with_context
from sqlalchemy import func as sa_func

from extensions import db
from models.download import Download
from models.history import HistoryEntry
from services import downloader
from services.queue_manager import queue_manager
from services.settings_service import get_settings, update_settings
from services.history_service import (
    delete_history_entry,
    export_history_csv,
    list_history,
)
from utils.helpers import get_disk_usage
from utils.logger import get_logger
from utils.validators import is_valid_youtube_url, sanitize_filename

api_bp = Blueprint("api", __name__)


def _session_id() -> str:
    return current_app.config.get("SESSION_ID", "")


# ------------------------------------------------------------------ health
@api_bp.route("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------- stats
@api_bp.route("/stats")
def stats():
    sid = _session_id()
    total = db.session.query(sa_func.count(Download.id)).scalar() or 0
    completed = Download.query.filter_by(status="completed").count()
    active = Download.query.filter_by(status="downloading").count()
    queued = Download.query.filter_by(status="queued").count()
    failed_session = Download.query.filter_by(status="failed", session_id=sid).count()
    session_bytes = (
        db.session.query(
            sa_func.coalesce(sa_func.sum(Download.downloaded_bytes), 0)
        )
        .filter(Download.session_id == sid)
        .scalar()
        or 0
    )
    total_bytes = (
        db.session.query(sa_func.coalesce(sa_func.sum(Download.downloaded_bytes), 0)).scalar()
        or 0
    )
    top_uploader_row = (
        db.session.query(Download.uploader, sa_func.count(Download.id))
        .filter(Download.status == "completed")
        .group_by(Download.uploader)
        .order_by(sa_func.count(Download.id).desc())
        .first()
    )
    top_format_row = (
        db.session.query(Download.quality_label, sa_func.count(Download.id))
        .filter(Download.status == "completed")
        .group_by(Download.quality_label)
        .order_by(sa_func.count(Download.id).desc())
        .first()
    )

    # Per-day completions for the last 7 days (dashboard bar chart).
    labels, counts = [], []
    today = datetime.now().date()
    for back in range(6, -1, -1):
        day = today - timedelta(days=back)
        start = time.mktime(day.timetuple())
        end = start + 86400
        labels.append(day.strftime("%m-%d"))
        counts.append(
            HistoryEntry.query.filter(
                HistoryEntry.date_completed >= start,
                HistoryEntry.date_completed < end,
                HistoryEntry.status == "completed",
            ).count()
        )

    _used, _total, _free = get_disk_usage(get_settings().download_folder or ".")

    return jsonify(
        {
            "total_downloads": total,
            "completed_downloads": completed,
            "active_downloads": active,
            "queued_downloads": queued,
            "downloaded_session_bytes": int(session_bytes),
            "failed_downloads": failed_session,
            "total_gb_downloaded": f"{total_bytes / 1024**3:.1f} GB",
            "success_rate": round(completed / total * 100, 1) if total else 100.0,
            "top_uploader": (top_uploader_row[0] if top_uploader_row and top_uploader_row[0] else "-"),
            "top_format": (top_format_row[0] if top_format_row and top_format_row[0] else "-"),
            "chart_days_labels": labels,
            "chart_days_counts": counts,
            "disk_used_bytes": _used,
            "disk_total_bytes": _total,
            "disk_free_bytes": _free,
        }
    )


# ------------------------------------------------------------------- fetch
@api_bp.route("/fetch", methods=["POST"])
def fetch():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please paste a valid YouTube link."}), 400
    try:
        return jsonify(downloader.fetch_overview(url))
    except RuntimeError as ex:
        get_logger().warning(f"fetch failed for {url}: {ex}")
        return jsonify({"error": str(ex)}), 502


@api_bp.route("/fetch_formats", methods=["POST"])
def fetch_formats():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please paste a valid YouTube link."}), 400
    try:
        return jsonify(downloader.fetch_formats(url))
    except RuntimeError as ex:
        get_logger().warning(f"fetch_formats failed for {url}: {ex}")
        return jsonify({"error": str(ex)}), 502


# ------------------------------------------------------------------- queue
@api_bp.route("/queue/add", methods=["POST"])
def queue_add():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Nothing to add."}), 400
    sid = _session_id()
    added, skipped = 0, 0
    for item in items:
        url = (item.get("url") or "").strip()
        if not is_valid_youtube_url(url):
            skipped += 1
            continue
        queue_manager.add_task(
            url=url,
            format_id=item.get("format_id") or "bestvideo+bestaudio/best",
            quality_label=item.get("quality_label") or "Best",
            title=item.get("title") or "Untitled",
            thumbnail=item.get("thumbnail") or "",
            uploader=item.get("uploader") or "",
            session_id=sid,
        )
        added += 1
    return jsonify({"count": added, "skipped": skipped})


@api_bp.route("/tasks")
def tasks():
    rows = Download.query.order_by(
        Download.priority.asc(), Download.created_time.asc()
    ).all()
    return jsonify([t.to_dict() for t in rows])


_TASK_ACTIONS = {"pause", "resume", "cancel", "retry", "remove"}


@api_bp.route("/tasks/<task_id>/<action>", methods=["POST"])
def task_action(task_id, action):
    if action in _TASK_ACTIONS:
        ok = getattr(queue_manager, action)(task_id)
    elif action in ("priority_up", "priority_down"):
        ok = queue_manager.reprioritize(task_id, "up" if action == "priority_up" else "down")
    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400
    if not ok:
        return jsonify({"error": "Task not found or action not allowed."}), 404
    return jsonify({"ok": True})


@api_bp.route("/tasks/<task_id>/file")
def task_file(task_id):
    task = db.session.get(Download, task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404
    if task.status != "completed" or not task.output_file:
        return jsonify({"error": "File is not ready yet."}), 409
    path = os.path.abspath(task.output_file)
    if not os.path.isfile(path):
        get_logger().warning(f"task file missing on disk: {path}")
        return jsonify({"error": "File no longer exists on the server."}), 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


# ---------------------------------------------------------- direct stream
@api_bp.route("/direct/download")
def direct_download():
    url = (request.args.get("url") or "").strip()
    format_id = request.args.get("format_id") or "best"
    title = request.args.get("title") or "video"
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube link."}), 400
    try:
        resolved = downloader.resolve_direct(url, format_id)
    except RuntimeError as ex:
        get_logger().warning(f"direct resolve failed for {url}: {ex}")
        return jsonify({"error": str(ex)}), 502

    if resolved.get("mode") == "mux":
        # Separate video+audio streams would need a live ffmpeg mux, which
        # the APK doesn't ship. Tell the user to pick a progressive quality.
        return (
            jsonify(
                {
                    "error": (
                        "That quality is split into separate video+audio streams "
                        "and can't be streamed directly. Pick a progressive "
                        "quality (marked with the resume icon) or add it to the "
                        "queue instead."
                    )
                }
            ),
            400,
        )

    try:
        import requests
    except ImportError:
        return jsonify({"error": "Direct streaming is unavailable in this build."}), 501

    upstream_headers = dict(resolved.get("headers") or {})
    # Pass through Range so the browser can pause/resume the transfer.
    if request.headers.get("Range"):
        upstream_headers["Range"] = request.headers["Range"]
    try:
        upstream = requests.get(resolved["url"], headers=upstream_headers,
                                stream=True, timeout=30)
    except Exception as ex:
        get_logger().warning(f"direct upstream failed: {ex}")
        return jsonify({"error": "Could not reach the media server."}), 502

    filename = f"{sanitize_filename(title)}.{resolved.get('ext') or 'mp4'}"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    for key in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
        if upstream.headers.get(key):
            headers[key] = upstream.headers[key]

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=65536)),
        status=upstream.status_code,
        headers=headers,
        direct_passthrough=True,
    )


# ---------------------------------------------------------------- settings
@api_bp.route("/settings")
def get_settings_route():
    return jsonify(get_settings().to_dict())


@api_bp.route("/settings", methods=["POST"])
def post_settings_route():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid settings payload."}), 400
    try:
        row = update_settings(data)
    except Exception as ex:
        get_logger().warning(f"settings update failed: {ex}")
        return jsonify({"error": "Could not save settings."}), 400
    # Make sure the (possibly new) folders exist right away so a typo
    # surfaces here instead of mid-download.
    for folder in (row.download_folder, row.temp_folder):
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as ex:
                return jsonify({"error": f"Cannot use folder '{folder}': {ex}"}), 400
    return jsonify(row.to_dict())


# ----------------------------------------------------------------- history
@api_bp.route("/history")
def history_list():
    search = request.args.get("search") or ""
    scope = request.args.get("scope") or ""
    entries = list_history(
        search=search,
        session_id=_session_id() if scope == "session" else None,
    )
    return jsonify([e.to_dict() for e in entries])


@api_bp.route("/history/<int:entry_id>", methods=["DELETE"])
def history_delete(entry_id):
    if not delete_history_entry(entry_id):
        return jsonify({"error": "History entry not found."}), 404
    return jsonify({"ok": True})


@api_bp.route("/history/<int:entry_id>/redownload", methods=["POST"])
def history_redownload(entry_id):
    entry = db.session.get(HistoryEntry, entry_id)
    if not entry:
        return jsonify({"error": "History entry not found."}), 404
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Please provide the original YouTube link."}), 400
    task = queue_manager.add_task(
        url=url,
        format_id=entry.format_id or "bestvideo+bestaudio/best",
        quality_label=entry.quality_label or "Best",
        title=entry.title,
        thumbnail=entry.thumbnail,
        uploader=entry.uploader,
        session_id=_session_id(),
    )
    return jsonify({"ok": True, "task_id": task.id})


@api_bp.route("/contact", methods=["POST"])
def contact():
    """Contact form submission. This is a self-hosted app with no mail
    server configured, so messages are validated and written to the app
    log for the operator to read (instead of pretending an email flew)."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    if not name or not email or not message:
        return jsonify({"error": "Name, email and message are required."}), 400
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400
    get_logger().info(
        "contact message from %s <%s> [%s]: %s",
        name[:80], email[:120], subject[:80], message[:2000],
    )
    return jsonify({"ok": True})


@api_bp.route("/history/export.csv")
def history_export():
    return Response(
        export_history_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=history.csv"},
    )
