"""Low-level HTTP client for the Fiix API.

Responsibilities
----------------
- Manage the ``requests.Session`` lifecycle.
- Attach a retry adapter (exponential back-off) for transient failures.
- Sign every outbound request via :class:`~fiix.auth.FiixAuth`.
- Translate HTTP / JSON errors into typed :mod:`fiix.exceptions` subclasses.

Business logic (which endpoints to call, what to do with responses) belongs
in dedicated modules such as ``workorders.py``.

Usage::

    from fiix.config import FiixConfig
    from fiix.client import FiixClient

    config = FiixConfig.from_env()
    with FiixClient(config) as client:
        body = client.post({"_maCn": "WorkOrder.find", "fields": [...], ...})
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Suppress SSL warnings produced by verify=False on every request.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .auth import FiixAuth
from .config import FiixConfig
from .exceptions import (
    FiixAPIError,
    FiixAuthError,
    FiixConnectionError,
    FiixRateLimitError,
)
from .logger import get_logger

log = get_logger(__name__)

# Fiix API client version — required in every request payload.
# Matches the version used in the validated Postman collection.
_CLIENT_VERSION: dict[str, int] = {"major": 2, "minor": 8, "patch": 1}

# HTTP status codes that should trigger an automatic retry.
_RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


def _build_retry_adapter(max_retries: int) -> HTTPAdapter:
    """Create an :class:`HTTPAdapter` with exponential back-off retry logic.

    Retries are attempted on the status codes in ``_RETRY_STATUS_CODES``.
    The back-off formula is ``{backoff_factor} * (2 ** (attempt - 1))``
    seconds, so with ``backoff_factor=1`` the delays are 0 s, 2 s, 4 s, …

    Args:
        max_retries: Maximum number of retry attempts per request.

    Returns:
        Configured :class:`HTTPAdapter`.
    """
    retry = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=list(_RETRY_STATUS_CODES),
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry)


class FiixClient:
    """Thread-safe Fiix API HTTP client.

    Must be used as a context manager so that the underlying
    ``requests.Session`` is always properly closed::

        with FiixClient(config) as client:
            response = client.post(request_payload)

    Args:
        config: Fully validated :class:`~fiix.config.FiixConfig` instance.

    Attributes:
        config: The :class:`~fiix.config.FiixConfig` used by this client.
    """

    def __init__(self, config: FiixConfig) -> None:
        self.config = config
        self._auth = FiixAuth(config)
        self._session: requests.Session | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "FiixClient":
        self._session = requests.Session()
        self._session.mount("https://", _build_retry_adapter(self.config.max_retries))
        # Content-Type is set per-request (text/plain per Fiix auth spec).
        log.info("FiixClient session opened (max_retries=%d).", self.config.max_retries)
        return self

    def __exit__(self, *_: object) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
            log.info("FiixClient session closed.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        """Sign and POST *request_payload* to the Fiix API.

        The payload is wrapped in the signed envelope by
        :class:`~fiix.auth.FiixAuth` before transmission.

        Args:
            request_payload: The inner ``request`` dict for the Fiix API
                             call.  Must contain at minimum a ``_maCn`` key
                             identifying the API action, e.g.::

                                 {"_maCn": "WorkOrder.find", "fields": [...]}

        Returns:
            Parsed JSON response body as a Python dict.

        Raises:
            FiixConnectionError: If called outside a context manager, or on
                                 any network-level failure (timeout, DNS, etc.).
            FiixAuthError:       On HMAC signing failure or HTTP 401/403.
            FiixRateLimitError:  On HTTP 429 (after retries exhausted).
            FiixAPIError:        On any other non-2xx response or malformed
                                 JSON body.
        """
        if self._session is None:
            raise FiixConnectionError(
                "FiixClient must be used as a context manager. "
                "Use: with FiixClient(config) as client: ..."
            )

        # clientVersion FIRST — matches the working Fiix integration code key order.
        payload: dict[str, Any] = {"clientVersion": _CLIENT_VERSION, **request_payload}
        # Serialise body to compact JSON.
        body_json: str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        # Derive action: "FindRequest" -> "FindResponse".
        action: str = str(payload.get("_maCn", "FindRequest")).replace("Request", "Response")

        # Build the URI to sign (NO https:// prefix) — this is what gets HMAC-signed.
        # Matches the working code pattern:
        #   hmac.new(secretKey, fiixUri, sha256).hexdigest()
        signing_uri = (
            f"{self.config.subdomain}/api/?"
            f"action={action}"
            f"&appKey={self.config.app_key}"
            f"&accessKey={self.config.access_key}"
            f"&signatureMethod=HmacSHA256"
            f"&signatureVersion=1"
        )

        # Full request URL = https:// + signing URI.
        full_url = f"https://{signing_uri}"

        # Auth headers: Content-Type text/plain, Authorization = HMAC signature.
        auth_headers = self._auth.build_headers(signing_uri)

        log.debug("Posting action '%s' -> %s", action, full_url)
        log.debug("Request body: %s", body_json)
        print(f"[Fiix] Body  : {body_json}")

        try:
            response = self._session.post(
                full_url,
                data=body_json,
                headers=auth_headers,
                timeout=self.config.timeout,
                verify=False,     # TODO: Remove once Fiix cert is valid
            )
        except requests.exceptions.ConnectionError as exc:
            raise FiixConnectionError(
                f"Network error reaching Fiix API at {full_url}: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise FiixConnectionError(
                f"Fiix API request timed out after {self.config.timeout}s "
                f"for action '{action}': {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise FiixConnectionError(
                f"Unexpected requests error for action '{action}': {exc}"
            ) from exc
        print("============================")
        print(response)
        print("============================")
        return self._handle_response(response, action)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_response(
        self, response: requests.Response, action: str
    ) -> dict[str, Any]:
        """Validate *response* and return its parsed JSON body.

        Args:
            response: Raw :class:`requests.Response` from the Fiix API.
            action:   API action string used only in log and error messages.

        Returns:
            Parsed JSON body as a dict.

        Raises:
            FiixRateLimitError: On HTTP 429.
            FiixAuthError:      On HTTP 401 or 403.
            FiixAPIError:       On any other non-2xx status, or if the
                                response body is not valid JSON.
        """
        log.debug("HTTP %d received for action '%s'.", response.status_code, action)

        if response.status_code == 429:
            raise FiixRateLimitError(
                f"Fiix API rate limit exceeded for action '{action}'.",
                status_code=429,
            )

        if response.status_code in (401, 403):
            raise FiixAuthError(
                f"Fiix API rejected credentials (HTTP {response.status_code}) "
                f"for action '{action}'. Verify FIIX_APP_KEY, FIIX_ACCESS_KEY, "
                "and FIIX_SECRET_KEY in the root .env file."
            )

        if not response.ok:
            raise FiixAPIError(
                f"Fiix API returned HTTP {response.status_code} for action "
                f"'{action}': {response.text[:400]}",
                status_code=response.status_code,
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise FiixAPIError(
                f"Fiix API returned non-JSON body for action '{action}': "
                f"{response.text[:400]}"
            ) from exc

        log.info(
            "Action '%s' succeeded. totalObjects=%s",
            action,
            body.get("totalObjects", "n/a"),
        )
        return body
