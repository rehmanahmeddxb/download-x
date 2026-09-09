"""Input validation / sanitization -- security-relevant helpers."""
import re
from urllib.parse import urlparse

ALLOWED_HOST_FRAGMENTS = ("youtube.com", "youtu.be", "music.youtube.com")


def is_valid_youtube_url(url: str) -> bool:
    """Basic scheme + host allow-list check. Does not guarantee the video
    exists -- yt-dlp itself validates that when fetching."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.netloc or "").lower()
    return any(frag in host for frag in ALLOWED_HOST_FRAGMENTS)


def sanitize_filename(name: str) -> str:
    """Strip path separators and other characters that could enable path
    traversal or break the filesystem."""
    if not name:
        return "file"
    name = name.replace("/", "_").replace("\\", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name[:200] or "file"


def safe_join_download_path(base_folder: str, filename: str) -> str:
    """Prevent path traversal when building an output path from a
    user/metadata-derived filename."""
    import os
    safe_name = sanitize_filename(filename)
    full_path = os.path.normpath(os.path.join(base_folder, safe_name))
    if not full_path.startswith(os.path.normpath(base_folder)):
        raise ValueError("Invalid output path (path traversal blocked)")
    return full_path
