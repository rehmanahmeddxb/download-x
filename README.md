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
| `config.py`                     | Central config. On Android the DB/temp/logs live in private storage while finished downloads go to the app-specific folder on shared storage (visible in file managers, no permission needed); on desktop everything stays next to the source. |
| `routes/api.py`                 | JSON API + file serving the UI calls (stats, fetch, queue, tasks, direct streaming, settings, history). |
| `buildozer.spec`                | python-for-android recipe (app id, permissions, requirements, SDK levels, ABI, file blacklist). |
| `requirements.txt`              | Pinned copy of the APK's Python closure (also what desktop dev installs). |
| `.github/workflows/build-apk.yml` | CI workflow: desktop smoke test + strip validation, then `buildozer android debug`, uploading the `.apk` as a workflow artifact. |
| `.github/smoke_test.py`         | Desktop smoke test: boots the app, verifies every `/api/*` path used by the frontend exists, and checks the API contract. Run with `python .github/smoke_test.py`. |
| `.github/strip_check.py`        | Simulates the APK packer's file strip and re-runs the whole smoke suite against the stripped tree. |
| `.github/generate_blacklist.py` | Regenerates the yt-dlp section of `p4a-blacklist.txt` from the pinned yt-dlp (`--check` fails if it drifted). |
| `p4a-blacklist.txt`             | File blacklist: unused yt-dlp extractors, test helpers and bytecode caches never packaged into the APK. |
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
* a minimal pinned closure — just flask, flask-sqlalchemy, sqlalchemy,
  typing-extensions, yt-dlp and certifi
  (only packages the code actually imports; see `requirements.txt`),
* a file blacklist (`p4a-blacklist.txt`) that drops the ~940 yt-dlp
  extractors for non-YouTube sites plus test helpers and bytecode caches
  (~33 MB uncompressed, validated by `.github/strip_check.py`),
* a single 64-bit ABI (`android.archs = arm64-v8a`),
* never packaging the desktop `database.db` (the app creates a fresh one
  in its private storage on first launch).

What remains is mostly unavoidable for this feature set: embedded CPython
+ OpenSSL/SQLite, the YouTube-relevant part of yt-dlp, and SQLAlchemy.
Expect roughly **20 MB** for the debug APK.

Note: `certifi`'s ~280 KB CA bundle is deliberately *in* the closure —
Android has no CA path Python's `ssl` module can use, so without it every
fetch and download would fail TLS verification on-device (yt-dlp prefers
certifi when installed, and `config.py` also exports `SSL_CERT_FILE` so
the stdlib urllib proxy uses it too).

Need 32-bit devices? Add the ABI (roughly doubles native size):

```ini
android.archs = arm64-v8a,armeabi-v7a
```

Every CI build writes a size breakdown to the
`downloadsx-build-report-<run number>` artifact (`apk-size.txt`), so new
bloat is easy to spot.

### Permissions

The app only requests `INTERNET` and `ACCESS_NETWORK_STATE`. The database
and logs live in private storage, while finished downloads go to the
app-specific folder on shared storage
(`Android/data/org.downloadsx.downloadsx/files/ytdlx/downloads`), which
any file manager can see — still with no storage permission (and no scary
"All files access").

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

1. Runs the desktop smoke test plus the blacklist freshness and strip
   validation (`smoke-test` job, fails fast before the slow build).
2. Installs system + Python build dependencies on `ubuntu-latest`.
3. Caches `~/.buildozer` between runs.
4. Runs `buildozer -v android debug`.
5. Uploads the resulting `bin/*.apk` as a downloadable artifact named
   **`downloadsx-apk-<run number>`**.
6. Writes an APK size breakdown (`apk-size.txt`, including red-flag
   checks for `database.db`/`__pycache__`/kivy leftovers) into the
   `downloadsx-build-report-<run number>` artifact.
7. If the push is a `v*` tag, it also attaches the APK to a GitHub Release.

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
