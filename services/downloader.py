"""Thin wrapper around yt-dlp for metadata / format discovery.

Two-tier fetch strategy (important for large playlists / channels with
thousands of videos):
  - fetch_overview(): fast, uses extract_flat -- just id/title/thumbnail
    for every entry. Good for listing a whole playlist instantly.
  - fetch_formats(): full extraction for ONE video -- returns every
    available format (resolution, fps, codec, bitrate, filesize, etc).
"""
import yt_dlp

# YouTube periodically blocks the default 'web' player client; falling
# back through android/ios clients avoids most "video unavailable" /
# "not found" errors without any user action.
PLAYER_CLIENTS = {"youtube": {"player_client": ["android", "ios", "web"]}}


def _base_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": PLAYER_CLIENTS,
    }
    if extra:
        opts.update(extra)
    return opts


def fetch_overview(url: str) -> dict:
    """Returns {'type': 'video'|'playlist'|'channel', 'title', 'entries': [...] }
    entries each: {id, url, title, thumbnail, uploader, duration}
    """
    last_error = None
    for flat in (True, False):
        try:
            with yt_dlp.YoutubeDL(_base_opts({"extract_flat": flat, "skip_download": True})) as ydl:
                info = ydl.extract_info(url, download=False)

            entries_raw = info.get("entries")
            if entries_raw:
                entries = []
                for e in entries_raw:
                    if not e:
                        continue
                    vid_id = e.get("id")
                    vid_url = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else e.get("url")
                    entries.append({
                        "id": vid_id or vid_url,
                        "url": vid_url,
                        "title": e.get("title") or "Untitled",
                        "thumbnail": e.get("thumbnail") or e.get("thumbnails", [{}])[-1].get("url", "") if e.get("thumbnails") else "",
                        "uploader": e.get("uploader") or info.get("uploader") or "",
                        "duration": e.get("duration") or 0,
                    })
                kind = "playlist"
                if info.get("_type") == "playlist" and info.get("webpage_url_basename") == "channel":
                    kind = "channel"
                return {"type": kind, "title": info.get("title") or "Playlist", "entries": entries}
            else:
                thumb = info.get("thumbnail") or ""
                return {
                    "type": "video",
                    "title": info.get("title") or "Untitled",
                    "entries": [{
                        "id": info.get("id"),
                        "url": url,
                        "title": info.get("title") or "Untitled",
                        "thumbnail": thumb,
                        "uploader": info.get("uploader") or "",
                        "duration": info.get("duration") or 0,
                        "view_count": info.get("view_count"),
                        "upload_date": info.get("upload_date"),
                        "description": (info.get("description") or "")[:500],
                    }],
                }
        except Exception as ex:
            last_error = ex
            continue
    raise RuntimeError(f"Could not fetch info: {last_error}")


def fetch_formats(url: str) -> dict:
    """Full metadata + all available formats for a single video."""
    last_error = None
    for client_order in (PLAYER_CLIENTS, {"youtube": {"player_client": ["ios", "android", "web"]}}):
        try:
            with yt_dlp.YoutubeDL(_base_opts({"extractor_args": client_order})) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = []
            for f in info.get("formats", []):
                if f.get("vcodec") == "none" and f.get("acodec") == "none":
                    continue
                formats.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f.get("resolution") or (f"{f.get('height')}p" if f.get("height") else "audio"),
                    "fps": f.get("fps"),
                    "vcodec": f.get("vcodec"),
                    "acodec": f.get("acodec"),
                    "abr": f.get("abr"),
                    "tbr": f.get("tbr"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "dynamic_range": f.get("dynamic_range"),
                    "is_audio_only": f.get("vcodec") == "none",
                    "is_video_only": f.get("acodec") == "none",
                })
            return {
                "id": info.get("id"),
                "title": info.get("title") or "Untitled",
                "uploader": info.get("uploader") or "",
                "thumbnail": info.get("thumbnail") or "",
                "duration": info.get("duration") or 0,
                "view_count": info.get("view_count"),
                "upload_date": info.get("upload_date"),
                "description": (info.get("description") or "")[:1000],
                "subtitles": list((info.get("subtitles") or {}).keys()),
                "automatic_captions": list((info.get("automatic_captions") or {}).keys())[:15],
                "formats": formats,
            }
        except Exception as ex:
            last_error = ex
            continue
    raise RuntimeError(f"Could not fetch formats: {last_error}")


def resolve_direct(url: str, format_id: str) -> dict:
    """Resolves a chosen format to its live CDN URL(s) with no download and
    no disk write -- used to stream straight to the browser.

    Returns either:
      {"mode": "proxy", "url", "headers", "ext"}  -- one stream, can be
        passed through with Range support (real pause/resume).
      {"mode": "mux", "video_url", "video_headers", "audio_url",
        "audio_headers"}  -- separate video+audio that must be muxed live
        with ffmpeg; can't be byte-resumed.
    """
    last_error = None
    for client_order in (PLAYER_CLIENTS, {"youtube": {"player_client": ["ios", "android", "web"]}}):
        try:
            with yt_dlp.YoutubeDL(_base_opts({"format": format_id, "extractor_args": client_order})) as ydl:
                info = ydl.extract_info(url, download=False)

            req = info.get("requested_formats")
            if req and len(req) == 2:
                video_f, audio_f = req[0], req[1]
                return {
                    "mode": "mux",
                    "video_url": video_f["url"], "video_headers": video_f.get("http_headers") or {},
                    "audio_url": audio_f["url"], "audio_headers": audio_f.get("http_headers") or {},
                }
            return {
                "mode": "proxy",
                "url": info.get("url"),
                "headers": info.get("http_headers") or {},
                "ext": info.get("ext") or "mp4",
            }
        except Exception as ex:
            last_error = ex
            continue
    raise RuntimeError(f"Could not resolve format: {last_error}")
