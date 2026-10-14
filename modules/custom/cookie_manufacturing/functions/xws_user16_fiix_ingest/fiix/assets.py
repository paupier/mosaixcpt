"""Fiix Asset retrieval service.

Responsibilities
----------------
- Query the Fiix API for Asset records by parent ID (``intAssetParentID``).
- Return strongly typed :class:`~fiix.models.Asset` objects.
- No CDF / mapping logic.
"""
from __future__ import annotations

from typing import Any

from .client import FiixClient
from .exceptions import FiixAPIError
from .logger import get_logger
from .models import Asset

log = get_logger(__name__)

_ASSET_CLASS: str = "Asset"
_FIND_REQUEST_ACTION: str = "FindRequest"
_FIND_RESPONSE_ACTION: str = "FindResponse"
_ASSET_FIELDS: str = "id, strName, strCode, strDescription"


class AssetService:
    """Retrieves Asset records from the Fiix CMMS API.

    Args:
        client: An **open** :class:`~fiix.client.FiixClient` instance.

    Usage::

        with FiixClient(config) as fc:
            assets = AssetService(fc).find_by_parent_id(78293848)
            equipment_code = assets[0].code if assets else None
    """

    def __init__(self, client: FiixClient) -> None:
        self._client = client

    def find_by_parent_id(self, parent_id: int) -> list[Asset]:
        """Fetch all Assets whose ``intAssetParentID`` matches *parent_id*.

        Sends the exact FindRequest structure specified in the integration spec::

            {
                "_maCn": "FindRequest",
                "className": "Asset",
                "filters": [{"ql": "intAssetParentID = ?", "parameters": [<parent_id>]}],
                "fields": "id, strName, strCode, strDescription"
            }

        Args:
            parent_id: The Fiix asset ID to use as the parent filter
                       (taken from WorkOrder ``strAssetIds``).

        Returns:
            List of :class:`~fiix.models.Asset` objects.  Empty if no match.

        Raises:
            FiixAPIError:        On unexpected API response or parse failure.
            FiixConnectionError: On network failure.
            FiixAuthError:       On authentication rejection.
        """
        payload: dict[str, Any] = {
            "_maCn": _FIND_REQUEST_ACTION,
            "className": _ASSET_CLASS,
            "filters": [{"ql": "intAssetParentID = ?", "parameters": [parent_id]}],
            "fields": _ASSET_FIELDS,
        }

        log.info("Fetching Asset with intAssetParentID=%d", parent_id)
        response = self._client.post(payload)

        response_class: str = str(response.get("_maCn", ""))
        if response_class != _FIND_RESPONSE_ACTION:
            raise FiixAPIError(
                f"Unexpected Asset response type: expected '{_FIND_RESPONSE_ACTION}', "
                f"got '{response_class}'."
            )

        raw_objects: list[dict[str, Any]] = response.get("objects") or []
        assets: list[Asset] = []
        for raw in raw_objects:
            try:
                assets.append(Asset.from_api_response(raw))
            except FiixAPIError:
                raise
            except Exception as exc:
                raise FiixAPIError(
                    f"Failed to parse Asset object: {exc}. Raw: {raw}"
                ) from exc

        log.info(
            "Found %d asset(s) for intAssetParentID=%d.", len(assets), parent_id
        )
        return assets
