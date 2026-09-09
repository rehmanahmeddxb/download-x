"""
YT Downloader X Pro -- Android (APK) entry point.

This file is the entry point that Buildozer / python-for-android looks for.
It starts the Flask app in a background thread (so the HTTP server keeps
serving the UI) and then runs a tiny Kivy event loop so the process stays
alive. The user opens the bundled WebView to interact with the app.
"""
import threading
import os
import sys

# Make sure the project root is on sys.path so the `app`, `config`,
# `services`, `routes`, etc. packages can be imported normally.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app       # noqa: E402  (intentional after sys.path tweak)
from config import Config        # noqa: E402


def _start_flask():
    flask_app = create_app()
    # threaded=True so the browser can poll /api/* while yt-dlp downloads
    # are happening on worker threads.
    flask_app.run(host=Config.HOST, port=Config.PORT,
                  debug=False, threaded=True, use_reloader=False)


def main():
    # Boot the web server in the background, then hand control to Kivy
    # so the Android process has an event loop and doesn't get killed.
    t = threading.Thread(target=_start_flask, daemon=True)
    t.start()

    try:
        # Lazy import so the rest of main.py works even if Kivy isn't
        # installed in the local dev environment.
        from kivy.app import App
        from kivy.uix.label import Label

        class HostApp(App):
            def build(self):
                return Label(
                    text=(
                        "YT Downloader X Pro is running.\n\n"
                        "Open the in-app browser tab to use the UI.\n"
                        f"Server: http://127.0.0.1:{Config.PORT}"
                    ),
                    halign="center",
                    valign="middle",
                )

        HostApp().run()
    except Exception as exc:
        # If Kivy isn't available (e.g. running `python main.py` on a
        # normal desktop for debugging) just keep the Flask thread alive.
        print(f"[main] Kivy unavailable ({exc!r}); running Flask only.")
        t.join()


if __name__ == "__main__":
    main()
