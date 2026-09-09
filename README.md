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
