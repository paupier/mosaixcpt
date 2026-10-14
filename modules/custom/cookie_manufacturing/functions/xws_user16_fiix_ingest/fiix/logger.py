"""Centralised logging factory for the Fiix integration package.

All modules obtain their logger through get_logger() so that
format and level are consistent across the entire package.

Usage::

    from fiix.logger import get_logger

    log = get_logger(__name__)
    log.info("Something happened.")
"""
from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Configure the root handler once at import time.
# If the host application has already configured logging this is a no-op.
logging.basicConfig(format=_LOG_FORMAT, datefmt=_DATE_FORMAT, level=logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger scoped to the fiix package.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
