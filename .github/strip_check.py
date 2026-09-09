"""Validate ``p4a-blacklist.txt`` without building an APK.

Simulates exactly what python-for-android's ``make_tar`` does with the
blacklist (same fnmatch semantics: every pattern implicitly matches
``*/<pattern>`` against each file's full path, ``*`` crosses directories):

1. copies this venv's site-packages (hardlinks, so instant),
2. deletes every file the blacklist matches, like the APK packer would,
3. asserts the runtime keep-set survived,
4. re-runs the FULL ``smoke_test.py`` with the stripped tree shadowing
   the real site-packages -- if the strip breaks any import the app (or
   yt-dlp/SQLAlchemy/Kivy) needs, this fails here instead of shipping a
   40-minute APK that crashes on launch.

Run locally with:  ``python .github/strip_check.py``
"""
import fnmatch
import os
import re
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLACKLIST = os.path.join(REPO_ROOT, "p4a-blacklist.txt")
STRIPPED = "/tmp/strip-sp"
STRIPPED_SCOPE = "/tmp/strip-scope"

# Top-level site-packages entries that actually ship in the APK:
# requirements.txt plus the flask recipe's python_depends
# (jinja2/werkzeug/markupsafe/itsdangerous/click/blinker). Everything else
# in a dev venv (pip, setuptools, greenlet, ...) is ignored so the report
# and the probes mirror the APK bundle instead of the workstation.
APK_TOP_LEVELS = {
    "flask", "flask_sqlalchemy", "sqlalchemy", "typing_extensions.py",
    "yt_dlp", "certifi",
    "jinja2", "werkzeug", "markupsafe", "itsdangerous", "click", "blinker",
}

# Files that MUST survive the strip (relative to site-packages).
MUST_KEEP = [
    # Flask stack
    "flask/__init__.py",
    "flask_sqlalchemy/__init__.py",
    "sqlalchemy/__init__.py",
    "sqlalchemy/orm/__init__.py",
    "sqlalchemy/dialects/sqlite/__init__.py",
    "sqlalchemy/engine/__init__.py",
    "typing_extensions.py",
    "werkzeug/__init__.py",
    "jinja2/__init__.py",
    "markupsafe/__init__.py",
    "itsdangerous/__init__.py",
    "click/__init__.py",
    "blinker/__init__.py",
    # Downloader engine
    "yt_dlp/__init__.py",
    "yt_dlp/YoutubeDL.py",
    "yt_dlp/extractor/__init__.py",
    "yt_dlp/extractor/common.py",
    "yt_dlp/extractor/generic.py",
    "yt_dlp/extractor/youtube/__init__.py",
    "yt_dlp/extractor/youtube/_video.py",
    "yt_dlp/utils/__init__.py",
    "yt_dlp/networking/__init__.py",
    "yt_dlp/downloader/__init__.py",
    # TLS CA bundle (yt-dlp loads certifi.where() when present)
    "certifi/__init__.py",
    "certifi/cacert.pem",
]

# Import probes executed with ONLY the stripped tree visible (plus stdlib).
# Each is `module` or `module:attr` that must import cleanly.
IMPORT_PROBES = [
    "flask",
    "flask_sqlalchemy",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.dialects.sqlite",
    "typing_extensions",
    "yt_dlp",
    "certifi",
]


