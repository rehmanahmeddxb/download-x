import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = "change-this-secret-in-production"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEFAULT_DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")
    DEFAULT_TEMP_FOLDER = os.path.join(BASE_DIR, "temp")
    LOG_DIR = os.path.join(BASE_DIR, "logs")

    DEFAULT_MAX_CONCURRENT = 3
    DEFAULT_CONCURRENT_FRAGMENTS = 8
    DEFAULT_MAX_RETRIES = 3

    HOST = "0.0.0.0"
    PORT = 5000
