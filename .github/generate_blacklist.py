"""Regenerate ``p4a-blacklist.txt``.

The APK file blacklist tells python-for-android which files to leave out
of the app bundle (see ``android.blacklist_src`` in buildozer.spec).
Patterns are fnmatch globs matched against each file's full path
(``*`` crosses directory boundaries).

p4a *appends* this file to its built-in defaults
(``BLACKLIST_PATTERNS += ...`` in the packaging step), so only
DownloadSX-specific strips are listed:

* yt-dlp extractor modules for the ~940 video sites we never touch
  (the URL validator only allows YouTube) -- ~20 MB uncompressed,
* SQLAlchemy test helpers + non-SQLite dialects,
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
# Static DownloadSX additions (part 1 of the generated file).
# ---------------------------------------------------------------------------
STATIC_ADDITIONS = """# --- DownloadSX additions (hand-maintained) ---

# SQLAlchemy: test helpers + dialects we never use (SQLite only).
sqlalchemy/testing/*
sqlalchemy/dialects/mysql/*
sqlalchemy/dialects/postgresql/*
sqlalchemy/dialects/oracle/*
sqlalchemy/dialects/mssql/*

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
        "# p4a appends this file to its built-in defaults.\n\n"
        "# ================= part 1: static additions =================\n"
        + STATIC_ADDITIONS
        + "\n# ================= part 2: generated yt-dlp strip =================\n"
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
