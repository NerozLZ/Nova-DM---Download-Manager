"""Configuração de logging com remoção de segredos."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    (re.compile(r"token:[^\s'\"]+", re.IGNORECASE), "token:***"),
    (re.compile(r"(rpc-secret=)[^\s'\"]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(authorization:\s*)[^\r\n]+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(cookie:\s*)[^\r\n]+", re.IGNORECASE), r"\1***"),
    (
        re.compile(
            r"((?:password|passwd|token|secret|apikey|api_key|access_token)=)[^&\s'\"]+",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
    (re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE), r"\1***:***@"),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("nova_dm")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        log_dir / "nova-dm.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(fmt)
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
    logger.propagate = False
