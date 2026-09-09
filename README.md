# download-x

YT Downloader X Pro — a self-hosted YouTube download manager built with
Flask + yt-dlp, packaged as an Android APK via
[Buildozer](https://github.com/buildozer/buildozer) (python-for-android)
and built automatically by GitHub Actions.

The Flask app inside `app.py` is identical to the upstream
**YT Downloader X Pro** project. The repository also ships:

| File / dir                      | Purpose                                                                 |
| ------------------------------- | ----------------------------------------------------------------------- |
| `main.py`                       | Android entry point. Starts Flask in a background thread and runs Kivy so the APK process stays alive. |
| `buildozer.spec`                | python-for-android recipe (app id, permissions, requirements, SDK levels). |
| `.github/workflows/build-apk.yml` | CI workflow that runs `buildozer android debug` and uploads the resulting `.apk` as a workflow artifact. |
| `.gitignore`                    | Excludes Buildozer build output and runtime data files.                |

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
