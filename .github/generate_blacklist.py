"""Regenerate ``p4a-blacklist.txt``.

The APK file blacklist tells python-for-android which files to leave out
of the app bundle (see ``android.blacklist_src`` in buildozer.spec).
Patterns are fnmatch globs matched against each file's full path
(``*`` crosses directory boundaries).

Because a custom blacklist file REPLACES the bootstrap's default list,
this script embeds that default list verbatim (source: the pinned p4a
commit in buildozer.spec, ``_sdl_common/build/blacklist.txt``) and then
appends DownloadSX-specific strips:

* yt-dlp extractor modules for the ~940 video sites we never touch
  (the URL validator only allows YouTube) -- ~20 MB uncompressed,
* SQLAlchemy test helpers + non-SQLite dialects,
* Kivy dev modules, chardet (unused; requests works without it),
* ``__pycache__`` (rebuilt on device) and ``.pyi`` stubs.

The yt-dlp section is generated from the INSTALLED yt-dlp, which must
match the pinned version in requirements.txt, otherwise the script fails.
CI enforces this via ``--check`` so the committed file can't drift.

Usage:
    python .github/generate_blacklist.py          # rewrite p4a-blacklist.txt
    python .github/generate_blacklist.py --check  # fail if it differs
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "p4a-blacklist.txt")

# ---------------------------------------------------------------------------
# Part 1: bootstrap defaults, verbatim from the pinned p4a commit.
# Source:
#   pythonforandroid/bootstraps/_sdl_common/build/blacklist.txt
# at p4a.commit in buildozer.spec. If the pin moves, re-copy this section
# from the new commit.
# ---------------------------------------------------------------------------
BOOTSTRAP_DEFAULTS = """# prevent user to include invalid extensions
*.apk
*.aab
*.apks
*.pxd

# eggs
*.egg-info

