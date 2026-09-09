# download-x

YT Downloader X Pro — a self-hosted YouTube download manager built with
Flask + yt-dlp, packaged as an Android APK via
[Buildozer](https://github.com/buildozer/buildozer) (python-for-android)
and built automatically by GitHub Actions.

The Flask app inside `app.py` is identical to the upstream
**YT Downloader X Pro** project. The repository also ships:

| File / dir                      | Purpose                                                                 |
| ------------------------------- | ----------------------------------------------------------------------- |
| `main.py`                       | Android entry point. Starts the web server (waitress) in a background thread and shows a Kivy status screen (server URL, "Open in Browser", log viewer). Every startup failure is written to `logs/crash.log` and shown on screen instead of closing silently. |
| `buildozer.spec`                | python-for-android recipe (app id, permissions, requirements, SDK levels). |
| `.github/workflows/build-apk.yml` | CI workflow: runs the desktop smoke test, then `buildozer android debug` and uploads the resulting `.apk` as a workflow artifact. |
| `.github/smoke_test.py`         | Desktop smoke test: boots the app, verifies every `/api/*` path used by the frontend exists, and checks the API contract. Run with `python .github/smoke_test.py`. |
| `.gitignore`                    | Excludes Buildozer build output and runtime data files.                |

## Using the app on Android

1. Install the `downloadsx-apk-*` artifact from the latest successful
   **Build Android APK** workflow run (or build locally, below).
2. Open **YT Downloader X Pro**. The status screen shows the server URL
   (normally `http://127.0.0.1:5000`).
3. Tap **Open App in Browser** — the full download manager UI opens in
   your browser. Finished downloads land in the app's folder on shared
   storage (`Android/data/org.downloadsx.downloadsx/files/...`), visible
   in any file manager.

## Why is the APK tens of megabytes?

Short version: it ships an entire Python runtime plus the download engine.

* **Python 3.14 + stdlib + native libraries** (OpenSSL, SQLite, SDL2) —
  roughly half the APK. Every Python-for-android app pays this floor.
* **Kivy + SDL2 bootstrap** — the launcher/status screen.
* **yt-dlp** — pure Python, but ~1000 video-site extractors; the biggest
  single Python payload.
* **Flask / SQLAlchemy / waitress / requests** and the bundled web UI.

Kept small on purpose: the build targets **`arm64-v8a` only** (every
phone made since ~2016; a second 32-bit ABI would nearly double the size),
ships **no database** (a fresh one is created in private storage on first
launch), and carries **no unused dependencies**. Each CI run publishes an
**APK size report** (step summary + `apk-contents.txt` in the build report
artifact) showing exactly what takes the space.

## Build the APK locally

```bash
pip install buildozer cython
# On Linux, also install the apt packages listed in the workflow file.
buildozer android debug          # output -> bin/*.apk
buildozer android release        # needs a signing keystore
```

## CI

`.github/workflows/build-apk.yml` runs on every push and PR to `main`.
It:

1. Installs system + Python build dependencies on `ubuntu-latest`.
2. Caches `~/.buildozer` between runs.
3. Runs `buildozer -v android debug`.
4. Uploads the resulting `bin/*.apk` as a downloadable artifact named
   **`downloadsx-apk`**.
5. If the push is a `v*` tag, it also attaches the APK to a GitHub Release.

The first run downloads the Android SDK / NDK and builds all native
recipes from source, so it can take 30-60 minutes. Subsequent runs are
much faster thanks to the cache.

### Android SDK setup in CI

The workflow checks the runner's Android command-line tools and copies them into
Buildozer's SDK at `tools/bin/sdkmanager` before starting the build.
`android.accept_sdk_license = True` lets Buildozer accept license prompts while
installing SDK packages. Do not create an SDK directory containing only license
files: Buildozer treats an existing directory as an installed SDK and then fails
with `sdkmanager ... does not exist`.

The `buildozer-sdk-v3` cache namespace avoids restoring the previous incomplete
SDK setup and cross-SDK symlinks. Both Android environment variables point to
the Buildozer SDK so platform installation and discovery use the same root.
If a build fails, download the `downloadsx-build-report-<run number>`
artifact for the full Buildozer log and diagnostics.

### Native build prerequisites and pip compatibility

Install the complete apt package list in the workflow, including `automake`,
`libltdl-dev`, `cmake`, and `zlib1g-dev`. The preflight checks for the
`LT_SYS_SYMBOL_USCORE` macro used by libffi; installing `libtool` alone is not
enough.

CI uses `.github/build-constraints.txt` for Buildozer and every pip subprocess.
The pinned python-for-android revision builds CPython 3.14.2, whose bundled pip
is 25.3. Keep these versions aligned: p4a reuses its virtual environment for
both architectures, and re-running its patched ensurepip over pip 26.x can
leave mixed pip files (`ImportError: BuildDependencyInstallError`). For local
builds with this toolchain, export the same constraint before installing tools:

```bash
export PIP_CONSTRAINT="$PWD/.github/build-constraints.txt"
python -m pip install --upgrade pip buildozer cython
buildozer android debug
```

## Troubleshooting

### The app opens and immediately closes, with no error

Android kills Python-for-android apps silently when the Python code
crashes during startup, so "flash and close" always means *an exception
happened before the UI came up*. Since v0.2.0 the launcher catches that:

1. Instead of closing, the app now shows a **"Server failed to start"**
   screen with the error text. Tap **View Logs** for the full trace.
2. The same report is appended to `logs/crash.log` in the app's private
   storage (`/data/user/0/org.downloadsx.downloadsx/files/downloadsx/logs/`
   — readable via `adb`, no root needed with `adb run-as` on debug builds).
3. For the deepest detail (including native crashes), capture logcat
   while reproducing:

   ```bash
   adb logcat -c
   adb logcat | grep -iE "python|downloadsx|FATAL"
   # now launch the app on the phone
   ```

If you report a crash, include the on-screen error (screenshot) and/or the
`crash.log` contents — that pinpoints the cause immediately.

### The UI loads but buttons do nothing / stats stay empty

That means the browser can't reach the in-app server. Check the status
screen shows **"Server is running"** and that the URL matches the one in
your browser tab (`http://127.0.0.1:5000` by default). Old installs that
shipped the stub API (v0.1.0, `/health`-only) show a permanently empty UI —
update to the latest APK.

### "Cannot use folder ..." when saving settings

On Android 10+, apps can only write to their own folders without special
permissions. Leave the download folder at its default (app-specific
external storage), which always works and is visible in file managers.
