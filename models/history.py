"""History model -- a permanent record of completed (or failed) downloads."""
import time
from extensions import db


class HistoryEntry(db.Model):
    __tablename__ = "history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(512), default="Untitled")
    thumbnail = db.Column(db.String(512), default="")
    uploader = db.Column(db.String(256), default="")

    date_completed = db.Column(db.Float, default=time.time)
    duration_seconds = db.Column(db.Integer, default=0)

    format_id = db.Column(db.String(64), default="")
    quality_label = db.Column(db.String(64), default="")
    size_bytes = db.Column(db.BigInteger, default=0)

    output_path = db.Column(db.String(1024), default="")
    status = db.Column(db.String(32), default="completed")  # completed | failed

    session_id = db.Column(db.String(32), default="", index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "thumbnail": self.thumbnail,
            "uploader": self.uploader,
            "date_completed": self.date_completed,
            "duration_seconds": self.duration_seconds,
            "format_id": self.format_id,
            "quality_label": self.quality_label,
            "size_bytes": self.size_bytes,
            "output_path": self.output_path,
            "status": self.status,
        }
