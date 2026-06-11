from pathlib import Path
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("mn.blueprint.business_email")
logger.setLevel(os.environ.get("MN_LOG_LEVEL", "INFO").upper())
logger.propagate = False
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    log_path = Path(os.environ.get("MN_BLUEPRINT_LOG_PATH", "/tmp/mn-business-email.log"))
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


skills_dir = Path(__file__).resolve().parent / "mn_skills"
if skills_dir.exists():
    sys.path.insert(0, str(skills_dir))

shared_skills_dir = Path(__file__).resolve().parent.parent / "_shared_skills"
if shared_skills_dir.exists():
    sys.path.insert(0, str(shared_skills_dir))
