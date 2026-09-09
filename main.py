"""YT Downloader X Pro -- Android (APK) entry point.

The APK uses the python-for-android ``webview`` bootstrap: Android shows a
native WebView pointed at http://127.0.0.1:5000 (with a loading screen
until the server is up) while this file runs the Flask server that
renders the UI. No Kivy / SDL needed -- which is also what keeps the APK
small.

Crash-proofing:
  * ``faulthandler`` prints a Python traceback to logcat even on segfaults,
  * every exception (including in background threads) is appended to
    ``<LOG_DIR>/crash.log`` and printed (visible via ``adb logcat``),
  * the Flask/app imports happen *inside* the guarded server loop, so a
    broken dependency shows up in crash.log instead of killing the
    process before the hooks are even installed,
  * if the Flask server ever exits or fails to start, it is restarted
    with backoff instead of taking the whole app down,
  * the main thread never returns, so the process (and the daemon server
    thread) stays alive for the whole app lifetime.

Running ``python main.py`` on a desktop does the same thing and then
opens the system browser -- handy for debugging the exact code path the
APK uses.
"""
import faulthandler
import os
import sys
import threading
import time
import traceback
import urllib.request

# Print fatal tracebacks (segfaults etc.) to stderr (= logcat on Android).
faulthandler.enable()

# Make sure the project root is on sys.path so the `app`, `config`,
# `services`, `routes`, etc. packages can be imported normally.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# NOTE: `config` is intentionally imported here (it is pure stdlib and
# cannot fail), but `app` is imported lazily inside _serve_forever so a
# broken dependency lands in crash.log instead of killing the process
# before the crash hooks below are installed.
from config import Config, is_android  # noqa: E402

CRASH_LOG = os.path.join(Config.LOG_DIR, "crash.log")


def _log_crash(text: str) -> None:
    """Persist a traceback where it can be retrieved after the fact."""
    try:
        os.makedirs(Config.LOG_DIR, exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{text}\n")
    except Exception:
        pass
    try:
        # `adb logcat` shows everything printed by the Python process.
        print(f"[ytdlx] {text}", flush=True)
    except Exception:
        pass


def _install_crash_hooks() -> None:
    def _hook(exc_type, exc, tb):
        _log_crash(
            "Uncaught exception:\n"
            + "".join(traceback.format_exception(exc_type, exc, tb))
        )

    sys.excepthook = _hook
    try:

        def _thread_hook(args):
            _log_crash(
                f"Uncaught exception in thread {args.thread.name}:\n"
                + "".join(
                    traceback.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback
                    )
                )
            )

        threading.excepthook = _thread_hook
    except AttributeError:
        pass  # Python < 3.8 -- never on our toolchain, but harmless


def _wait_for_server(timeout: float = 60.0) -> bool:
    url = f"http://127.0.0.1:{Config.PORT}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _serve_forever() -> None:
    backoff = 2
    while True:
        try:
            print(
                f"[ytdlx] starting server on {Config.HOST}:{Config.PORT}",
                flush=True,
            )
            from app import create_app  # lazy: see module docstring

            flask_app = create_app()
            backoff = 2  # a clean start resets the backoff
            # threaded=True so the WebView can poll /api/* while yt-dlp
            # downloads are happening on worker threads.
            flask_app.run(
                host=Config.HOST,
                port=Config.PORT,
                debug=False,
                threaded=True,
                use_reloader=False,
            )
            _log_crash("Flask server exited unexpectedly; restarting...")
        except Exception:
            _log_crash(
                f"Server error, restarting in {backoff}s:\n"
                + traceback.format_exc()
            )
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)


def main() -> None:
    _install_crash_hooks()

    server = threading.Thread(
        target=_serve_forever, name="flask-server", daemon=True
    )
    server.start()

    if not is_android():
        # Desktop debug run: open the system browser once the server is up.
        if _wait_for_server(timeout=60):
            try:
                import webbrowser

                webbrowser.open(f"http://127.0.0.1:{Config.PORT}/")
            except Exception as exc:
                print(f"[ytdlx] could not open browser: {exc!r}", flush=True)
        else:
            print("[ytdlx] server did not become ready in time", flush=True)
    else:
        print(
            "[ytdlx] running on Android; the WebView bootstrap loads the UI",
            flush=True,
        )

    # Never return: the bootstrap's WebView needs this process (and the
    # daemon server thread) alive for the whole app lifetime.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
