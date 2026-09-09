"""Settings CRUD -- a single-row table holding all user preferences."""
from extensions import db
from models.settings import SettingsRecord
from config import Config


def ensure_default_settings():
    """Called once at startup: create the settings row if it doesn't exist."""
    row = SettingsRecord.query.get(1)
    if row is None:
        row = SettingsRecord(
            id=1,
            download_folder=Config.DEFAULT_DOWNLOAD_FOLDER,
            temp_folder=Config.DEFAULT_TEMP_FOLDER,
            max_concurrent=Config.DEFAULT_MAX_CONCURRENT,
            concurrent_fragments=Config.DEFAULT_CONCURRENT_FRAGMENTS,
            max_retries=Config.DEFAULT_MAX_RETRIES,
        )
        db.session.add(row)
        db.session.commit()
    return row


def get_settings() -> SettingsRecord:
    row = SettingsRecord.query.get(1)
    if row is None:
        row = ensure_default_settings()
    return row


def update_settings(data: dict) -> SettingsRecord:
    row = get_settings()
    bool_fields = {
        "auto_resume", "embed_metadata", "embed_thumbnail",
        "embed_subtitles", "sponsorblock",
    }
    int_fields = {"max_concurrent", "concurrent_fragments", "max_retries", "speed_limit_kbps"}

    for key, value in data.items():
        if not hasattr(row, key):
            continue
        if key in bool_fields:
            value = bool(value) and str(value).lower() not in ("false", "0", "")
        elif key in int_fields:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        setattr(row, key, value)

    db.session.commit()
    return row
