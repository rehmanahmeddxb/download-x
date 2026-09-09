"""Small Android helpers. Every function degrades gracefully on desktop
(where pyjnius / the `android` module don't exist) so this module is safe
to import anywhere.
"""
import os
import webbrowser

from config import is_android


def open_in_browser(url: str) -> bool:
    """Open `url` in the device's browser. Returns True on success."""
    if is_android():
        try:
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            PythonActivity.mActivity.startActivity(intent)
            return True
        except Exception:
            pass  # fall through to webbrowser below
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def request_storage_permissions() -> None:
    """Best-effort runtime permission request (Android 6+).

    Fire-and-forget: internal + app-specific external dirs work without
    any permission, so the app must keep booting even if the user denies
    or the request API is unavailable.
    """
    if not is_android():
        return
    try:
        from android.permissions import Permission, request_permissions

        request_permissions(
            [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
        )
    except Exception:
        pass


def get_crash_log_path() -> str:
    """Writable path for the startup crash log, desktop or Android."""
    try:
        from config import Config

        log_dir = Config.LOG_DIR
    except Exception:
        import tempfile

        log_dir = tempfile.gettempdir()
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        import tempfile

        log_dir = tempfile.gettempdir()
    return os.path.join(log_dir, "crash.log")
