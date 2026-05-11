import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(os.environ.get("MN_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    log_path = Path(
        os.environ.get("MN_BLUEPRINT_LOG_PATH", "/tmp/mn-drug-discovery.log")
    )
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=int(os.environ.get("MN_LOG_MAX_BYTES", "1048576")),
            backupCount=int(os.environ.get("MN_LOG_BACKUP_COUNT", "5")),
        )
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
