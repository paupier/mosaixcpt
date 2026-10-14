"""Fiix domain models.

This module is the single source of truth for all Fiix entity types.

Design constraints
------------------
- No DataMosaix / CDF imports. Models are fully independent of the
  upload target.
- No fiix.client or fiix.config imports. Models carry no I/O concern.
- ``WorkOrder`` is a frozen dataclass — immutable after construction and
  safe to cache, hash, or store in sets.
- All Fiix Unix-millisecond timestamps are converted to timezone-aware
  UTC :class:`datetime` objects at construction time.
- Optional fields use ``None`` explicitly; empty strings returned by the
  Fiix API are normalised to ``None`` during construction.

The ``from_api_response`` classmethod on each model encapsulates the full
mapping from a raw Fiix JSON object dict to the typed Python model.
Validation of required fields is performed there so parse errors are
raised as :class:`~fiix.exceptions.FiixAPIError` with actionable messages.

Reference:
    https://fiixlabs.github.io/api-documentation/#/ApiDoc#WorkOrder
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .exceptions import FiixAPIError

# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------


def _ms_to_utc(epoch_ms: int | None) -> datetime | None:
    """Convert a Fiix Unix epoch-milliseconds integer to a UTC :class:`datetime`.

    Fiix sends ``0`` (not ``null``) when a timestamp field has no value, so
    both ``None`` and ``0`` are treated as absent and mapped to ``None``.

    Args:
        epoch_ms: Milliseconds since the Unix epoch, ``None``, or ``0``.

    Returns:
        Timezone-aware UTC :class:`datetime`, or ``None`` if input is falsy.

    Examples::

        >>> _ms_to_utc(1778747717000)
        datetime.datetime(2026, 5, 13, ..., tzinfo=datetime.timezone.utc)

        >>> _ms_to_utc(0) is None
        True

        >>> _ms_to_utc(None) is None
        True
    """
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkOrder:
    """Immutable, typed representation of a single Fiix Work Order.

    Constructed via :meth:`from_api_response` rather than directly so that
    all field validation and type coercion happens in one place.

    Fiix field → Python attribute mapping
    ---------------------------------------
    .. list-table::
       :header-rows: 1

       * - Fiix JSON field
         - Attribute
         - Type
         - Notes
       * - ``id``
         - ``fiix_id``
         - ``int``
         - Required. Fiix numeric primary key.
       * - ``strUuid``
         - ``external_id``
         - ``str``
         - Required. Stable UUID; used as CDF ``externalId``.
       * - ``strCode``
         - ``work_order_number``
         - ``str | None``
         - Human-readable work order code.
       * - ``strDescription``
         - ``description``
         - ``str | None``
         - Work order description / title.
       * - ``strCompletionNotes``
         - ``completion_notes``
         - ``str | None``
         - Notes recorded at completion.
       * - ``intWorkOrderStatusID``
         - ``status_id``
         - ``int | None``
         - Numeric status identifier.
       * - ``intMaintenanceTypeID``
         - ``maintenance_type_id``
         - ``int | None``
         - Numeric maintenance type identifier.
       * - ``intPriorityID``
         - ``priority_id``
         - ``int | None``
         - Numeric priority identifier.
       * - ``intScheduledMaintenanceID``
         - ``scheduled_maintenance_id``
         - ``int | None``
         - Linked scheduled maintenance record, if any.
       * - ``strAssetIds``
         - ``asset_ids``
         - ``str | None``
         - Comma-separated Fiix asset ID string.
       * - ``strAssets``
         - ``asset_name``
         - ``str | None``
         - Human-readable asset name(s).
       * - ``strAssignedUserIds``
         - ``assigned_user_ids``
         - ``str | None``
         - Comma-separated assigned user ID string.
       * - ``strAssignedUsers``
         - ``assigned_user_names``
         - ``str | None``
         - Human-readable assigned user name(s).
       * - ``strCompletedByUsers``
         - ``completed_by_users``
         - ``str | None``
         - Human-readable completing user name(s).
       * - ``dtmDateCreated``
         - ``created_time``
         - ``datetime | None``
         - UTC; converted from Unix ms.
       * - ``dtmDateLastModified``
         - ``last_updated_time``
         - ``datetime | None``
         - UTC; converted from Unix ms.
       * - ``dtmDateCompleted``
         - ``actual_end_time``
         - ``datetime | None``
         - UTC; converted from Unix ms.
       * - ``dtmSuggestedStartDate``
         - ``planned_start_time``
         - ``datetime | None``
         - UTC; converted from Unix ms.
       * - ``dtmSuggestedCompletionDate``
         - ``planned_end_time``
         - ``datetime | None``
         - UTC; converted from Unix ms.
    """

    # --- Required fields (raise FiixAPIError if absent) ---
    fiix_id: int
    external_id: str

    # --- Optional string fields ---
    work_order_number: str | None
    description: str | None
    completion_notes: str | None

    # --- Optional numeric ID fields ---
    status_id: int | None
    # Human-readable label from extraFields.dv_intWorkOrderStatusID (e.g. "Closed, Completed").
    status_label: str | None
    maintenance_type_id: int | None
    # Human-readable label from extraFields.dv_intMaintenanceTypeID (e.g. "Preventive").
    maintenance_type_label: str | None
    priority_id: int | None
    scheduled_maintenance_id: int | None

    # --- Optional asset / personnel string fields ---
    asset_ids: str | None
    asset_name: str | None
    assigned_user_ids: str | None
    assigned_user_names: str | None
    completed_by_users: str | None

    # --- Optional timestamp fields (UTC datetime) ---
    created_time: datetime | None
    last_updated_time: datetime | None
    actual_end_time: datetime | None
    planned_start_time: datetime | None
    planned_end_time: datetime | None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_api_response(cls, raw: dict[str, Any]) -> "WorkOrder":
        """Construct a :class:`WorkOrder` from a single Fiix API response object.

        Performs all type coercion, timestamp conversion, and null normalisation
        in one place:

        - Empty strings are normalised to ``None``.
        - Unix millisecond timestamps are converted to UTC-aware
          :class:`datetime` objects via :func:`_ms_to_utc`.
        - ``0`` timestamps (Fiix's sentinel for "no value") map to ``None``.
        - Required fields (``id``, ``strUuid``) raise :class:`FiixAPIError`
          when absent so the caller receives an actionable error message.

        Args:
            raw: A single dict from the ``objects`` list in a Fiix
                 ``FindResponse``.  Typically looks like::

                     {
                         "className": "WorkOrder",
                         "id": 165540519,
                         "strUuid": "3935cf23-...",
                         "strCode": "15517",
                         ...
                     }

        Returns:
            Fully populated, immutable :class:`WorkOrder` instance.

        Raises:
            FiixAPIError: If ``id`` or ``strUuid`` is missing or empty.

        Example::

            wo = WorkOrder.from_api_response(api_object_dict)
            print(wo.fiix_id, wo.external_id, wo.planned_start_time)
        """
        fiix_id: Any = raw.get("id")
        external_id: str | None = raw.get("strUuid") or None

        if fiix_id is None:
            raise FiixAPIError(
                f"Work order object is missing the required 'id' field. "
                f"Raw object: {raw}"
            )
        if not external_id:
            raise FiixAPIError(
                f"Work order id={fiix_id} is missing the required 'strUuid' field. "
                "Every work order must have a stable UUID for use as CDF externalId."
            )

        return cls(
            # --- Required ---
            fiix_id=int(fiix_id),
            external_id=str(external_id),
            # --- Optional strings ---
            work_order_number=raw.get("strCode") or None,
            description=raw.get("strDescription") or None,
            completion_notes=raw.get("strCompletionNotes") or None,
            # --- Optional numeric IDs ---
            # Labels come from the nested extraFields dict returned by dv_ field requests.
            status_id=raw.get("intWorkOrderStatusID"),
            status_label=(raw.get("extraFields") or {}).get("dv_intWorkOrderStatusID") or None,
            maintenance_type_id=raw.get("intMaintenanceTypeID"),
            maintenance_type_label=(raw.get("extraFields") or {}).get("dv_intMaintenanceTypeID") or None,
            priority_id=raw.get("intPriorityID"),
            scheduled_maintenance_id=raw.get("intScheduledMaintenanceID"),
            # --- Optional asset / personnel strings ---
            # Fiix returns leading/trailing whitespace in ID strings (e.g. " 78293848 ").
            # Strip here so downstream mapping and node_reference() receive clean values.
            asset_ids=raw.get("strAssetIds", "").strip() or None,
            asset_name=raw.get("strAssets") or None,
            assigned_user_ids=raw.get("strAssignedUserIds", "").strip() or None,
            assigned_user_names=raw.get("strAssignedUsers") or None,
            completed_by_users=raw.get("strCompletedByUsers") or None,
            # --- Optional timestamps ---
            created_time=_ms_to_utc(raw.get("dtmDateCreated")),
            last_updated_time=_ms_to_utc(raw.get("dtmDateLastModified")),
            actual_end_time=_ms_to_utc(raw.get("dtmDateCompleted")),
            planned_start_time=_ms_to_utc(raw.get("dtmSuggestedStartDate")),
            planned_end_time=_ms_to_utc(raw.get("dtmSuggestedCompletionDate")),
        )


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Asset:
    """Immutable representation of a single Fiix Asset.

    Constructed via :meth:`from_api_response`.

    Attributes:
        fiix_id:     Fiix numeric primary key (``id``).
        name:        Human-readable asset name (``strName``).
        code:        Asset code used as CDF ``externalId`` (``strCode``).
        description: Optional description (``strDescription``).
    """

    fiix_id: int
    name: str | None
    code: str | None
    description: str | None

    @classmethod
    def from_api_response(cls, raw: dict[str, Any]) -> "Asset":
        """Construct an :class:`Asset` from a single Fiix API response object."""
        fiix_id: Any = raw.get("id")
        if fiix_id is None:
            raise FiixAPIError(
                f"Asset object is missing the required 'id' field. Raw: {raw}"
            )
        return cls(
            fiix_id=int(fiix_id),
            name=raw.get("strName") or None,
            code=raw.get("strCode") or None,
            description=raw.get("strDescription") or None,
        )