def load_patterns():
    patterns = []
    for line in open(BLACKLIST, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_blacklisted(patterns, full_path):
    # Exact replica of p4a's match_filename().
    for pattern in patterns:
        if pattern.startswith("^"):
            pattern = pattern[1:]
        else:
            pattern = "*/" + pattern
        if fnmatch.fnmatch(full_path, pattern):
            return True
    return False


def site_packages_dir():
    for path in sys.path:
        if path.endswith("site-packages") and os.path.isdir(path):
            return path
    raise SystemExit("could not locate site-packages on sys.path")


def main():
    failures = []
    src = site_packages_dir()
    print(f"site-packages: {src}")
    patterns = load_patterns()
    print(f"blacklist patterns: {len(patterns)}")

    # Pre-check: the validation needs the full closure installed.
    expected = ["flask", "flask_sqlalchemy", "sqlalchemy", "yt_dlp",
                "certifi"]
    missing_pkgs = [p for p in expected
                    if not os.path.exists(os.path.join(src, p))]
    if missing_pkgs:
        print(f"FAIL: install the full closure first, missing: {missing_pkgs}\n"
              f"  pip install -r requirements.txt")
        return 1

    # 1+2. copy (hardlinks) + strip
    if os.path.exists(STRIPPED):
        shutil.rmtree(STRIPPED)

    def _link_or_copy(src_file, dst_file):
        try:
            os.link(src_file, dst_file)
        except OSError:
            shutil.copy2(src_file, dst_file)

    shutil.copytree(src, STRIPPED, copy_function=_link_or_copy,
                    ignore_dangling_symlinks=True)
    removed_files, removed_bytes = 0, 0
    removed_by_topdir: dict[str, int] = {}
    for top in sorted(APK_TOP_LEVELS):
        top_path = os.path.join(STRIPPED, top)
        if os.path.isfile(top_path):
            candidates = [top_path]
        elif os.path.isdir(top_path):
            candidates = [
                os.path.join(root, name)
                for root, _dirs, files in os.walk(top_path)
                for name in files
            ]
        else:
            continue
        for full in candidates:
            if is_blacklisted(patterns, full):
                removed_bytes += os.path.getsize(full)
                removed_by_topdir[top] = removed_by_topdir.get(top, 0) + 1
                removed_files += 1
                os.remove(full)
    print(f"stripped {removed_files} APK files "
          f"({removed_bytes / 1024 / 1024:.1f} MB uncompressed):")
    for top, count in sorted(removed_by_topdir.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {top}")

    # Probe tree exposing ONLY the APK closure (symlinked, instant).
    if os.path.exists(STRIPPED_SCOPE):
        shutil.rmtree(STRIPPED_SCOPE)
    os.makedirs(STRIPPED_SCOPE)
    for top in sorted(APK_TOP_LEVELS):
        src_top = os.path.join(STRIPPED, top)
        if os.path.exists(src_top):
            os.symlink(src_top, os.path.join(STRIPPED_SCOPE, top))
    # ...plus their dist-info (pip installs wheels with metadata intact and
    # nothing in the chain strips it; flask's own test client needs
    # importlib.metadata.version("werkzeug")).
    dist_names = {"flask", "flask-sqlalchemy", "sqlalchemy",
                  "typing-extensions", "yt-dlp", "certifi",
                  "jinja2", "werkzeug", "markupsafe", "itsdangerous",
                  "click", "blinker"}
    for entry in os.listdir(STRIPPED):
        if not entry.endswith(".dist-info"):
            continue
        canon = re.sub(r"[-_.]+", "-", entry[:-len(".dist-info")]).lower()
        canon = re.sub(r"-\d.*$", "", canon)  # drop -<version>
        if canon in dist_names:
            os.symlink(os.path.join(STRIPPED, entry),
                       os.path.join(STRIPPED_SCOPE, entry))

    def check(name, condition, detail=""):
        print(("PASS " if condition else "FAIL ") + name
              + ("" if condition else f" -- {detail}"))
        if not condition:
            failures.append(name)

    # 3. keep-set
    missing = [rel for rel in MUST_KEEP
               if not os.path.exists(os.path.join(STRIPPED, rel))]
    check(f"keep-set survives ({len(MUST_KEEP)} files)", not missing,
          f"stripped: {missing}")

    # Spot-check that the big strips actually fired. (Empty directories
    # remain -- like p4a's make_tar, we only delete files -- so count files.)
    def files_left(rel):
        root = os.path.join(STRIPPED, rel)
        if not os.path.exists(root):
            return []
        out = []
        for _r, _d, files in os.walk(root):
            out.extend(files)
        return out

    remaining_extractors = sorted(
        f for f in os.listdir(os.path.join(STRIPPED, "yt_dlp", "extractor"))
        if f.endswith(".py")
    )
    expected_extractors = sorted([
        "__init__.py", "_extractors.py", "extractors.py",
        "lazy_extractors.py", "common.py", "commonmistakes.py",
        "commonprotocols.py", "generic.py", "genericembeds.py",
        "openload.py", "afreecatv.py", "adobepass.py",
    ])
    check("yt-dlp extractors stripped to YouTube stack",
          remaining_extractors == expected_extractors,
          str(remaining_extractors))
    check("sqlalchemy testing stripped",
          not files_left(os.path.join("sqlalchemy", "testing")))
    check("sqlalchemy mysql dialect stripped",
          not files_left(os.path.join("sqlalchemy", "dialects", "mysql")))
    check("sqlalchemy sqlite dialect kept",
          bool(files_left(os.path.join("sqlalchemy", "dialects", "sqlite"))))
    check("certifi CA bundle kept",
          os.path.exists(os.path.join(STRIPPED, "certifi", "cacert.pem")))

    if failures:
        print(f"\n{len(failures)} failure(s) before import probes -- aborting")
        return 1

    # 4. import probes against the stripped tree only
    probe_code = (
        "import sys; "
        f"sys.path = {[STRIPPED_SCOPE]} + [p for p in sys.path "
        "if 'site-packages' not in p and 'dist-packages' not in p]; "
        "import importlib; "
        f"[importlib.import_module(m.split(':')[0]) for m in {IMPORT_PROBES!r}]; "
        "print('all import probes ok')"
    )
    proc = subprocess.run([sys.executable, "-c", probe_code], capture_output=True,
                          text=True, cwd=REPO_ROOT)
    check("import probes on stripped tree", proc.returncode == 0,
          (proc.stderr or proc.stdout)[-2000:])
    if proc.returncode != 0:
        return 1

    # 5. functional probes: sqlite engine, youtube extractor resolution
    func_code = (
        "import sys; "
        f"sys.path = {[STRIPPED_SCOPE]} + [p for p in sys.path "
        "if 'site-packages' not in p and 'dist-packages' not in p]; "
        "from sqlalchemy import create_engine, text; "
        "e = create_engine('sqlite://'); "
        "e.connect().execute(text('select 1')); "
        "from yt_dlp import YoutubeDL; "
        "ydl = YoutubeDL({'quiet': True, 'no_warnings': True}); "
        "ie = ydl.get_info_extractor('Youtube'); "
        "assert ie is not None and ie.ie_key() == 'Youtube', ie; "
        "from yt_dlp.dependencies import certifi; "
        "assert certifi is not None, 'yt-dlp cannot see certifi (TLS would fail on Android)'; "
        "print('functional probes ok:', type(ie).__name__)"
    )
    proc = subprocess.run([sys.executable, "-c", func_code], capture_output=True,
                          text=True, cwd=REPO_ROOT)
    check("sqlite engine + youtube extractor resolve", proc.returncode == 0,
          (proc.stderr or proc.stdout)[-2000:])
    if proc.returncode != 0:
        return 1

    # 6. the whole smoke suite with the stripped tree shadowing site-packages
    env = dict(os.environ)
    env["PYTHONPATH"] = STRIPPED_SCOPE + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # -S skips the real site-packages: only the stdlib + the scope tree
    # (PYTHONPATH) are importable, exactly like the APK bundle.
    proc = subprocess.run([sys.executable, "-S", ".github/smoke_test.py"],
                          capture_output=True, text=True, cwd=REPO_ROOT, env=env)
    print("----- smoke_test.py under stripped tree -----")
    print(proc.stdout[-3000:])
    if proc.stderr:
        print(proc.stderr[-1500:])
    check("full smoke suite passes on stripped tree", proc.returncode == 0)

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
