"""Settings model -- a single row holding all user-configurable options."""
from extensions import db


class SettingsRecord(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True, default=1)

    download_folder = db.Column(db.String(1024), default="")
    temp_folder = db.Column(db.String(1024), default="")
    filename_template = db.Column(db.String(256), default="%(title)s.%(ext)s")

    max_concurrent = db.Column(db.Integer, default=3)
    concurrent_fragments = db.Column(db.Integer, default=8)
    max_retries = db.Column(db.Integer, default=3)
    auto_resume = db.Column(db.Boolean, default=True)
    speed_limit_kbps = db.Column(db.Integer, default=0)  # 0 = unlimited

    default_quality = db.Column(db.String(32), default="best")
    theme = db.Column(db.String(32), default="dark")
    language = db.Column(db.String(16), default="en")

    proxy = db.Column(db.String(256), default="")
    cookies_path = db.Column(db.String(1024), default="")
    ffmpeg_path = db.Column(db.String(1024), default="")

    embed_metadata = db.Column(db.Boolean, default=False)
    embed_thumbnail = db.Column(db.Boolean, default=False)
    embed_subtitles = db.Column(db.Boolean, default=False)
    sponsorblock = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
