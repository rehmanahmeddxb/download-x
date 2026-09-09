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
source.include_exts = py,png,jpg,kv,atlas,html,js,css,db

# (list) Source files to exclude
source.exclude_patterns = .git/*,.github/*,buildozer.spec,*.zip,downloads/*,temp/*,logs/*,instance/*,__pycache__/*

# (str) Application versioning (method 1)
version = 0.1.0

# (list) Application requirements (must be in p4a's recipes)
# flask, flask-sqlalchemy, apscheduler, requests and waitress are pure-Python
# and are bundled directly without needing a recipe.
requirements = python3,flask,flask-sqlalchemy,yt-dlp,apscheduler,requests,waitress,kivy

# (str) Presplash / icon
# (we don't ship one, so leave the defaults)
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (str) Permissions the app needs on Android
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,WAKE_LOCK,FOREGROUND_SERVICE

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

# (str) Android entry point - we use our main.py
android.entrypoint = org.downloadsx.downloadsx.MainActivity

# (str) Bootstrap to use
android.bootstrap = sdl2

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
