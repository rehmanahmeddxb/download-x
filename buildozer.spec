# ---------------------------------------------------------------------------
# Buildozer / python-for-android spec for YT Downloader X Pro
#
# `buildozer android debug` (or `release`) reads this file to produce an
# installable .apk. The GitHub Actions workflow in
# .github/workflows/build-apk.yml drives that build and uploads the resulting
# APK as a workflow artifact.
#
# Size strategy (this is what keeps the APK small):
#   * `webview` bootstrap instead of SDL2/Kivy -- the UI is a native Android
#     WebView pointed at the bundled Flask server, so the whole game-engine
#     stack (~20 MB) and the Kivy dependency are gone.
#   * Minimal `requirements`: only what the code actually imports.
#   * Single 64-bit ABI (`android.archs = arm64-v8a`). Add `armeabi-v7a`
#     only if you must support 32-bit-only devices -- it roughly doubles
#     the native-code size.
#   * The desktop `database.db` is never packaged; the app creates a fresh
#     database in its private storage on first launch.
#   * `p4a-blacklist.txt` strips dead weight out of the Python bundle
#     (non-YouTube yt-dlp extractors, SQLAlchemy test helpers and
#     non-SQLite dialects, bytecode caches).
# ---------------------------------------------------------------------------

[app]

# (str) Title of your application
title = YT Downloader X Pro

# (str) Package name (must be a valid Python identifier, no dashes, dots ok)
package.name = downloadsx

# (str) Package domain (required by android for the package id)
package.domain = org.downloadsx

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all)
# NOTE: no `db` -- the APK must NOT bundle database.db. A fresh database is
# created in the app's private storage on first launch. Shipping a desktop
# database would leak download history into the artifact and resurrect
# stale queued tasks pointing at non-existent /storage paths.
source.include_exts = py,png,jpg,html,js,css

# (list) Source files to exclude
source.exclude_patterns = .git/*,.github/*,buildozer.spec,*.zip,*.log,database.db*,downloads/*,temp/*,logs/*,instance/*,__pycache__/*,bin/*,.buildozer/*,ci-artifacts/*,.ccache/*

# (str) Application versioning (method 1)
version = 0.2.0

# (int) Version code -- bump for every release so Android accepts the new
# APK as an upgrade over the previously installed one.
android.numeric_version = 2

# (list) Application requirements -- keep minimal AND complete: only
# packages the code actually imports, but ALL of them, including
# transitive pure-Python deps. p4a's automatic pip-dependency resolution
# silently drops packages it cannot fetch for Android (notably SQLAlchemy,
# which ships no Android wheel), so an unlisted dep simply ends up missing
# from the APK -- and the app then dies with ModuleNotFoundError on launch
# (or, with the webview bootstrap, spins on the loading screen forever).
# What each entry is for:
#   flask                  recipe (pulls jinja2/werkzeug/markupsafe/itsdangerous/click/blinker)
#   flask-sqlalchemy       pip, pure -- ORM integration (needs sqlalchemy below)
#   sqlalchemy             recipe -- ORM, compiled C extensions for ARM
#   typing-extensions      pip, pure -- imported unconditionally by sqlalchemy
#   yt-dlp                 pip, pure -- download engine (only the YouTube
#                          extractor stack is kept; the other ~930 site
#                          modules are stripped by p4a-blacklist.txt)
#   certifi                pip, pure -- TLS CA bundle. Android ships no usable
#                          system CA path for Python's ssl module, so without
#                          this every YouTube fetch/download fails with
#                          "certificate verify failed" (yt-dlp prefers certifi
#                          when present; config.py also exports SSL_CERT_FILE
#                          so stdlib urllib uses it too).
# Deliberately absent: Kivy (webview bootstrap needs no UI toolkit),
# waitress (Flask's threaded dev server is enough for a loopback server),
# requests (direct streaming uses stdlib urllib), APScheduler (unused),
# mutagen (thumbnail embedding needs ffmpeg anyway -- absent on Android).
# Version pins mirror requirements.txt so desktop and APK behave the same.
requirements = python3,flask==3.1.3,flask-sqlalchemy==3.1.1,sqlalchemy==2.0.52,typing-extensions==4.16.0,yt-dlp==2026.8.19,certifi==2026.7.22

# (str) p4a file blacklist: fnmatch patterns for files to LEAVE OUT of the
# APK (see above). p4a appends this file to its built-in defaults, so
# p4a-blacklist.txt only lists OUR strips. It is partly generated -- see
# .github/generate_blacklist.py -- and validated without building an APK
# by .github/strip_check.py (runs in CI).
android.blacklist_src = p4a-blacklist.txt

# (str) Presplash / icon
# (we don't ship one, so leave the defaults)
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Permissions the app needs on Android. Downloads, the database and
# logs all live in the app's private storage, so no storage permission is
# needed (and MANAGE_EXTERNAL_STORAGE must stay out -- it triggers install
# warnings and Play review for no benefit).
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# (str) Android API version to target / min
android.api = 33
android.minapi = 21

# (bool) Let Buildozer accept SDK licenses while installing real SDK packages.
# Do not pre-create a licenses-only SDK directory: it skips SDK installation.
android.accept_sdk_license = True

# (int) Target Android NDK API
android.ndk_api = 21

# (list) ABIs to build. arm64-v8a covers virtually all modern phones and
# keeps the APK minimal. Add armeabi-v7a (comma-separated) only if you need
# 32-bit-only devices -- it roughly doubles the native-code size.
android.archs = arm64-v8a

# (str) Bootstrap to use: a native WebView showing the bundled Flask app.
# The bootstrap displays a loading screen until the server on `p4a.port`
# answers, then loads the UI -- purpose-built for apps like this one.
p4a.bootstrap = webview

# (int) Port the WebView bootstrap loads (must match Config.PORT).
p4a.port = 5000

# Keep the Python/hostpython recipes (3.14.2) in sync with CI's pip constraint.
p4a.branch = master
p4a.commit = 58d21141f17c889bf8585f5665921d72028f8831

# ---------------------------------------------------------------------------
# Build settings
# ---------------------------------------------------------------------------

[buildozer]

# (int) Log level (0 = error, 1 = info, 2 = debug (default))
log_level = 2

# (int) Display warning if buildozer.conf has been modified
warn_on_sources = 1
