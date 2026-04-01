"""Logging configuration using structlog."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    log_file_max_bytes: int = 10_485_760,
    log_file_backup_count: int = 5,
) -> None:
    """Configure structlog with stdlib logging integration.

    Dev mode (DEBUG): colored, human-readable console output.
    Prod mode (INFO+): JSON output for log aggregation.

    When ``log_file`` is set, a RotatingFileHandler writes JSON logs to the
    specified path in addition to stdout. Rotation triggers at
    ``log_file_max_bytes`` (default 10 MB), keeping ``log_file_backup_count``
    (default 5) old files.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    is_dev = level <= logging.DEBUG

    # Shared processors for both structlog and stdlib
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        # Human-readable colored output for development
        console_renderer = structlog.dev.ConsoleRenderer()
    else:
        # JSON output for production log aggregation
        console_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to route through structlog
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            console_renderer,
        ],
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)

    # File handler — always JSON, with rotation
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=log_file_max_bytes,
            backupCount=log_file_backup_count,
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
