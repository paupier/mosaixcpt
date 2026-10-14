"""Custom exception hierarchy for the Fiix integration.

All exceptions inherit from FiixError so callers can catch the entire
package with a single except clause when needed.
"""
from __future__ import annotations


class FiixError(Exception):
    """Base exception for all Fiix integration errors."""


class FiixAuthError(FiixError):
    """Raised when authentication with the Fiix API fails.

    Covers both credential validation errors and HMAC signing failures.
    """


class FiixAPIError(FiixError):
    """Raised when the Fiix API returns an unexpected or error response.

    Attributes:
        status_code: HTTP status code returned by the API, if available.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FiixConnectionError(FiixError):
    """Raised on network-level failures when calling the Fiix API.

    Covers connection refused, DNS resolution failures, and timeouts.
    """


class FiixRateLimitError(FiixAPIError):
    """Raised when the Fiix API returns a rate-limit response (HTTP 429)."""
