"""
YT Downloader X Pro -- entry point.

Run with:
    python app.py

Then open http://127.0.0.1:5000 in a browser on the same device.

NOTE: this module intentionally has no import-time side effects besides
logging setup helpers, so the Android entry point (main.py) can import
`create_app` without booting the whole stack twice.
"""
import os
import uuid
from datetime import datetime
from flask import Flask
from sqlalchemy import text

from config import Config
from extensions import db
from utils.logger import setup_logger
from services.settings_service import ensure_default_settings
from services.queue_manager import queue_manager


def _ensure_columns(app):
    """Lightweight in-place migration: adds any columns that the model
    definitions expect but an existing database predates (SQLite supports
    ALTER TABLE ADD COLUMN, so this preserves existing rows). Never raises:
    a failed migration must not prevent the app from booting."""
    import logging

    log = logging.getLogger("ytdlx")
    with app.app_context():
        engine = db.engine
        with engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            }
            for model in db.Model.__subclasses__():
                table = model.__table__
                if table.name not in tables:
                    continue
                existing = {
                    row[1]
                    for row in conn.execute(text(f"PRAGMA table_info({table.name})"))
                }
                for column in table.columns:
                    if column.name in existing or column.primary_key:
                        continue
                    try:
                        ddl_type = column.type.compile(dialect=engine.dialect)
                        conn.execute(
                            text(
                                f"ALTER TABLE {table.name} "
                                f"ADD COLUMN {column.name} {ddl_type}"
                            )
                        )
                        conn.commit()
                    except Exception as exc:
                        log.warning(
                            "migration skipped (%s.%s): %s",
                            table.name, column.name, exc,
                        )


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Unique id for this process lifetime. New downloads / history rows are
    # tagged with it so the dashboard can show "this session" stats.
    app.config["SESSION_ID"] = uuid.uuid4().hex[:12]

    os.makedirs(Config.DEFAULT_DOWNLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.DEFAULT_TEMP_FOLDER, exist_ok=True)
    os.makedirs(Config.LOG_DIR, exist_ok=True)

    setup_logger(Config.LOG_DIR)

    db.init_app(app)

    from routes.home import home_bp
    from routes.api import api_bp
    app.register_blueprint(home_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Inject the current year into every template (used by the footer).
    @app.context_processor
    def _inject_now_year():
        return {"now_year": datetime.utcnow().year}

    with app.app_context():
        db.create_all()
        _ensure_columns(app)
        settings = ensure_default_settings()
        if settings.auto_resume:
            # Resume any tasks that were mid-download when the app last closed.
            queue_manager.recover_incomplete_tasks()
        else:
            queue_manager.mark_incomplete_paused()
        queue_manager.start(app)

    return app


def run_server(flask_app):
    """Serve `flask_app`, blocking the current thread.

    The Flask dev server (threaded) is all a loopback server needs, so no
    production WSGI container is bundled (keeps the APK smaller).
    """
    host = flask_app.config.get("HOST", Config.HOST)
    port = int(flask_app.config.get("PORT", Config.PORT))
    # threaded=True lets the browser poll /api/tasks while downloads run
    # in their own background threads.
    flask_app.run(host=host, port=port, debug=False, threaded=True,
                  use_reloader=False)


if __name__ == "__main__":
    run_server(create_app())
