"""Shared extension instances. Kept in their own module so both app.py and
the models/ package can import `db` without circular-import problems."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
