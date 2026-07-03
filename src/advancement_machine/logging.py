import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .config import ConfigManager

class CorrelationFilter(logging.Filter):
    def __init__(self, correlation_id: str = ""):
        super().__init__()
        self._cid = correlation_id or str(uuid.uuid4())[:8]

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self._cid
        return True

class RedactFilter(logging.Filter):
    SENSITIVE_PATTERNS = [
        ("password", "***"), ("secret", "***"), ("token", "***"),
        ("api_key", "***"), ("authorization", "***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            if pattern in msg.lower():
                record.msg = msg.replace(msg, f"[{pattern} redacted]")
                break
        return True

def setup_logging() -> logging.Logger:
    from . import __app_name__
    cfg = ConfigManager.get()
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(__app_name__)
    logger.setLevel(cfg.log_level.upper())
    logger.addFilter(RedactFilter())

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(cfg.log_level.upper())
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(correlation_id)s] %(levelname)s %(message)s"
    ))
    console.addFilter(CorrelationFilter())
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "advancement.log", maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(correlation_id)s] %(name)s %(levelname)s %(module)s:%(lineno)d | %(message)s"
    ))
    file_handler.addFilter(CorrelationFilter())
    logger.addHandler(file_handler)

    return logger