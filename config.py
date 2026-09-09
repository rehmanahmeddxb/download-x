"""Central configuration.

Desktop behaviour is unchanged: database, downloads, temp files and logs
live next to the source tree.

On Android (python-for-android) the source directory is read-only-ish and
user files must live in the app's private storage, so all writable paths
are relocated there:

* ``files/downloadsx/``            -> SQLite database, logs, temp files
* ``external files/downloadsx/``   -> finished downloads (visible in the
  device's file manager, no storage permission needed on Android 10+)
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def is_android() -> bool:
    """True when running inside the Android APK (python-for-android)."""
    if sys.platform == "android":
        return True
    return any(
        var in os.environ
        for var in ("ANDROID_ARGUMENT", "ANDROID_PRIVATE", "ANDROID_APP_PATH")
    )


def _android_dirs():
    """Returns (private_dir, external_dir) on Android, else (None, None).

    Uses pyjnius to ask the Activity for its storage roots. Any failure
    falls back to ``None`` so the caller can use BASE_DIR instead.
    """
    if not is_android():
        return None, None
    try:
        from jnius import autoclass  # lazy: only installed inside the APK

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        private = activity.getFilesDir().getAbsolutePath()
        try:
            ext_file = activity.getExternalFilesDir(None)
            external = ext_file.getAbsolutePath() if ext_file else None
        except Exception:
            external = None
        return private, external
    except Exception:
        return None, None


def _resolve_dirs():
    private, external = _android_dirs()
    if private:
        root = os.path.join(private, "downloadsx")
        dl_root = (
            os.path.join(external, "downloadsx", "downloads")
            if external
            else os.path.join(root, "downloads")
        )
        return {
            "db": os.path.join(root, "database.db"),
            "downloads": dl_root,
            "temp": os.path.join(root, "temp"),
            "logs": os.path.join(root, "logs"),
        }
    return {
        "db": os.path.join(BASE_DIR, "database.db"),
        "downloads": os.path.join(BASE_DIR, "downloads"),
        "temp": os.path.join(BASE_DIR, "temp"),
        "logs": os.path.join(BASE_DIR, "logs"),
    }


_PATHS = _resolve_dirs()

IS_ANDROID = is_android()


class Config:
    SECRET_KEY = os.environ.get("YTDX_SECRET_KEY", "change-this-secret-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "YTDX_DATABASE_URI", f"sqlite:///{_PATHS['db']}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Engine options: pre-ping avoids stale pooled connections after the
    # device sleeps; a generous timeout avoids "database is locked" when
    # the dispatcher and download threads write at the same time.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 30},
    }

    DATABASE_PATH = _PATHS["db"]
    DEFAULT_DOWNLOAD_FOLDER = os.environ.get(
        "YTDX_DOWNLOAD_FOLDER", _PATHS["downloads"]
    )
    DEFAULT_TEMP_FOLDER = os.environ.get("YTDX_TEMP_FOLDER", _PATHS["temp"])
    LOG_DIR = os.environ.get("YTDX_LOG_DIR", _PATHS["logs"])

    DEFAULT_MAX_CONCURRENT = int(os.environ.get("YTDX_MAX_CONCURRENT", "3"))
    DEFAULT_CONCURRENT_FRAGMENTS = int(os.environ.get("YTDX_FRAGMENTS", "8"))
    DEFAULT_MAX_RETRIES = int(os.environ.get("YTDX_MAX_RETRIES", "3"))

    HOST = os.environ.get("YTDX_HOST", "0.0.0.0")
    PORT = int(os.environ.get("YTDX_PORT", "5000"))
