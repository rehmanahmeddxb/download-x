"""Central configuration for YT Downloader X Pro.

Storage notes (this is what used to crash the APK on launch):
  * On Android (python-for-android, any bootstrap) every writable file --
    the SQLite database, temp files and logs -- lives under the app's
    *private* storage directory, which is always writable and needs
    no storage permission.
  * Finished downloads default to the app-specific folder on *shared*
    storage (``Android/data/<package>/files/...``), which is writable
    without any permission on Android 4.4+ AND visible in file managers --
    a downloader whose files the user can't reach is useless.
  * On desktop everything stays next to the source tree, as before.

All values can be overridden with YTDLX_* environment variables (handy
for tests: set YTDLX_DATABASE_URI to a temp file).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ANDROID_PACKAGE = "org.downloadsx.downloadsx"


def _point_ssl_at_bundled_cas() -> None:
    """Make every default TLS context use the bundled certifi CA file.

    Android ships no CA path Python's ``ssl`` module can use, so without
    this every HTTPS call (yt-dlp fetches, the urllib direct-stream
    proxy) fails on-device with "certificate verify failed". yt-dlp
    prefers certifi on its own when it is installed; exporting
    ``SSL_CERT_FILE`` covers everything else that builds a default
    context (``ssl.create_default_context`` honors it). Respects an
    explicitly configured environment and never raises.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi

        bundle = certifi.where()
        if os.path.isfile(bundle):
            os.environ["SSL_CERT_FILE"] = bundle
    except Exception:
        pass


_point_ssl_at_bundled_cas()


def is_android() -> bool:
    """True when running inside the Android APK."""
    if sys.platform == "android":
        return True
    if any(
        var in os.environ
        for var in (
            "ANDROID_ARGUMENT",
            "ANDROID_PRIVATE",
            "ANDROID_APP_PATH",
            "ANDROID_STORAGE",
        )
    ):
        return True
    try:
        import android  # noqa: F401  (only importable on-device)
        return True
    except Exception:
        return False


def _data_dir() -> str:
    """Writable base directory for DB / temp / logs."""
    if is_android():
        try:
            from android.storage import app_storage_path
            path = os.path.join(app_storage_path(), "ytdlx")
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            pass  # fall through to BASE_DIR (also private+writable on device)
    return BASE_DIR


def _downloads_dir(data_dir: str) -> str:
    """Default folder for finished downloads.

    On Android this prefers the app-specific directory on shared storage
    so files are reachable from any file manager (no permission needed);
    if shared storage is missing (rare), it falls back to private storage.
    """
    if is_android():
        try:
            from android.storage import primary_external_storage_path
            shared = os.path.join(
                primary_external_storage_path(),
                "Android", "data", ANDROID_PACKAGE, "files",
                "ytdlx", "downloads",
            )
            os.makedirs(shared, exist_ok=True)
            # Prove writability (a read-only mount would fail later anyway).
            probe = os.path.join(shared, ".write-test")
            with open(probe, "w") as fh:
                fh.write("ok")
            os.remove(probe)
            return shared
        except Exception:
            pass
    return os.path.join(data_dir, "downloads")


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
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False, "timeout": 30},
    }

    DEFAULT_DOWNLOAD_FOLDER = os.environ.get(
        "YTDLX_DOWNLOAD_FOLDER", _downloads_dir(DATA_DIR)
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
