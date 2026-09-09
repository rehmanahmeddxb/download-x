"""Small shared helpers used across services/routes."""
import os
import shutil
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def get_disk_usage(path: str):
    """Returns (used_bytes, total_bytes, free_bytes) for the disk holding
    `path`, falling back to '.' if the path doesn't exist yet."""
    check_path = path if os.path.exists(path) else "."
    total, used, free = shutil.disk_usage(check_path)
    return used, total, free


def detect_content_type(url: str) -> str:
    """Best-effort classification of a pasted URL for the UI badge.
    yt-dlp itself handles the actual extraction correctly regardless."""
    u = url.lower()
    if "playlist" in u or "list=" in u:
        return "playlist"
    if "/shorts/" in u:
        return "shorts"
    if "/channel/" in u or "/@" in u or "/c/" in u:
        return "channel"
    if "live" in u:
        return "live"
    return "video"
