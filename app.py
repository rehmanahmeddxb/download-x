"""
YT Downloader X Pro -- entry point.

Run with:
    python app.py

Then open http://127.0.0.1:5000 in a browser on the same device.
"""
import os
from datetime import datetime
from flask import Flask
from sqlalchemy import text

from config import Config
from extensions import db
from utils.logger import setup_logger
from services.settings_service import ensure_default_settings
from services.queue_manager import queue_manager


def _ensure_columns(app):
    """Lightweight in-place migration: adds any columns that model
    definitions expect but an existing database.db predates (SQLite
    supports ALTER TABLE ADD COLUMN, so this preserves existing rows)."""
    with app.app_context():
        engine = db.engine
        with engine.connect() as conn:
            for table, column, ddl_type in (
                ("downloads", "session_id", "VARCHAR(32) DEFAULT ''"),
                ("history", "session_id", "VARCHAR(32) DEFAULT ''"),
            ):
                existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
                    conn.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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
        ensure_default_settings()
        # Resume any tasks that were mid-download when the app last closed.
        queue_manager.recover_incomplete_tasks()
        queue_manager.start(app)

    return app


app = create_app()

if __name__ == "__main__":
    # threaded=True lets the browser poll /api/tasks while downloads run
    # in their own background threads.
    app.run(host=Config.HOST, port=Config.PORT, debug=False, threaded=True)
