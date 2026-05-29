"""Logging setup for API and worker processes."""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )
