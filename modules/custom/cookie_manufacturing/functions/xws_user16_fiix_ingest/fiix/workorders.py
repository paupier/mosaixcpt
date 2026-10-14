"""Work Order retrieval from the Fiix CMMS API.

Responsibilities
----------------
- Provide FindRequest / WorkOrderFilter / PageResult value objects.
- Implement WorkOrderService for paginated Work Order retrieval.
- Return strongly typed :class:`~fiix.models.WorkOrder` objects.
- No CDF / DataMosaix upload logic.

Architecture notes
------------------
- The WorkOrder domain model lives in :mod:`fiix.models`, not here.
  This module is concerned only with how to query and paginate the API.
- WorkOrderService depends on FiixClient (injected), not on FiixConfig
  directly, keeping the service testable without real credentials.
- Pagination is exposed both as a single-page call (find_page) and as a
  lazy generator (find_all) so callers control their memory trade-off.

Reference:
    https://fiixlabs.github.io/api-documentation/#/ApiDoc#WorkOrder
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Generator

from .client import FiixClient
from .exceptions import FiixAPIError
from .logger import get_logger
from .models import WorkOrder

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WORK_ORDER_CLASS: str = "WorkOrder"
_FIND_REQUEST_ACTION: str = "FindRequest"
_FIND_RESPONSE_ACTION: str = "FindResponse"

# Complete set of Fiix fields needed to satisfy the Phase 1 RAW column mapping.
# Extend this tuple when later phases introduce new fields.
_WORK_ORDER_FIELDS: tuple[str, ...] = (
    "id",
    "strUuid",
    "strCode",
    "strDescription",
    "strCompletionNotes",
    "intWorkOrderStatusID",
    "intMaintenanceTypeID",
    "intPriorityID",
    "intScheduledMaintenanceID",
    "strAssetIds",
    "strAssets",
    "strAssignedUserIds",
    "strAssignedUsers",
    "strCompletedByUsers",
    "dtmDateCreated",
    "dtmDateLastModified",
    "dtmDateCompleted",
    "dtmSuggestedStartDate",
    "dtmSuggestedCompletionDate",
)

DEFAULT_PAGE_SIZE: int = 50


# ---------------------------------------------------------------------------
# Lookup helpers  (one API call each, fetch once per import run)
# ---------------------------------------------------------------------------


def fetch_status_labels(client: FiixClient) -> dict[int, str]:
    """Return ``{status_id: label}`` by fetching all WorkOrderStatus objects.

    Example result::

        {493615: "Open", 493617: "Closed, Completed", ...}

    Args:
        client: An open :class:`~fiix.client.FiixClient`.

    Returns:
        Dict mapping numeric status ID to human-readable label.
    """
    response = client.post({"_maCn": "FindRequest", "className": "WorkOrderStatus", "fields": "*"})
    labels: dict[int, str] = {
        int(obj["id"]): str(obj["strName"])
        for obj in (response.get("objects") or [])
        if obj.get("id") is not None and obj.get("strName")
    }
    log.info("Fetched %d WorkOrderStatus labels.", len(labels))
    return labels


def fetch_maintenance_type_labels(client: FiixClient) -> dict[int, str]:
    """Return ``{type_id: label}`` by fetching all MaintenanceType objects.

    Example result::

        {604625: "Preventive", 604627: "Corrective", ...}

    Args:
        client: An open :class:`~fiix.client.FiixClient`.

    Returns:
        Dict mapping numeric maintenance type ID to human-readable label.
    """
    response = client.post({"_maCn": "FindRequest", "className": "MaintenanceType", "fields": "*"})
    labels: dict[int, str] = {
        int(obj["id"]): str(obj["strName"])
        for obj in (response.get("objects") or [])
        if obj.get("id") is not None and obj.get("strName")
    }
    log.info("Fetched %d MaintenanceType labels.", len(labels))
    return labels
# ---------------------------------------------------------------------------


def _to_ql_filter(wf: WorkOrderFilter) -> dict[str, Any]:
    """Convert a :class:`WorkOrderFilter` to the Fiix API ql/parameters format.

    Single value:  ``{"ql": "field = ?", "parameters": [v]}``
    Multiple values: ``{"ql": "field IN (?, ?)", "parameters": [v1, v2]}``

    Args:
        wf: Filter to convert.

    Returns:
        Dict with ``ql`` and ``parameters`` keys.
    """
    if len(wf.values) == 1:
        return {"ql": f"{wf.field_name} = ?", "parameters": wf.values}
    placeholders = ", ".join("?" * len(wf.values))
    return {"ql": f"{wf.field_name} IN ({placeholders})", "parameters": wf.values}
# ---------------------------------------------------------------------------


@dataclass
class WorkOrderFilter:
    """A single field-level filter expression for a Fiix FindRequest.

    Args:
        field_name: Fiix field name to filter on (e.g.
                    ``"intWorkOrderStatusID"``).
        values:     Allowed values for that field.  The Fiix API treats this
                    as an OR condition across the list.

    Example::

        WorkOrderFilter(field_name="intWorkOrderStatusID", values=[1, 2, 3])
    """

    field_name: str
    values: list[Any]


@dataclass
class FindRequest:
    """Parameters for a single paginated Fiix Work Order API call.

    Fiix uses 1-based page numbering.

    Args:
        page:      1-based page index to retrieve (default ``1``).
        page_size: Records per page (default ``50``).  The Fiix API typically
                   supports up to 1 000 records per page.
        filters:   Optional list of :class:`WorkOrderFilter` expressions
                   applied server-side before pagination.

    Example::

        FindRequest(
            page=1,
            page_size=100,
            filters=[WorkOrderFilter("intWorkOrderStatusID", [1, 2])],
        )
    """

    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    filters: list[WorkOrderFilter] = field(default_factory=list)


@dataclass
class PageResult:
    """Outcome of a single paginated Fiix API call.

    Attributes:
        items:     Parsed :class:`WorkOrder` objects from this page.
        total:     Total number of matching records across all pages.
        page:      1-based page number that was fetched.
        page_size: Number of records that were requested per page.
    """

    items: list[WorkOrder]
    total: int
    page: int
    page_size: int

    @property
    def has_more(self) -> bool:
        """``True`` when there are additional pages beyond this one."""
        return self.page * self.page_size < self.total


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WorkOrderService:
    """Retrieves Work Orders from the Fiix CMMS API.

    Separates API interaction from business decisions:
    - Builds FindRequest payloads from typed parameters.
    - Handles pagination transparently.
    - Returns strongly typed :class:`WorkOrder` objects.
    - Contains no CDF / DataMosaix upload logic.

    Args:
        client: An **open** :class:`~fiix.client.FiixClient` instance.
                The caller is responsible for the client lifecycle.

    Usage::

        from fiix import FiixConfig, FiixClient
        from fiix.workorders import WorkOrderService, FindRequest, WorkOrderFilter

        config = FiixConfig.from_env()
        with FiixClient(config) as client:
            service = WorkOrderService(client)

            # --- Single page ---
            result = service.find_page(FindRequest(page=1, page_size=50))
            print(f"Page 1 of {result.total} total work orders")

            # --- All pages (generator, memory-efficient) ---
            for wo in service.find_all(page_size=100):
                print(wo.fiix_id, wo.description)

            # --- Filtered query ---
            filters = [WorkOrderFilter("intWorkOrderStatusID", [1, 2])]
            for wo in service.find_all(filters=filters):
                print(wo.external_id)
    """

    def __init__(self, client: FiixClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_page(self, request: FindRequest) -> PageResult:
        """Fetch a single page of Work Orders.

        Args:
            request: :class:`FindRequest` specifying page number, page size,
                     and any filters.

        Returns:
            :class:`PageResult` containing parsed :class:`WorkOrder` objects,
            the total record count, and pagination metadata.

        Raises:
            FiixAPIError:        On unexpected API response structure or
                                 parse failure.
            FiixConnectionError: On any network-level failure.
            FiixAuthError:       On authentication rejection by Fiix.
        """
        payload = self._build_payload(request)

        log.info(
            "Requesting Work Orders: page=%d page_size=%d filters=%d",
            request.page,
            request.page_size,
            len(request.filters),
        )

        response = self._client.post(payload)
        result = self._parse_page_result(response, request)

        log.info(
            "Received %d work orders on page %d (total=%d, has_more=%s).",
            len(result.items),
            result.page,
            result.total,
            result.has_more,
        )
        print("[Fiix RAW response JSON]")
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return result

    def find_all(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        filters: list[WorkOrderFilter] | None = None,
    ) -> Generator[WorkOrder, None, None]:
        """Yield every Work Order matching the given filters across all pages.

        Pagination is handled automatically.  Each page is requested only when
        the generator is advanced, keeping memory usage bounded to one page at
        a time regardless of the total record count.

        Args:
            page_size: Records per API call (default ``50``).
            filters:   Optional :class:`WorkOrderFilter` expressions.  Pass
                       ``None`` or omit to retrieve all work orders.

        Yields:
            :class:`WorkOrder` instances in the order returned by the API.

        Raises:
            FiixAPIError:        On unexpected API response or parse failure.
            FiixConnectionError: On network failure.
            FiixAuthError:       On authentication rejection.

        Example::

            for wo in service.find_all(page_size=100):
                process(wo)
        """
        active_filters: list[WorkOrderFilter] = filters or []
        page = 1
        total_yielded = 0

        while True:
            result = self.find_page(
                FindRequest(page=page, page_size=page_size, filters=active_filters)
            )

            for item in result.items:
                yield item
                total_yielded += 1

            log.debug(
                "Page %d done — yielded %d / %d work orders so far.",
                page,
                total_yielded,
                result.total,
            )

            if not result.has_more:
                break

            page += 1

        log.info(
            "find_all complete — %d work order(s) retrieved in %d page(s).",
            total_yielded,
            page,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(request: FindRequest) -> dict[str, Any]:
        """Translate a :class:`FindRequest` into a raw Fiix API request dict.

        Uses ``fields: "*"`` to request all available fields, matching the
        Postman-validated request format.  Filters use the Fiix ql/parameters
        SQL-style syntax.  The ``filters`` key is omitted when no filters are
        present.

        Args:
            request: Validated :class:`FindRequest`.

        Returns:
            Dict ready to pass to :meth:`~fiix.client.FiixClient.post`.
        """
        # Key order must match the Postman-validated payload:
        # _maCn, className, filters (if any), fields
        payload: dict[str, Any] = {
            "_maCn": _FIND_REQUEST_ACTION,
            "className": _WORK_ORDER_CLASS,
        }
        payload["filters"] = [{"ql": "id = ?", "parameters": [173959783]}]
        if request.filters:
            payload["filters"] = [_to_ql_filter(wf) for wf in request.filters]

        # "*" returns all base fields for this Fiix instance.
        # dv_ derived-value fields are NOT supported by this API configuration.
        # Status and maintenance type labels are resolved via separate lookup calls.
        #payload["fields"] = "*"
        # Request base fields plus dv_ derived-value fields for labels.
        payload["fields"] = (
            "*, dv_intPriorityID, dv_intMaintenanceTypeID, dv_intWorkOrderStatusID, "
            "dv_intScheduledMaintenanceID, dv_intRCAActionID, dv_intRCACauseID, dv_intRCAProblemID"
        )

        return payload

    @staticmethod
    def _parse_page_result(
        response: dict[str, Any], request: FindRequest
    ) -> PageResult:
        """Validate a raw Fiix FindResponse and return a typed :class:`PageResult`.

        Args:
            response: Raw dict returned by :meth:`~fiix.client.FiixClient.post`.
            request:  The originating :class:`FindRequest` (for metadata).

        Returns:
            Populated :class:`PageResult`.

        Raises:
            FiixAPIError: If ``_maCn`` is not ``"FindResponse"``, if the
                          ``objects`` list is malformed, or if any individual
                          work order object cannot be parsed.
        """
        response_class: str = str(response.get("_maCn", ""))
        if response_class != _FIND_RESPONSE_ACTION:
            raise FiixAPIError(
                f"Unexpected response type from Fiix API: "
                f"expected '{_FIND_RESPONSE_ACTION}', got '{response_class}'. "
                "Verify credentials and the Fiix API endpoint."
            )

        raw_objects: list[dict[str, Any]] = response.get("objects") or []
        total: int = int(response.get("totalObjects", 0))

        work_orders: list[WorkOrder] = []
        for idx, raw in enumerate(raw_objects):
            try:
                work_orders.append(WorkOrder.from_api_response(raw))
            except FiixAPIError:
                raise
            except Exception as exc:
                raise FiixAPIError(
                    f"Failed to parse work order at index {idx} "
                    f"on page {request.page}: {exc}"
                ) from exc

        log.debug(
            "Parsed %d work order(s) from page %d (server total=%d).",
            len(work_orders),
            request.page,
            total,
        )
        return PageResult(
            items=work_orders,
            total=total,
            page=request.page,
            page_size=request.page_size,
        )
