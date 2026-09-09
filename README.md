# download-x

YT Downloader X Pro — a self-hosted YouTube download manager built with
Flask + yt-dlp, packaged as an Android APK via
[Buildozer](https://github.com/buildozer/buildozer) (python-for-android)
and built automatically by GitHub Actions.

The APK uses the python-for-android **`webview` bootstrap**: Android shows
a native WebView pointed at the bundled Flask server
(`http://127.0.0.1:5000`, with a loading screen until the server answers).
No Kivy / SDL stack — the UI is the same Flask templates + JS you see on
desktop.

| File / dir                      | Purpose                                                                 |
| ------------------------------- | ----------------------------------------------------------------------- |
| `main.py`                       | Android entry point. Runs the Flask server (with crash logging + auto-restart) that the WebView bootstrap displays. On desktop it also opens your browser — handy for debugging the exact code path the APK uses. |
| `config.py`                     | Central config. On Android all writable data (DB, downloads, temp, logs) goes to the app's private storage (no storage permission needed); on desktop it stays next to the source. |
| `routes/api.py`                 | JSON API + file serving the UI calls (stats, fetch, queue, tasks, direct streaming, settings, history). |
| `buildozer.spec`                | python-for-android recipe (app id, permissions, requirements, SDK levels, ABI). |
| `.github/workflows/build-apk.yml` | CI workflow that runs `buildozer android debug` and uploads the resulting `.apk` as a workflow artifact. |
| `.gitignore`                    | Excludes Buildozer build output and runtime data files.                |

## Build the APK locally

```bash
pip install buildozer cython
# On Linux, also install the apt packages listed in the workflow file.
buildozer android debug          # output -> bin/*.apk
buildozer android release        # needs a signing keystore
```

## APK size: what's inside, and how it stays small

Old builds were ~51 MB because they shipped the SDL2/Kivy engine (~20 MB)
just to show a static label, plus unused Python packages (APScheduler,
waitress, requests, Kivy). Current builds are much smaller thanks to:

* `webview` bootstrap instead of SDL2/Kivy,
* minimal `requirements = python3,flask,flask-sqlalchemy,yt-dlp`
  (only packages the code actually imports),
* a single 64-bit ABI (`android.archs = arm64-v8a`),
* never packaging the desktop `database.db` (the app creates a fresh one
  in its private storage on first launch).

What remains is mostly unavoidable for this feature set: embedded CPython
+ OpenSSL/SQLite (~10 MB), yt-dlp with all its extractors (~7 MB source),
and SQLAlchemy (~4 MB). Expect roughly **25–35 MB** for the debug APK.

Need 32-bit devices? Add the ABI (roughly doubles native size):

```ini
android.archs = arm64-v8a,armeabi-v7a
```

Every CI build writes a size breakdown to the
`downloadsx-build-report-<run number>` artifact (`apk-size.txt`), so new
bloat is easy to spot.

### Permissions

The app only requests `INTERNET` and `ACCESS_NETWORK_STATE`. Downloads,
the database and logs live in private storage, so no storage permission
(and no scary "All files access") is needed.

## If the app closes right after opening

1. Uninstall the old 0.1.x APK first if the new one refuses to install
   (version code changed from 1 to 2, so upgrades should work — but a
   clean install rules out stale-data issues).
2. Grab the crash log without root:
   ```bash
   adb logcat | grep -i "ytdlx\|python"
   adb shell run-as org.downloadsx.downloadsx cat files/ytdlx/logs/crash.log
   ```
3. `main.py` logs every uncaught exception (including in background
   threads) to `crash.log` and auto-restarts the Flask server with
   backoff, so a single failed request/download can never kill the app.

## CI

`.github/workflows/build-apk.yml` runs on every push and PR to `main`.
It:

1. Installs system + Python build dependencies on `ubuntu-latest`.
2. Caches `~/.buildozer` between runs.
3. Runs `buildozer -v android debug`.
4. Uploads the resulting `bin/*.apk` as a downloadable artifact named
   **`downloadsx-apk-<run number>`**.
5. Writes an APK size breakdown (`apk-size.txt`) into the
   `downloadsx-build-report-<run number>` artifact.
6. If the push is a `v*` tag, it also attaches the APK to a GitHub Release.

The first run downloads the Android SDK / NDK and builds all native
recipes from source, so it can take 30-60 minutes. Subsequent runs are
much faster thanks to the cache. (Switching bootstrap/ABI, like the
v0.2.0 slim-down, forces one slow rebuild.)

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
