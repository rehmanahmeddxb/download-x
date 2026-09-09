"""
JSON API routes for YT Downloader X Pro.

This is a minimal placeholder -- the full implementation lives in the
upstream project (queue management, settings CRUD, history CSV export,
yt-dlp format probing, etc.) and is intentionally kept out of the APK
build so the static-info pages can be served without the heavy backend
dependencies.

The blueprint is still registered in app.py so future modules can add
endpoints here without touching the bootstrap code.
"""
from flask import Blueprint

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    return {"status": "ok"}
