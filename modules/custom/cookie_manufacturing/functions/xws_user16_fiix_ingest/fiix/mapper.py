"""Fiix Work Order → CDF RAW row mapper.

Single responsibility: translate :class:`~fiix.models.WorkOrder` instances
into flat dictionaries whose keys match the ``isa_work_order`` RAW table
schema consumed by the existing SQL transformation.

No API calls. No CDF SDK imports. No uploads.

Schema authority
----------------
The output dictionary schema is governed by three files that must stay
aligned.  Do not rename RAW columns here without checking all three:

1. ``data/resources/isa_work_order.RawRows.csv``
   — defines the column names in the seed data.
2. ``modules/.../transformations/work_order_tr.Transformation.sql``
   — reads and casts every column; determines timestamp parsing format.
3. ``docs/references/fiix-api-integration-reference.md`` (Section 10 / 19)
   — the authoritative Fiix field → RAW column mapping table.

Timestamp format
----------------
The SQL transformation parses timestamps with::

    to_timestamp(col, "yyyy-MM-dd'T'HH:mm:ss'Z'")

All datetime fields must be serialised to that exact format before being
stored in the RAW row dict.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .logger import get_logger
from .models import WorkOrder

log = get_logger(__name__)

# Timestamp format expected by work_order_tr.Transformation.sql.
# Must match the Spark SQL pattern: "yyyy-MM-dd'T'HH:mm:ss'Z'"
_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"


def _description_prefix(description: str | None) -> str:
    """Extract the prefix before ``|`` from ``strDescription``, stripped.

    Returns an empty string if the description is absent or has no ``|``.
    e.g. ``"WO_CHI_00 | Investigate..."`` → ``"WO_CHI_00"``
    """
    return (description.split("|", 1)[0].strip() if description else "") or ""


def _parse_site_code(description: str | None) -> str | None:
    """Extract the site code from the ``strDescription`` prefix.

    Splits the prefix by ``_`` and returns the second segment.
    e.g. ``"WO_CHI_00 | ..."`` → prefix ``"WO_CHI_00"`` → site ``"CHI"``.

    Returns ``None`` if the description is absent or the prefix has fewer
    than two ``_``-separated segments.
    """
    prefix = _description_prefix(description)
    if not prefix:
        return None
    parts = prefix.split("_")
    return parts[1] if len(parts) > 1 else None


def _parse_asset_ext_id(asset_name: str | None) -> str | None:
    """Extract the external ID from the parenthesised suffix of ``strAssets``.

    e.g. ``"CHI Oven 1 Unit (UNIT_CHI_BAKE)"`` → ``"UNIT_CHI_BAKE"``.

    Returns ``None`` if the value is absent or contains no parentheses.
    """
    if not asset_name:
        return None
    start = asset_name.rfind("(")
    end = asset_name.rfind(")")
    if start != -1 and end != -1 and end > start:
        return asset_name[start + 1:end].strip() or None
    return None


def _parse_wo_id(description: str | None, fiix_id: int) -> str:
    """Build the composite work order key from ``strDescription`` and ``id``.

    The key is formed as ``"<prefix>_<fiix_id>"``
    (e.g. ``"WO_CHI_00_173959783"``).

    Falls back to the bare fiix_id string if the description is absent
    or contains no prefix before the ``|``.
    """
    prefix = _description_prefix(description)
    return f"{prefix}_{fiix_id}" if prefix else str(fiix_id)


def _parse_wo_title(description: str | None) -> str | None:
    """Extract the title part from ``strDescription`` (after the ``|``).

    e.g. ``"WO_CHI_00 | Investigate a problem with the burner"``
    → ``"Investigate a problem with the burner"``.

    Returns the full description if no ``|`` is present, or ``None`` if absent.
    """
    if not description:
        return None
    parts = description.split("|", 1)
    return parts[1].strip() if len(parts) > 1 else description.strip()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fmt_ts(dt: datetime | None) -> str | None:
    """Serialise a UTC :class:`datetime` to ISO 8601 string for RAW storage.

    Args:
        dt: Timezone-aware UTC datetime, or ``None``.

    Returns:
        String in ``YYYY-MM-DDTHH:MM:SSZ`` format, or ``None`` if absent.
    """
    return dt.strftime(_TIMESTAMP_FORMAT) if dt is not None else None


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


class WorkOrderMapper:
    """Maps :class:`~fiix.models.WorkOrder` instances to ``isa_work_order``
    RAW table row dictionaries.

    Stateless. Labels for ``work_type`` and ``work_status`` are read directly
    from the :class:`~fiix.models.WorkOrder` model, which extracts them from
    the ``extraFields`` dict returned by the Fiix API when ``dv_`` fields are
    requested.

    Usage::

        from fiix.mapper import WorkOrderMapper

        mapper = WorkOrderMapper()
        row  = mapper.to_raw_row(work_order)
        rows = mapper.to_raw_rows([wo1, wo2, wo3])
    """
    # Public interface
    # ------------------------------------------------------------------

    def to_raw_row(self, work_order: WorkOrder, asset_code: str | None = None) -> dict[str, Any]:
        """Map a single :class:`~fiix.models.WorkOrder` to a RAW row dict.

        The returned dict always contains **every** RAW column key, even
        when the value is ``None``, so the uploader receives a complete
        and predictable schema regardless of which Fiix fields are populated.

        Fiix field → RAW column mapping (Phase 1)
        ------------------------------------------

        .. list-table::
           :header-rows: 1

           * - Fiix field
             - WorkOrder attribute
             - RAW column
             - Notes
           * - ``strUuid``
             - ``external_id``
             - ``key``, ``externalId``
             - Stable UUID; used as RAW row key for idempotent upserts.
           * - ``id``
             - ``fiix_id``
             - ``work_order_id``
             - Numeric Fiix PK, cast to string.
           * - ``strCode``
             - ``work_order_number``
             - ``work_order_number``
             - Human-readable code.
           * - ``strDescription``
             - ``description``
             - ``work_order_name``, ``description``
             - Maps to both name and description columns.
           * - ``extraFields.dv_intMaintenanceTypeID``
             - ``maintenance_type_label``
             - ``work_type``
             - From nested ``extraFields`` dict (e.g. ``"Preventive"``).
           * - ``extraFields.dv_intWorkOrderStatusID``
             - ``status_label``
             - ``work_status``
             - From nested ``extraFields`` dict (e.g. ``"Closed, Completed"``).
             Falls back to numeric ``status_id`` string if absent.
           * - ``dtmDateCreated``
             - ``created_time``
             - ``actual_start_time``, ``created_time``
             - Maps to both columns: creation time is treated as actual start.
           * - ``dtmSuggestedStartDate``
             - ``planned_start_time``
             - ``planned_start_time``
             - UTC ISO 8601 string.
           * - ``dtmSuggestedCompletionDate``
             - ``planned_end_time``
             - ``planned_end_time``
             - UTC ISO 8601 string.
           * - ``dtmDateCompleted``
             - ``actual_end_time``
             - ``actual_end_time``
             - UTC ISO 8601 string.
           * - ``dtmDateCreated``
             - ``created_time``
             - ``created_time``
             - UTC ISO 8601 string.
           * - ``dtmDateLastModified``
             - ``last_updated_time``
             - ``last_updated_time``
             - UTC ISO 8601 string.
           * - ``strAssetIds``
             - ``asset_ids``
             - ``asset_externalId``
             - Comma-separated IDs; Phase 1 passes as-is.
           * - ``strAssets``
             - ``asset_name``
             - ``asset_name``
             - Helper field; not consumed by the current SQL.
           * - ``strAssignedUserIds``
             - ``assigned_user_ids``
             - ``assigned_personnel_externalId``
             - Comma-separated IDs; Phase 1 passes as-is.
           * - ``strAssignedUsers``
             - ``assigned_user_names``
             - ``assigned_person_name``
             - Helper field; not consumed by the current SQL.
           * - ``strCompletionNotes``
             - ``completion_notes``
             - ``completion_notes``
             - Optional; not consumed by the current SQL.

        Columns with no Fiix source:
        ``equipment_externalId``, ``production_order_externalId`` are always
        ``None``.  ``asset_externalId`` and ``assigned_personnel_externalId``
        are populated from ``strAssetIds`` / ``strAssignedUserIds`` (whitespace
        stripped in the model).

        Args:
            work_order: Populated, immutable :class:`~fiix.models.WorkOrder`.

        Returns:
            Flat ``dict[str, Any]`` matching the ``isa_work_order`` RAW schema.
        """
        log.debug(
            "Mapping work order fiix_id=%d external_id=%s",
            work_order.fiix_id,
            work_order.external_id,
        )

        wo_id = _parse_wo_id(work_order.description, work_order.fiix_id)
        wo_prefix = _description_prefix(work_order.description)

        return {
            # ── RAW row key ───────────────────────────────────────────────
            # Composite key: strDescription prefix + '_' + Fiix numeric id
            # e.g. "WO_CHI_00 | Investigate ..." + 173959783 → "WO_CHI_00_173959783"
            "key": wo_id,

            # ── Identity ─────────────────────────────────────────────────
            "externalId": wo_id,
            "work_order_id": wo_id,
            # strDescription prefix + '_' + strCode
            # e.g. "WO_CHI_00" + "325" → "WO_CHI_00_325"
            "work_order_number": f"{wo_prefix}_{work_order.work_order_number}" if wo_prefix and work_order.work_order_number else work_order.work_order_number,

            # strDescription title part (after '|') populates both display name and description.
            # e.g. "WO_CHI_00 | Investigate a problem..." -> "Investigate a problem..."
            "work_order_name": _parse_wo_title(work_order.description),
            "description": _parse_wo_title(work_order.description),

            # -- Classification ────────────────────────────────────────────
            # work_type: from extraFields.dv_intMaintenanceTypeID (e.g. "Preventive")
            "work_type": work_order.maintenance_type_label,

            # work_status: from extraFields.dv_intWorkOrderStatusID (e.g. "Closed, Completed")
            # Falls back to the numeric status_id string if the label is absent.
            "work_status": (
                work_order.status_label
                or (str(work_order.status_id) if work_order.status_id is not None else None)
            ),

            # ── Timestamps ────────────────────────────────────────────────
            # Serialised as "YYYY-MM-DDTHH:MM:SSZ" to match the Spark SQL
            # pattern in work_order_tr.Transformation.sql:
            #   to_timestamp(col, "yyyy-MM-dd'T'HH:mm:ss'Z'")
            "planned_start_time": _fmt_ts(work_order.planned_start_time),
            "planned_end_time": _fmt_ts(work_order.planned_end_time),
            # actual_start_time: Fiix creation time used as the actual start (dtmDateCreated).
            "actual_start_time": _fmt_ts(work_order.created_time),
            "actual_end_time": _fmt_ts(work_order.actual_end_time),
            # These columns extend the seed schema; the current SQL does not
            # read them but future enhancements may use them.
            "created_time": _fmt_ts(work_order.created_time),
            "last_updated_time": _fmt_ts(work_order.last_updated_time),

            # ── Asset / equipment references ──────────────────────────────
            # asset_externalId: extracted from strAssets parenthesised suffix
            # e.g. "CHI Oven 1 Unit (UNIT_CHI_BAKE)" -> "UNIT_CHI_BAKE"
            "asset_externalId": _parse_asset_ext_id(work_order.asset_name),

            # equipment_externalId = Asset.strCode resolved via intAssetParentID lookup.
            "equipment_externalId": asset_code,
            # production_order_externalId: PROD-{site_code}-{strCode}
            # e.g. description prefix "WO_CHI_00" + strCode "325" -> "PROD-CHI-325"
            "production_order_externalId": (
                f"PROD-{_parse_site_code(work_order.description)}-{work_order.work_order_number}"
                if _parse_site_code(work_order.description) and work_order.work_order_number
                else None
            ),

            # ── Personnel ─────────────────────────────────────────────────
            # strAssignedUsers contains the personnel external ID (e.g. "PERS_COOKIE_002").
            "assigned_personnel_externalId": work_order.assigned_user_names,

            # ── Optional helper columns ───────────────────────────────────
            # Not read by the current SQL transformation but included for
            # traceability and future enhancements.
            "asset_name": work_order.asset_name,
            "assigned_person_name": work_order.assigned_user_names,
            "completion_notes": work_order.completion_notes,
        }

    def to_raw_rows(self, work_orders: list[WorkOrder]) -> list[dict[str, Any]]:
        """Map a batch of work orders to a list of RAW row dicts.

        Preserves input order. Each item is independently mapped by
        :meth:`to_raw_row`.

        Args:
            work_orders: Work orders to map.

        Returns:
            List of RAW row dicts in the same order as *work_orders*.
        """
        rows = [self.to_raw_row(wo) for wo in work_orders]
        log.debug("Mapped %d work order(s) to RAW rows.", len(rows))
        return rows
