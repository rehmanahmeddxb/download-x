"""Rotating file logger setup."""
import logging
import os
from logging.handlers import RotatingFileHandler

_configured = False


def setup_logger(log_dir: str):
    global _configured
    if _configured:
        return logging.getLogger("ytdlx")

    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("ytdlx")
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=1_000_000, backupCount=3
    )
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    _configured = True
    return logger


def get_logger():
    return logging.getLogger("ytdlx")
