"""History CRUD + CSV export."""
import csv
import io
from extensions import db
from models.history import HistoryEntry


def add_history_entry(**kwargs) -> HistoryEntry:
    entry = HistoryEntry(**kwargs)
    db.session.add(entry)
    db.session.commit()
    return entry


def list_history(search: str = ""):
    q = HistoryEntry.query.order_by(HistoryEntry.date_completed.desc())
    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(HistoryEntry.title.ilike(like), HistoryEntry.uploader.ilike(like))
        )
    return q.all()


def delete_history_entry(entry_id: int) -> bool:
    entry = HistoryEntry.query.get(entry_id)
    if not entry:
        return False
    db.session.delete(entry)
    db.session.commit()
    return True


def export_history_csv() -> str:
    entries = list_history()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Title", "Uploader", "Date", "Quality", "Size (bytes)", "Status", "Path"])
    for e in entries:
        writer.writerow([
            e.title, e.uploader, e.date_completed, e.quality_label,
            e.size_bytes, e.status, e.output_path,
        ])
    return buf.getvalue()
