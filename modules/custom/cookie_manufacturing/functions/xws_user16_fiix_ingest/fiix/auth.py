"""Fiix HMAC-SHA256 request signing.

Responsible for:
- Computing the HMAC-SHA256 signature required by the Fiix API.
- Building the HTTP headers that authenticate every request.

Fiix authentication (confirmed from working integration code)::

    # 1. Build signing URI (NO https:// prefix)
    signing_uri = "{subdomain}/api/?action=FindResponse
                   &appKey={appKey}&accessKey={accessKey}
                   &signatureMethod=HmacSHA256&signatureVersion=1"

    # 2. Sign the URI with the secret key
    signature = HMAC-SHA256(secretKey, signing_uri)

    # 3. Full request URL
    url = "https://" + signing_uri

    # 4. Headers
    headers = {"Content-Type": "text/plain", "Authorization": signature}

    # 5. Body is plain JSON (no auth wrapper)

Reference:
    https://fiixlabs.github.io/api-documentation/#/ApiDoc#Authentication
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .config import FiixConfig
from .exceptions import FiixAuthError
from .logger import get_logger

log = get_logger(__name__)


class FiixAuth:
    """Builds HTTP headers that authenticate a Fiix API request.

    Authentication flow (from working Fiix integration code)::

        signing_uri = "{subdomain}/api/?action=FindResponse
                       &appKey={appKey}&accessKey={accessKey}
                       &signatureMethod=HmacSHA256&signatureVersion=1"

        signature = HMAC-SHA256(secretKey, signing_uri)
        url = "https://" + signing_uri
        headers = {"Content-Type": "text/plain", "Authorization": signature}

    Key points:
    - The URI is signed (NOT the request body).
    - The signature goes in the ``Authorization`` header.
    - ``Content-Type`` is ``text/plain``.
    - The full request URL is ``https://`` + signing_uri.

    Args:
        config: Immutable :class:`FiixConfig` holding all credentials.
    """

    def __init__(self, config: FiixConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def build_headers(self, signing_uri: str) -> dict[str, str]:
        """Return HTTP headers for an authenticated Fiix API request.

        The HMAC-SHA256 signature is computed over *signing_uri* (the URI
        string **without** the ``https://`` scheme) and placed in the
        ``Authorization`` header.

        Args:
            signing_uri: URI string to sign, e.g.::

                ``rockwellpartners.macmms.com/api/?action=FindResponse
                  &appKey=...&accessKey=...&signatureMethod=HmacSHA256
                  &signatureVersion=1``

        Returns:
            Dict of HTTP headers::

                {
                    "Content-Type":  "text/plain",
                    "Authorization": "<hmac_sha256_hex>",
                }

        Raises:
            FiixAuthError: If HMAC signing fails.
        """
        signature = self._sign(signing_uri)
        log.debug("Auth headers built (sig prefix: %s...).", signature[:8])
        return {
            "Content-Type": "text/plain",
            "Authorization": signature,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sign(self, body_json: str) -> str:
        """Compute the HMAC-SHA256 hex digest of *body_json*.

        Args:
            body_json: Compact JSON string to sign (UTF-8 encoded).

        Returns:
            Lowercase hex-encoded HMAC-SHA256 digest.

        Raises:
            FiixAuthError: If the HMAC computation fails.
        """
        try:
            digest: str = hmac.new(
                self._config.secret_key.encode("utf-8"),
                body_json.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        except Exception as exc:
            raise FiixAuthError(
                f"Failed to compute HMAC-SHA256 signature: {exc}"
            ) from exc
        log.debug("HMAC-SHA256 signature computed.")
        return digest
        return digest
