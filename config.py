"""Central configuration for YT Downloader X Pro.

Storage notes (this is what used to crash the APK on launch):
  * On Android (python-for-android, any bootstrap) every writable file --
    the SQLite database, downloads, temp files and logs -- lives under the
    app's *private* storage directory, which is always writable and needs
    no storage permission.
  * On desktop everything stays next to the source tree, as before.

All values can be overridden with YTDLX_* environment variables (handy
for tests: set YTDLX_DATABASE_URI to a temp file).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def is_android() -> bool:
    """True when running inside the Android APK."""
    if "ANDROID_PRIVATE" in os.environ or "ANDROID_STORAGE" in os.environ:
        return True
    try:
        import android  # noqa: F401  (only importable on-device)
        return True
    except Exception:
        return False


def _data_dir() -> str:
    """Writable base directory for DB / downloads / temp / logs."""
    if is_android():
        try:
            from android.storage import app_storage_path
            path = os.path.join(app_storage_path(), "ytdlx")
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            pass  # fall through to BASE_DIR (also private+writable on device)
    return BASE_DIR


DATA_DIR = _data_dir()


def _port() -> int:
    try:
        return int(os.environ.get("YTDLX_PORT", "5000"))
    except (TypeError, ValueError):
        return 5000


class Config:
    SECRET_KEY = os.environ.get(
        "YTDLX_SECRET_KEY", "change-this-secret-in-production"
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "YTDLX_DATABASE_URI",
        f"sqlite:///{os.path.join(DATA_DIR, 'database.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # The app is heavily multithreaded (request threads + dispatcher +
    # download workers share one SQLite file). Without this, pooled
    # connections raise "SQLite objects created in a thread can only be
    # used in that same thread" and busy writers raise "database is
    # locked" -- both used to surface as instant failures on-device.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False, "timeout": 30},
    }

    DEFAULT_DOWNLOAD_FOLDER = os.environ.get(
        "YTDLX_DOWNLOAD_FOLDER", os.path.join(DATA_DIR, "downloads")
    )
    DEFAULT_TEMP_FOLDER = os.environ.get(
        "YTDLX_TEMP_FOLDER", os.path.join(DATA_DIR, "temp")
    )
    LOG_DIR = os.environ.get("YTDLX_LOG_DIR", os.path.join(DATA_DIR, "logs"))

    DEFAULT_MAX_CONCURRENT = 3
    DEFAULT_CONCURRENT_FRAGMENTS = 8
    DEFAULT_MAX_RETRIES = 3

    # On Android the UI is the on-device WebView, so bind loopback only
    # (least privilege, no LAN exposure). On desktop keep 0.0.0.0.
    HOST = os.environ.get(
        "YTDLX_HOST", "127.0.0.1" if is_android() else "0.0.0.0"
    )
    PORT = _port()
