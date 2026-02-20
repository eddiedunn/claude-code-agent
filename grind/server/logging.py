"""Structured logging configuration."""
import json
import logging
import sys
from typing import Any

class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def get_logger(name: str, structured: bool = False) -> logging.Logger:
    """Get a logger with grind.server prefix.

    Args:
        name: Logger name (will be prefixed with grind.server)
        structured: If True, use JSON structured logging
    """
    logger = logging.getLogger(f"grind.server.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if structured:
            handler.setFormatter(StructuredFormatter())
        else:
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

class LogContext:
    """Context manager for adding structured fields to logs."""

    def __init__(self, logger: logging.Logger, **fields: Any):
        self.logger = logger
        self.fields = fields
        self.old_factory = logging.getLogRecordFactory()

    def __enter__(self) -> logging.Logger:
        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = self.old_factory(*args, **kwargs)
            for key, value in self.fields.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self.logger

    def __exit__(self, *args: Any) -> None:
        logging.setLogRecordFactory(self.old_factory)
