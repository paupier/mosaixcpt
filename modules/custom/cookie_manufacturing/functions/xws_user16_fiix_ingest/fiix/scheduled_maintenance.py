"""ScheduledMaintenance lookup from the Fiix CMMS API.

Responsibilities
----------------
- Query the Fiix API for a ScheduledMaintenance record by ``strCode``.
- Return the numeric ``id`` needed to filter Work Orders by
  ``intScheduledMaintenanceID``.
- No CDF / mapping logic.
"""
from __future__ import annotations

from typing import Any

from .client import FiixClient
from .exceptions import FiixAPIError
from .logger import get_logger

log = get_logger(__name__)

_SM_CLASS: str = "ScheduledMaintenance"
_FIND_REQUEST_ACTION: str = "FindRequest"
_FIND_RESPONSE_ACTION: str = "FindResponse"


class ScheduledMaintenanceService:
    """Retrieves ScheduledMaintenance records from the Fiix CMMS API.

    Args:
        client: An **open** :class:`~fiix.client.FiixClient` instance.

    Usage::

        with FiixClient(config) as fc:
            sm_id = ScheduledMaintenanceService(fc).find_id_by_code("xws_testXX_SM")
    """

    def __init__(self, client: FiixClient) -> None:
        self._client = client

    def find_id_by_code(self, code: str) -> int:
        """Return the Fiix ``id`` of the ScheduledMaintenance whose ``strCode`` matches *code*.

        Sends the following FindRequest to the Fiix API::

            {
                "_maCn": "FindRequest",
                "className": "ScheduledMaintenance",
                "filters": [{"ql": "strCode = ?", "parameters": ["<code>"]}],
                "fields": "*"
            }

        Args:
            code: The ``strCode`` value to match (e.g. ``"xws_testXX_SM"``).
                  Configured via the ``fiixUserCode`` variable in
                  ``config.prod.yaml``.

        Returns:
            The numeric Fiix ``id`` of the matching ScheduledMaintenance record.

        Raises:
            FiixAPIError:        If no record matches *code*, or on unexpected
                                 API response structure.
            FiixConnectionError: On network failure.
            FiixAuthError:       On authentication rejection.
        """
        payload: dict[str, Any] = {
            "_maCn": _FIND_REQUEST_ACTION,
            "className": _SM_CLASS,
            "filters": [{"ql": "strCode = ?", "parameters": [code]}],
            "fields": "*",
        }

        log.info("Fetching ScheduledMaintenance with strCode=%r", code)
        response = self._client.post(payload)

        response_class: str = str(response.get("_maCn", ""))
        if response_class != _FIND_RESPONSE_ACTION:
            raise FiixAPIError(
                f"Unexpected ScheduledMaintenance response type: "
                f"expected '{_FIND_RESPONSE_ACTION}', got '{response_class}'."
            )

        objects: list[dict] = response.get("objects") or []
        if not objects:
            raise FiixAPIError(
                f"No ScheduledMaintenance found with strCode={code!r}. "
                "Verify the 'fiixUserCode' variable in config.prod.yaml."
            )

        sm_id = int(objects[0]["id"])
        log.info("Resolved ScheduledMaintenance id=%d for strCode=%r", sm_id, code)
        return sm_id
