"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from agentic_health_hackathon.constants import SCHEMA_ID


class JsonLogFormatter(logging.Formatter):
    """Format log records as newline-delimited JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "run_id": getattr(record, "run_id", None),
            "phase": getattr(record, "phase", None),
            "schema_id": getattr(record, "schema_id", SCHEMA_ID),
            "duration": getattr(record, "duration", None),
            "status": getattr(record, "status", None),
        }
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the journal lookup logger."""
    logger = logging.getLogger("agentic_health_hackathon.journal_lookup")
    if logger.handlers:
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def new_run_id() -> str:
    """Create a stable identifier for a single CLI invocation."""
    return str(uuid.uuid4())


@contextmanager
def log_phase(
    logger: logging.Logger,
    *,
    run_id: str,
    phase: str,
    status_on_success: str = "ok",
) -> Iterator[None]:
    """Log phase lifecycle with timing metadata."""
    start = time.perf_counter()
    logger.info(
        "phase_started",
        extra={"run_id": run_id, "phase": phase, "schema_id": SCHEMA_ID, "status": "started"},
    )
    try:
        yield
    except Exception:
        duration = round(time.perf_counter() - start, 4)
        logger.exception(
            "phase_failed",
            extra={
                "run_id": run_id,
                "phase": phase,
                "schema_id": SCHEMA_ID,
                "duration": duration,
                "status": "failed",
            },
        )
        raise
    duration = round(time.perf_counter() - start, 4)
    logger.info(
        "phase_finished",
        extra={
            "run_id": run_id,
            "phase": phase,
            "schema_id": SCHEMA_ID,
            "duration": duration,
            "status": status_on_success,
        },
    )
