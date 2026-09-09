# ---------------------------------------------------------------------------
# Buildozer / python-for-android spec for YT Downloader X Pro
#
# `buildozer android debug` (or `release`) reads this file to produce an
# installable .apk. The GitHub Actions workflow in
# .github/workflows/build-apk.yml drives that build and uploads the resulting
# APK as a workflow artifact.
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
# database would leak the developer's download history into the artifact and
# resurrect stale queued tasks pointing at non-existent /storage paths.
source.include_exts = py,png,jpg,kv,atlas,html,js,css

# (list) Source files to exclude
source.exclude_patterns = .git/*,.github/*,buildozer.spec,*.zip,downloads/*,temp/*,logs/*,instance/*,__pycache__/*,*.db,*.db-journal,ci-artifacts/*

# (str) Application versioning (method 1)
version = 0.2.0

# (list) Application requirements
# flask, flask-sqlalchemy, sqlalchemy, requests and waitress are pure-Python
# and are bundled directly without needing a recipe. yt-dlp is pure-Python
# too, but large (~1000 extractor modules) -- it is the single biggest
# Python payload in the APK. kivy (with the sdl2 bootstrap below) provides
# the launcher / status screen; the app UI itself is the Flask web UI.
# Version pins mirror requirements.txt so desktop and APK behave the same.
requirements = python3,flask==3.1.3,flask-sqlalchemy==3.1.1,sqlalchemy==2.0.52,yt-dlp==2026.8.19,requests==2.34.2,waitress==3.0.2,kivy

# (str) Presplash / icon
# (we don't ship one, so leave the defaults)
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Permissions the app needs on Android
# Keep this minimal: downloads default to the app-specific external dir
# (no permission needed on Android 10+); MANAGE_EXTERNAL_STORAGE would
# trigger Play Protect warnings and needs a special Settings grant, and no
# foreground service is implemented, so both are intentionally omitted.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,WAKE_LOCK

# (list) CPU architectures to build for.
# arm64-v8a covers virtually every device made since ~2016 and keeps the
# APK roughly HALF the size of a fat (arm64 + armeabi-v7a) build, because
# every native library (Python, SDL2, Kivy, OpenSSL, SQLite, ...) is
# shipped once instead of twice. Only add armeabi-v7a back if you must
# support 32-bit-only phones -- expect the APK to roughly double in size.
android.archs = arm64-v8a

# (str) Android API version to target / min
android.api = 33
android.minapi = 21

# (bool) Let Buildozer accept SDK licenses while installing real SDK packages.
# Do not pre-create a licenses-only SDK directory: it skips SDK installation.
android.accept_sdk_license = True

# (int) Target Android SDK
android.ndk_api = 21

# (bool) Use legacy build (may be needed on older p4a versions)
# android.use_legacy_build = True

# (str) Java activity supplied by the SDL2 bootstrap (Python starts in main.py).
android.entrypoint = org.kivy.android.PythonActivity

# (str) Bootstrap to use
p4a.bootstrap = sdl2

# Keep the Python/hostpython recipes (3.14.2) in sync with CI's pip constraint.
p4a.branch = master
p4a.commit = 58d21141f17c889bf8585f5665921d72028f8831

# (list) Android additional libraries
# p4a.archives =
# p4a.bootstrap =

# ---------------------------------------------------------------------------
# Build settings
# ---------------------------------------------------------------------------

[buildozer]

# (int) Log level (0 = error, 1 = info, 2 = debug (default))
log_level = 2

# (int) Display warning if buildozer.conf has been modified
warn_on_sources = 1
