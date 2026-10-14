"""Fiix integration configuration.

Loads all credentials and runtime settings exclusively from the root .env
file.  No credential is ever hard-coded here.

Usage::

    from fiix.config import FiixConfig

    config = FiixConfig.from_env()
    print(config.base_url)

Environment variables required in .env
---------------------------------------
FIIX_SUBDOMAIN   – Your Fiix tenant subdomain (e.g. ``acme`` for acme.fiixsoftware.com)
FIIX_APP_KEY     – Application key from the Fiix integration settings
FIIX_ACCESS_KEY  – Public access key for the integration credential
FIIX_SECRET_KEY  – Secret key used for HMAC-SHA256 request signing
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .exceptions import FiixError

# Resolve and load the root-level .env exactly once at module import time.
# override=False means existing OS environment variables take precedence.
_ROOT_ENV: Path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ROOT_ENV, override=False)

_REQUIRED_VARS: tuple[str, ...] = (
    "FIIX_SUBDOMAIN",
    "FIIX_APP_KEY",
    "FIIX_ACCESS_KEY",
    "FIIX_SECRET_KEY",
)


@dataclass(frozen=True)
class FiixConfig:
    """Immutable snapshot of Fiix integration settings.

    Construct via :meth:`from_env` rather than directly to ensure all
    required variables are validated at startup.

    Attributes:
        subdomain:   Fiix tenant subdomain.
        app_key:     Registered application key.
        access_key:  Public access key for the credential.
        secret_key:  Secret key used for HMAC signing.
        timeout:     HTTP request timeout in seconds (default 60).
        max_retries: Maximum retry attempts on transient failures (default 3).
    """

    subdomain: str
    app_key: str
    access_key: str
    secret_key: str
    timeout: int = 60
    max_retries: int = 3

    @property
    def base_url(self) -> str:
        return f"https://{self.subdomain}/api/"

    @classmethod
    def from_env(cls) -> "FiixConfig":
        """Build a :class:`FiixConfig` from environment variables.

        Reads ``FIIX_SUBDOMAIN``, ``FIIX_APP_KEY``, ``FIIX_ACCESS_KEY``,
        and ``FIIX_SECRET_KEY`` from the environment (populated by the root
        ``.env`` file at module load time).

        Returns:
            Validated :class:`FiixConfig` instance.

        Raises:
            FiixError: If any required environment variable is absent or empty.
        """
        missing = [var for var in _REQUIRED_VARS if not os.getenv(var)]
        if missing:
            raise FiixError(
                f"Missing required Fiix environment variables: {', '.join(missing)}. "
                "Add them to the root .env file and retry."
            )

        return cls(
            subdomain=os.environ["FIIX_SUBDOMAIN"],
            app_key=os.environ["FIIX_APP_KEY"],
            access_key=os.environ["FIIX_ACCESS_KEY"],
            secret_key=os.environ["FIIX_SECRET_KEY"],
        )
