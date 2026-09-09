"""Download (Task) model -- represents one item in the download queue."""
import uuid
import time
from extensions import db


def gen_id():
    return uuid.uuid4().hex[:12]


class Download(db.Model):
    __tablename__ = "downloads"

    id = db.Column(db.String(16), primary_key=True, default=gen_id)
    url = db.Column(db.String(512), nullable=False)
    title = db.Column(db.String(512), default="Untitled")
    thumbnail = db.Column(db.String(512), default="")
    uploader = db.Column(db.String(256), default="")

    format_id = db.Column(db.String(64), default="best")
    quality_label = db.Column(db.String(64), default="Best")

    status = db.Column(db.String(32), default="queued")
    # queued | downloading | paused | completed | failed | cancelled

    speed = db.Column(db.Float, default=0.0)          # bytes/sec
    eta_seconds = db.Column(db.Integer, default=0)
    downloaded_bytes = db.Column(db.BigInteger, default=0)
    total_bytes = db.Column(db.BigInteger, default=0)
    progress = db.Column(db.Float, default=0.0)        # 0-100

    output_file = db.Column(db.String(1024), default="")
    error_message = db.Column(db.Text, default="")

    resume_supported = db.Column(db.Boolean, default=True)
    retry_count = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer, default=0)

    pause_flag = db.Column(db.Boolean, default=False)
    cancel_flag = db.Column(db.Boolean, default=False)

    session_id = db.Column(db.String(32), default="", index=True)

    created_time = db.Column(db.Float, default=time.time)
    finished_time = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "thumbnail": self.thumbnail,
            "uploader": self.uploader,
            "format_id": self.format_id,
            "quality_label": self.quality_label,
            "status": self.status,
            "speed": self.speed,
            "eta_seconds": self.eta_seconds,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "progress": round(self.progress, 1),
            "output_file": self.output_file,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "priority": self.priority,
            "created_time": self.created_time,
            "finished_time": self.finished_time,
        }