# unit test
unittest/*

# python config
config/makesetup

# unused kivy files (platform specific)
kivy/input/providers/wm_*
kivy/input/providers/mactouch*
kivy/input/providers/probesysfs*
kivy/input/providers/mtdev*
kivy/input/providers/hidinput*
kivy/core/camera/camera_videocapture*
kivy/core/spelling/*osx*
kivy/core/video/video_pyglet*
kivy/tools
kivy/tests/*
kivy/*/*.h
kivy/*/*.pxi

# unused encodings
lib-dynload/*codec*
encodings/cp*.pyo
encodings/tis*
encodings/shift*
encodings/bz2*
encodings/iso*
encodings/undefined*
encodings/johab*
encodings/p*
encodings/m*
encodings/euc*
encodings/k*
encodings/unicode_internal*
encodings/quo*
encodings/gb*
encodings/big5*
encodings/hp*
encodings/hz*

# unused python modules
bsddb/*
wsgiref/*
hotshot/*
pydoc_data/*
tty.pyo
anydbm.pyo
nturl2path.pyo
LICENCE.txt
macurl2path.pyo
dummy_threading.pyo
audiodev.pyo
antigravity.pyo
dumbdbm.pyo
sndhdr.pyo
__phello__.foo.pyo
sunaudio.pyo
os2emxpath.pyo
multiprocessing/dummy*

# unused binaries python modules
lib-dynload/termios.so
lib-dynload/_lsprof.so
lib-dynload/*audioop.so
lib-dynload/_hotshot.so
lib-dynload/_heapq.so
lib-dynload/_json.so
lib-dynload/grp.so
lib-dynload/resource.so
lib-dynload/pyexpat.so
lib-dynload/_ctypes_test.so
lib-dynload/_testcapi.so

# odd files
plat-linux3/regen
"""

# ---------------------------------------------------------------------------
# Part 2: static DownloadSX additions.
# ---------------------------------------------------------------------------
STATIC_ADDITIONS = """# --- DownloadSX additions (hand-maintained) ---

# SQLAlchemy: test helpers + dialects we never use (SQLite only).
sqlalchemy/testing/*
sqlalchemy/dialects/mysql/*
sqlalchemy/dialects/postgresql/*
sqlalchemy/dialects/oracle/*
sqlalchemy/dialects/mssql/*

# Kivy developer modules (inspector/recorder/...) -- never activated.
# NOTE: kivy/__init__.py unconditionally does
# `from kivy.modules import Modules`, so the package __init__ must stay;
# list the dev modules explicitly instead of blacklisting the directory.
kivy/modules/_webdebugger.py
kivy/modules/console.py
kivy/modules/cursor.py
kivy/modules/inspector.py
kivy/modules/joycursor.py
kivy/modules/keybinding.py
kivy/modules/monitor.py
kivy/modules/recorder.py
kivy/modules/screen.py
kivy/modules/showborder.py
kivy/modules/touchring.py
kivy/modules/webdebugger.py

# chardet is pulled in by the kivy recipe but nothing uses it
# (requests falls back cleanly when it is absent).
chardet/*

# Bytecode caches are rebuilt on first import; stubs are never imported.
__pycache__/*
*.pyi
"""

# yt-dlp extractor files we KEEP. Everything else under
# yt_dlp/extractor/ is one pattern per file below. The app only accepts
# YouTube URLs, and the youtube/ subpackage is self-contained (it only
# imports extractor/common, yt_dlp/utils and yt_dlp/networking).
YTDLP_KEEP = {
    "__init__.py",
    "_extractors.py",  # eager registry; runtime uses lazy_extractors instead,
    # but keep it as the fallback path (tiny, and strip_check proves it is
    # never imported when lazy mode is active)
    "extractors.py",  # lazy registry (generated file in recent versions)
    "lazy_extractors.py",  # lazy class lookup (generated file)
    "common.py",
    "commonmistakes.py",
    "commonprotocols.py",
    "generic.py",
    "genericembeds.py",
    # Imported at module top-level by non-extractor code (found by audit):
    "openload.py",  # YoutubeDL.py: PhantomJSwrapper
    "afreecatv.py",  # downloader/soop.py: _cloudfront_auth_request
    "adobepass.py",  # yt_dlp/__init__.py: MSO_INFO
    "youtube",  # whole subpackage directory
}


def pinned_ytdlp_version():
    for line in open(os.path.join(REPO_ROOT, "requirements.txt"), encoding="utf-8"):
        line = line.strip()
        if line.lower().startswith("yt-dlp=="):
            return line.split("==", 1)[1]
    raise SystemExit("yt-dlp pin not found in requirements.txt")


def generate():
    import yt_dlp

    pinned = pinned_ytdlp_version()
    installed = yt_dlp.version.__version__

    def _norm(ver):
        # Compare numerically per segment so 2026.08.19 == 2026.8.19.
        parts = []
        for chunk in ver.split("."):
            parts.append(int(chunk) if chunk.isdigit() else chunk)
        return parts

    if _norm(installed) != _norm(pinned):
        raise SystemExit(
            f"installed yt-dlp {installed} != pinned {pinned}; "
            f"`pip install -r requirements.txt` first"
        )
    extractor_dir = os.path.join(os.path.dirname(yt_dlp.__file__), "extractor")
    names = sorted(os.listdir(extractor_dir))
    if "youtube" not in names or "common.py" not in names:
        raise SystemExit(f"unexpected yt-dlp layout in {extractor_dir}")

    patterns = []
    for name in names:
        if name in YTDLP_KEEP or name == "__pycache__":
            continue
        full = os.path.join(extractor_dir, name)
        if os.path.isdir(full):
            patterns.append(f"yt_dlp/extractor/{name}/*")
        else:
            patterns.append(f"yt_dlp/extractor/{name}")

    header = (
        "# --- DownloadSX additions (GENERATED -- do not edit by hand) ---\n"
        f"# yt-dlp {pinned}: strip every extractor module except the YouTube\n"
        "# stack. Regenerate with: python .github/generate_blacklist.py\n"
    )
    return (
        "# p4a APK file blacklist (android.blacklist_src in buildozer.spec).\n"
        "#\n"
        "# A custom file REPLACES the bootstrap default list, so part 1\n"
        "# below is that default list, copied verbatim. Parts 2-3 are ours.\n\n"
        "# ================= part 1: bootstrap defaults =================\n"
        + BOOTSTRAP_DEFAULTS
        + "\n# ================= part 2: static additions =================\n"
        + STATIC_ADDITIONS
        + "\n# ================= part 3: generated yt-dlp strip =================\n"
        + header
        + "".join(p + "\n" for p in patterns)
    )


def main():
    check = len(sys.argv) > 1 and sys.argv[1] == "--check"
    content = generate()
    if check:
        current = open(OUT_PATH, encoding="utf-8").read() if os.path.exists(OUT_PATH) else ""
        if current != content:
            print("FAIL: p4a-blacklist.txt is out of date; run python .github/generate_blacklist.py")
            return 1
        print(f"OK: p4a-blacklist.txt matches generator "
              f"({content.count(chr(10))} lines)")
        return 0
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
