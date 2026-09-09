"""Desktop smoke test for YT Downloader X Pro.

Catches the class of bugs that ships as "the APK installs but instantly
closes / shows a dead UI":

1. import-time crashes (a missing/broken dependency kills the APK on boot
   with no error message -- here it fails loudly instead),
2. Flask app boot failures (DB migrations, settings, dispatcher),
3. dead frontend: every ``/api/*`` path referenced by ``static/js`` and
   ``templates`` must exist in the Flask url map (this is what caught the
   stub ``routes/api.py`` that only served ``/health``),
4. basic API contract checks (no real YouTube traffic).

Run locally with:  ``python .github/smoke_test.py``
"""
import os
import re
import sys

FAILURES = []


def check(name, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + name
          + ("" if condition else f" -- {detail}"))
    if not condition:
        FAILURES.append(name)


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, repo_root)
    os.chdir(repo_root)

    # Use a throwaway database so the test never touches real data.
    os.environ["YTDLX_DATABASE_URI"] = "sqlite:////tmp/smoke-test.db"
    os.environ["YTDLX_DOWNLOAD_FOLDER"] = "/tmp/smoke-downloads"
    os.environ["YTDLX_TEMP_FOLDER"] = "/tmp/smoke-temp"
    os.environ["YTDLX_LOG_DIR"] = "/tmp/smoke-logs"
    for stale in ("/tmp/smoke-test.db",):
        if os.path.exists(stale):
            os.remove(stale)

    # 1. imports (would be an instant-close on Android)
    try:
        import main as launcher  # noqa: F401  (import side effects are the test)
        from app import create_app
        check("import main + app", True)
    except Exception as exc:
        check("import main + app", False, repr(exc))
        return 1

    # 2. app boot (migrations, settings, dispatcher)
    try:
        app = create_app()
        check("create_app()", True)
    except Exception as exc:
        check("create_app()", False, repr(exc))
        return 1

    client = app.test_client()

    # 3. frontend/backend route inventory
    refs = set()
    for folder, suffix in (("static/js", ".js"), ("templates", ".html")):
        for name in os.listdir(os.path.join(repo_root, folder)):
            if not name.endswith(suffix):
                continue
            with open(os.path.join(repo_root, folder, name), encoding="utf-8") as fh:
                refs |= set(re.findall(r"/api/[A-Za-z0-9_.$/{}\-]+", fh.read()))
    rules = [str(r) for r in app.url_map.iter_rules()
             if str(r).startswith("/api")]

    def rule_to_re(rule):
        tmp = re.sub(r"<[^>]+>", "\x00", rule)
        return "^" + re.escape(tmp).replace("\x00", "[^/]+") + "$"

    uncovered = []
    for ref in sorted(refs):
        path = ref.split("?")[0].split("${")[0]
        if ref != path or path.endswith("/"):  # dynamic/prefix reference
            prefix = path.rstrip("/") + "/"
            if not any(r == path.rstrip("/") or r.startswith(prefix) for r in rules):
                uncovered.append(ref)
        elif not any(re.match(rule_to_re(r), path) for r in rules):
            uncovered.append(ref)
    check(f"JS/template /api refs covered ({len(refs)} refs, {len(rules)} routes)",
          not uncovered, f"missing: {uncovered}")

    # 4. API contract (no real downloads)
    get = client.get
    post = client.post
    check("GET /", get("/").status_code == 200)
    check("GET /api/health", get("/api/health").get_json() == {"status": "ok"})

    stats = get("/api/stats").get_json()
    check("GET /api/stats keys",
          isinstance(stats, dict) and {
              "total_downloads", "completed_downloads", "active_downloads",
              "queued_downloads", "downloaded_session_bytes", "failed_downloads",
              "total_gb_downloaded", "success_rate", "top_uploader", "top_format",
              "chart_days_labels", "chart_days_counts", "disk_used_bytes",
              "disk_free_bytes",
          } <= set(stats),
          str(sorted((stats or {}).keys())))

    check("GET /api/tasks empty", get("/api/tasks").get_json() == [])
    settings = get("/api/settings").get_json()
    check("GET /api/settings", isinstance(settings, dict) and "max_concurrent" in settings)
    check("POST /api/settings round-trip",
          post("/api/settings", json={"max_concurrent": 2}).get_json().get("max_concurrent") == 2)
    check("POST /api/settings invalid",
          post("/api/settings", json={"max_concurrent": "not-a-number"}).status_code == 200)
    check("GET /api/history empty", get("/api/history").get_json() == [])
    check("GET /api/history?scope=session",
          get("/api/history?scope=session").status_code == 200)
    check("GET /api/history/export.csv",
          get("/api/history/export.csv").status_code == 200)
    check("POST /api/fetch rejects bad URL",
          post("/api/fetch", json={"url": "junk"}).status_code == 400)
    check("POST /api/fetch_formats rejects bad URL",
          post("/api/fetch_formats", json={"url": "http://x.com/"}).status_code == 400)
    check("POST /api/queue/add rejects empty",
          post("/api/queue/add", json={"items": []}).status_code == 400)

    added = post("/api/queue/add", json={"items": [
        {"url": "https://www.youtube.com/watch?v=smoke_test_id",
         "title": "smoke", "format_id": "best", "quality_label": "Best"},
        {"url": "junk"},
    ]}).get_json()
    check("POST /api/queue/add counts", added == {"count": 1, "skipped": 1}, str(added))
    tasks = get("/api/tasks").get_json()
    tid = tasks[0]["id"] if tasks else None
    check("task queued", tid is not None)
    if tid:
        # Cancel/remove immediately so the dispatcher never starts a real
        # yt-dlp download for the fake URL.
        check("POST cancel", post(f"/api/tasks/{tid}/cancel").status_code == 200)
        check("POST retry", post(f"/api/tasks/{tid}/retry").status_code == 200)
        check("POST cancel again", post(f"/api/tasks/{tid}/cancel").status_code == 200)
        check("POST remove", post(f"/api/tasks/{tid}/remove").status_code == 200)
        check("queue empty again", get("/api/tasks").get_json() == [])
    check("POST unknown action",
          post("/api/tasks/x/explode").status_code == 400)
    check("DELETE /api/history/9999 -> 404",
          client.delete("/api/history/9999").status_code == 404)
    check("POST /api/history/9999/redownload -> 404",
          post("/api/history/9999/redownload",
               json={"url": "https://youtu.be/x"}).status_code == 404)
    check("GET /api/direct/download rejects bad URL",
          get("/api/direct/download?url=junk").status_code == 400)
    check("POST /api/contact ok",
          post("/api/contact", json={"name": "T", "email": "t@x.io",
                                      "subject": "Hi", "message": "hello"}).get_json()
          == {"ok": True})
    check("POST /api/contact validates",
          post("/api/contact", json={"name": "", "email": "bad",
                                      "message": ""}).status_code == 400)

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
