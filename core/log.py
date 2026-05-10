# core/log.py
from __future__ import annotations

import logging
import logging.handlers
import pathlib

_LOG_DIR = pathlib.Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3

_configured = False


def _setup() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    _LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. by Streamlit)

    root.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    _setup()
    return logging.getLogger(name)
