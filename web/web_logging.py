"""Logging setup for the web layer. Call setup_web_logging() once at app startup."""

import logging
import os
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / 'logs' / 'web'
MAX_LOG_FILES = 10


def setup_web_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _prune_old_logs()

    timestamp = datetime.now().strftime('%Y-%m-%d_%H_%M_%S')
    log_file = LOGS_DIR / f'{timestamp}_WebGame_Log.log'

    fmt = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                            datefmt='%H:%M:%S')

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    logger = logging.getLogger('liars_dice')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False


def _prune_old_logs() -> None:
    logs = sorted(LOGS_DIR.glob('*_WebGame_Log.log'), key=lambda p: p.stat().st_mtime)
    # keep MAX_LOG_FILES - 1 to leave room for the new file being created now
    for old in logs[:max(0, len(logs) - (MAX_LOG_FILES - 1))]:
        old.unlink()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f'liars_dice.{name}')
