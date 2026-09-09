"""
YT Downloader X Pro -- Android (APK) entry point.

Starts the Flask app in a background thread (waitress when available,
Flask's dev server otherwise) and shows a small Kivy status screen with
the server URL, an "Open in Browser" button and a log viewer.

Crash-proofing (this is what turns "opens then instantly closes with no
message" into something diagnosable):

* ``faulthandler`` dumps a Python traceback to logcat even on segfaults.
* every startup failure is written to ``logs/crash.log`` AND shown on
  screen instead of killing the process silently.
* the server thread is watched: if it dies, the status screen shows the
  error instead of pretending everything is fine.
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


def _early_log_path():
    """Crash-log path that works even if `config` itself is broken."""
    try:
        from utils.android import get_crash_log_path

        return get_crash_log_path()
    except Exception:
        import tempfile

        return os.path.join(tempfile.gettempdir(), "downloadsx-crash.log")


def log_crash(title, exc_text):
    """Append a crash report to the log file and echo it (logcat)."""
    report = f"\n===== {title} @ {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{exc_text}\n"
    print(report, flush=True)
    try:
        path = _early_log_path()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(report)
        print(f"[main] crash report written to {path}", flush=True)
    except Exception as exc:
        print(f"[main] could not write crash log: {exc!r}", flush=True)


def _excepthook(exc_type, exc, tb):
    log_crash("uncaught exception (main thread)", "".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = _excepthook


class ServerState:
    """Shared between the server thread and the Kivy UI thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "starting"  # starting | running | failed
        self.url = ""
        self.error = ""
        self.log_path = ""

    def set(self, **kwargs):
        with self.lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def snapshot(self):
        with self.lock:
            return dict(
                status=self.status, url=self.url, error=self.error, log_path=self.log_path
            )


STATE = ServerState()


def _wait_for_health(url, timeout=30.0):
    """Poll /api/health until the server answers or the timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _start_server():
    from app import create_app, run_server
    from config import Config

    try:
        try:
            from utils.android import request_storage_permissions

            request_storage_permissions()
        except Exception:
            pass  # optional; internal storage works without permissions

        flask_app = create_app()
        port = int(flask_app.config.get("PORT", Config.PORT))
        url = f"http://127.0.0.1:{port}"
        STATE.set(url=url, log_path=os.path.join(Config.LOG_DIR, "app.log"))
        run_server(flask_app)  # blocks until the process exits
        STATE.set(status="failed", error="The web server stopped unexpectedly.")
    except Exception:
        text = traceback.format_exc()
        log_crash("server thread failed", text)
        STATE.set(status="failed", error=text[-2000:])


def _launch_server_thread():
    thread = threading.Thread(target=_start_server, daemon=True, name="flask-server")
    thread.start()

    def _watchdog():
        # Give the server a moment to bind, then verify it answers.
        time.sleep(1.0)
        snap = STATE.snapshot()
        url = snap["url"]
        for _ in range(60):  # up to ~30s for slow first boot (yt-dlp import)
            snap = STATE.snapshot()
            if snap["status"] == "failed":
                return
            if snap["url"] and _wait_for_health(snap["url"], timeout=1.5):
                STATE.set(status="running")
                print(f"[main] server is up at {snap['url']}", flush=True)
                return
            if not thread.is_alive():
                STATE.set(status="failed",
                           error="The web server stopped unexpectedly.")
                return
            time.sleep(0.5)
        if STATE.snapshot()["status"] == "starting":
            STATE.set(status="failed",
                       error="Timed out waiting for the web server to start. "
                             "See the logs for details.")

    threading.Thread(target=_watchdog, daemon=True, name="server-watchdog").start()
    return thread


# ------------------------------------------------------------------ Kivy UI
def _run_kivy_ui():
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    def _read_tail(path, limit=12000):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - limit))
                return fh.read() or "(empty)"
        except Exception as exc:
            return f"(could not read {path}: {exc})"

    class HostApp(App):
        title = "YT Downloader X Pro"

        def build(self):
            self.status_label = Label(
                text="Starting server...", halign="center", valign="middle",
                size_hint_y=0.35,
            )
            self.status_label.bind(size=self._fit_text)
            self.error_label = Label(
                text="", halign="left", valign="top",
                size_hint_y=0.35, font_size="12sp",
            )
            self.error_label.bind(size=self._fit_text)

            open_btn = Button(text="Open App in Browser", size_hint_y=0.12)
            open_btn.bind(on_press=self._open_browser)
            logs_btn = Button(text="View Logs", size_hint_y=0.12)
            logs_btn.bind(on_press=self._show_logs)

            root = BoxLayout(orientation="vertical", padding=16, spacing=8)
            root.add_widget(Label(text="YT Downloader X Pro",
                                  font_size="22sp", size_hint_y=0.15))
            root.add_widget(self.status_label)
            root.add_widget(self.error_label)
            root.add_widget(open_btn)
            root.add_widget(logs_btn)

            Clock.schedule_interval(self._refresh, 1.0)
            self._refresh(0)
            return root

        @staticmethod
        def _fit_text(label, *_args):
            label.text_size = (label.width, None)

        def _refresh(self, _dt):
            snap = STATE.snapshot()
            if snap["status"] == "running":
                self.status_label.text = (
                    f"Server is running.\n{snap['url']}\n\n"
                    "Tap below to open the app in your browser."
                )
                self.error_label.text = ""
            elif snap["status"] == "failed":
                self.status_label.text = (
                    "Server failed to start.\n"
                    f"Details below and in:\n{snap['log_path'] or _early_log_path()}"
                )
                self.error_label.text = snap["error"] or "(no details captured)"
            else:
                self.status_label.text = "Starting server...\n(first boot can take ~20s)"

        def _open_browser(self, _btn):
            snap = STATE.snapshot()
            url = snap["url"] or "http://127.0.0.1:5000"
            try:
                from utils.android import open_in_browser

                ok = open_in_browser(url)
            except Exception:
                ok = False
            if not ok:
                self.error_label.text = f"Could not open a browser. Go to {url} manually."

        def _show_logs(self, _btn):
            snap = STATE.snapshot()
            app_log = snap["log_path"] or os.path.join("logs", "app.log")
            text = (
                f"--- {app_log} ---\n{_read_tail(app_log)}\n\n"
                f"--- {_early_log_path()} ---\n{_read_tail(_early_log_path())}"
            )
            view = ScrollView()
            label = Label(text=text, halign="left", valign="top",
                          size_hint_y=None, font_size="11sp")
            label.bind(
                width=lambda inst, w: setattr(inst, "text_size", (w, None)),
                texture_size=lambda inst, size: setattr(inst, "height", size[1]),
            )
            view.add_widget(label)
            Popup(title="Logs", content=view, size_hint=(0.95, 0.9)).open()

    HostApp().run()


def main():
    server_thread = _launch_server_thread()

    try:
        _run_kivy_ui()
    except ImportError as exc:
        # Kivy isn't installed (e.g. plain `python main.py` on a desktop for
        # debugging): just keep serving Flask in this process.
        print(f"[main] Kivy unavailable ({exc!r}); running server only.", flush=True)
        snap = STATE.snapshot()
        if snap["url"]:
            print(f"[main] Open {snap['url']} in your browser.", flush=True)
        server_thread.join()
    except Exception:
        log_crash("Kivy UI failed", traceback.format_exc())
        # Keep the server alive in the background even if the UI died, so a
        # browser pointed at the URL keeps working.
        server_thread.join()


if __name__ == "__main__":
    main()
