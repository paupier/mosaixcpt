"""Upload mapped Work Order rows to CDF RAW.

Responsibilities
----------------
- Configure a :class:`CogniteClient` from the root .env credentials.
- Accept pre-mapped RAW row dicts produced by :class:`~fiix.mapper.WorkOrderMapper`.
- Upload rows to the ``isa_work_order`` RAW table in configurable batches.
- Retry failed batches with exponential back-off.
- Return :class:`UploadResult` statistics after every upload call.

No Fiix API calls. No mapping logic.

Credential loading
------------------
Reads from the same root ``.env`` file used by the CDF Toolkit CLI and the
existing admin scripts.  Credential env-var names are resolved in this order
so the uploader works with both the standard CDF Toolkit format and the
existing project convention:

+-------------------------------+-------------------------------------------+
| CDF Toolkit (primary)         | Existing project convention (fallback)    |
+===============================+===========================================+
| ``IDP_CLIENT_ID``             | ``FTDM_CLIENT_ID``                        |
+-------------------------------+-------------------------------------------+
| ``IDP_CLIENT_SECRET``         | ``FTDM_CLIENT_SECRET``                    |
+-------------------------------+-------------------------------------------+
| ``IDP_TOKEN_URL``             | default: DataMosaix Auth0 URL             |
+-------------------------------+-------------------------------------------+
| ``CDF_PROJECT``               | default: ``ptec-04``                      |
+-------------------------------+-------------------------------------------+
| ``CDF_CLUSTER``               | default: ``westeurope-1``                 |
+-------------------------------+-------------------------------------------+
| ``CDF_RAW_DATABASE``          | required — matches ``rawDatabaseName`` in |
|                               | ``config.prod.yaml``                      |
+-------------------------------+-------------------------------------------+
| ``CDF_RAW_TABLE``             | default: ``isa_work_order``               |
+-------------------------------+-------------------------------------------+
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from cognite.client import CogniteClient
from cognite.client.config import ClientConfig
from cognite.client.credentials import OAuthClientCredentials
from cognite.client.data_classes import RowWrite
from cognite.client.exceptions import CogniteAPIError

from .exceptions import FiixError
from .logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants — match the existing admin/deleteResourcesByPrefixREST.py values
# so this uploader is compatible out of the box with the same .env file.
# ---------------------------------------------------------------------------
_DEFAULT_PROJECT: str = "ptec-04"
_DEFAULT_CLUSTER: str = "westeurope-1"
_DEFAULT_TOKEN_URL: str = "https://datamosaix-prod.us.auth0.com/oauth/token"
_DEFAULT_RAW_TABLE: str = "isa_work_order"
_DEFAULT_BATCH_SIZE: int = 1_000
_DEFAULT_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 2.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CdfUploadConfig:
    """Immutable CDF connection and upload settings.

    Construct via :meth:`from_env` to validate all required variables at
    startup rather than at first upload.

    Attributes:
        project:      CDF project name.
        cluster:      CDF cluster name (e.g. ``westeurope-1``).
        token_url:    OAuth2 token endpoint URL.
        client_id:    OAuth2 client ID.
        client_secret: OAuth2 client secret.
        raw_database: Target RAW database name (must exist or ``ensure_parent``
                      will create it on first upload).
        raw_table:    Target RAW table name (default: ``isa_work_order``).
        batch_size:   Maximum rows per API call (default: 1 000).
        max_retries:  Retry attempts per failed batch (default: 3).
    """

    project: str
    cluster: str
    token_url: str
    client_id: str
    client_secret: str
    raw_database: str
    raw_table: str = field(default=_DEFAULT_RAW_TABLE)
    batch_size: int = field(default=_DEFAULT_BATCH_SIZE)
    max_retries: int = field(default=_DEFAULT_MAX_RETRIES)

    @classmethod
    def from_env(cls) -> "CdfUploadConfig":
        """Build a :class:`CdfUploadConfig` from environment variables.

        Credential env vars are checked in priority order:
        ``IDP_CLIENT_ID`` → ``FTDM_CLIENT_ID`` (and same for the secret).

        ``CDF_RAW_DATABASE`` is required because it is user-specific
        (matches ``rawDatabaseName`` in ``config.prod.yaml``).

        Returns:
            Validated :class:`CdfUploadConfig` instance.

        Raises:
            FiixError: If any required variable is absent or empty.
        """
        client_id = (
            os.getenv("IDP_CLIENT_ID")
            or os.getenv("FTDM_CLIENT_ID")
            or ""
        )
        client_secret = (
            os.getenv("IDP_CLIENT_SECRET")
            or os.getenv("FTDM_CLIENT_SECRET")
            or ""
        )
        raw_database = os.getenv("CDF_RAW_DATABASE", "")

        missing: list[str] = []
        if not client_id:
            missing.append("IDP_CLIENT_ID (or FTDM_CLIENT_ID)")
        if not client_secret:
            missing.append("IDP_CLIENT_SECRET (or FTDM_CLIENT_SECRET)")
        if not raw_database:
            missing.append("CDF_RAW_DATABASE")
        if missing:
            raise FiixError(
                f"Missing required CDF upload environment variables: "
                f"{', '.join(missing)}. Add them to the root .env file."
            )

        return cls(
            project=os.getenv("CDF_PROJECT", _DEFAULT_PROJECT),
            cluster=os.getenv("CDF_CLUSTER", _DEFAULT_CLUSTER),
            token_url=os.getenv("IDP_TOKEN_URL", _DEFAULT_TOKEN_URL),
            client_id=client_id,
            client_secret=client_secret,
            raw_database=raw_database,
            raw_table=os.getenv("CDF_RAW_TABLE", _DEFAULT_RAW_TABLE),
        )


# ---------------------------------------------------------------------------
# Upload statistics
# ---------------------------------------------------------------------------


@dataclass
class UploadResult:
    """Statistics returned by :meth:`WorkOrderUploader.upload`.

    Attributes:
        rows_attempted:  Total rows passed to :meth:`~WorkOrderUploader.upload`.
        rows_uploaded:   Rows successfully written to CDF RAW.
        batches_sent:    Number of batch API calls that succeeded.
        batches_failed:  Number of batch API calls that failed after all retries.
    """

    rows_attempted: int = 0
    rows_uploaded: int = 0
    batches_sent: int = 0
    batches_failed: int = 0

    @property
    def success(self) -> bool:
        """``True`` when every attempted row was uploaded successfully."""
        return self.batches_failed == 0 and self.rows_uploaded == self.rows_attempted

    @property
    def success_rate(self) -> float:
        """Fraction of rows uploaded (0.0–1.0)."""
        if self.rows_attempted == 0:
            return 1.0
        return self.rows_uploaded / self.rows_attempted

    def __str__(self) -> str:
        return (
            f"UploadResult("
            f"rows={self.rows_uploaded}/{self.rows_attempted}, "
            f"batches_ok={self.batches_sent}, "
            f"batches_failed={self.batches_failed})"
        )


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------


class WorkOrderUploader:
    """Uploads pre-mapped ``isa_work_order`` RAW rows to CDF.

    Must be used as a context manager so the :class:`CogniteClient`
    lifecycle is managed correctly::

        config = CdfUploadConfig.from_env()
        with WorkOrderUploader(config) as uploader:
            result = uploader.upload(mapped_rows)
            print(result)

    Args:
        config: Validated :class:`CdfUploadConfig` instance.
    """

    def __init__(self, config: CdfUploadConfig) -> None:
        self._config = config
        self._client: CogniteClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "WorkOrderUploader":
        self._client = self._build_client()
        log.info(
            "WorkOrderUploader ready — project=%s cluster=%s "
            "database=%s table=%s batch_size=%d",
            self._config.project,
            self._config.cluster,
            self._config.raw_database,
            self._config.raw_table,
            self._config.batch_size,
        )
        return self

    def __exit__(self, *_: object) -> None:
        self._client = None
        log.info("WorkOrderUploader closed.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self, rows: list[dict[str, Any]]) -> UploadResult:
        """Upload mapped RAW row dicts to the ``isa_work_order`` table.

        Rows are split into batches of :attr:`~CdfUploadConfig.batch_size`.
        Each batch is retried up to :attr:`~CdfUploadConfig.max_retries` times
        with exponential back-off on failure.  A permanently failing batch is
        counted in :attr:`~UploadResult.batches_failed` and skipped so the
        remaining batches can still be uploaded.

        The ``key`` entry in every row dict is promoted to the CDF RAW row key
        and removed from the column payload.  ``None`` values are omitted so
        the stored JSON stays clean; the existing SQL transformation treats
        absent columns as ``NULL``.

        Args:
            rows: List of dicts produced by
                  :meth:`~fiix.mapper.WorkOrderMapper.to_raw_rows`.
                  Each dict must contain a non-empty ``"key"`` entry.

        Returns:
            :class:`UploadResult` with counts for the upload operation.

        Raises:
            FiixError: If called outside a ``with`` block.
        """
        if self._client is None:
            raise FiixError(
                "WorkOrderUploader must be used as a context manager. "
                "Use: with WorkOrderUploader(config) as uploader: ..."
            )

        if not rows:
            log.info("upload() called with an empty list — nothing to do.")
            return UploadResult()

        result = UploadResult(rows_attempted=len(rows))
        batches = list(_chunk(rows, self._config.batch_size))

        log.info(
            "Upload starting: %d row(s) → %d batch(es) → %s / %s",
            len(rows),
            len(batches),
            self._config.raw_database,
            self._config.raw_table,
        )

        for batch_num, batch in enumerate(batches, start=1):
            ok = self._upload_batch_with_retry(batch, batch_num, len(batches))
            if ok:
                result.rows_uploaded += len(batch)
                result.batches_sent += 1
            else:
                result.batches_failed += 1

        log.info(
            "Upload complete: %s", result
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> CogniteClient:
        """Construct and return a configured :class:`CogniteClient`."""
        credentials = OAuthClientCredentials(
            token_url=self._config.token_url,
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            scopes=["user_impersonation"],
        )
        cfg = ClientConfig(
            client_name="fiix-work-order-uploader",
            project=self._config.project,
            cluster=self._config.cluster,
            credentials=credentials,
        )
        return CogniteClient(cfg)

    def _upload_batch_with_retry(
        self,
        batch: list[dict[str, Any]],
        batch_num: int,
        total_batches: int,
    ) -> bool:
        """Attempt to upload *batch*, retrying on transient failure.

        Args:
            batch:         Subset of mapped row dicts.
            batch_num:     1-based index of this batch (for log messages).
            total_batches: Total number of batches (for log messages).

        Returns:
            ``True`` if the batch was uploaded successfully, ``False`` after
            exhausting all retry attempts.
        """
        row_writes = _to_row_writes(batch)
        if not row_writes:
            log.warning("Batch %d/%d produced zero valid RowWrite objects — skipped.", batch_num, total_batches)
            return False

        # Narrow the type so the loop body below has a concrete CogniteClient.
        client = self._client
        assert client is not None, "_upload_batch_with_retry requires an open client"

        for attempt in range(1, self._config.max_retries + 1):
            try:
                client.raw.rows.insert(
                    db_name=self._config.raw_database,
                    table_name=self._config.raw_table,
                    row=row_writes,
                    ensure_parent=True,
                )
                log.info(
                    "Batch %d/%d uploaded successfully (%d row(s)).",
                    batch_num,
                    total_batches,
                    len(row_writes),
                )
                return True

            except CogniteAPIError as exc:
                log.warning(
                    "Batch %d/%d — attempt %d/%d — CogniteAPIError %s: %s",
                    batch_num,
                    total_batches,
                    attempt,
                    self._config.max_retries,
                    exc.code,
                    exc.message,
                )
            except Exception as exc:
                log.warning(
                    "Batch %d/%d — attempt %d/%d — unexpected error: %s",
                    batch_num,
                    total_batches,
                    attempt,
                    self._config.max_retries,
                    exc,
                )

            if attempt < self._config.max_retries:
                backoff = _BACKOFF_BASE_SECONDS * attempt
                log.info(
                    "Retrying batch %d/%d in %.1fs (attempt %d → %d) …",
                    batch_num,
                    total_batches,
                    backoff,
                    attempt,
                    attempt + 1,
                )
                time.sleep(backoff)

        log.error(
            "Batch %d/%d permanently failed after %d attempt(s) — %d row(s) skipped.",
            batch_num,
            total_batches,
            self._config.max_retries,
            len(row_writes),
        )
        return False


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no I/O)
# ---------------------------------------------------------------------------


def _to_row_writes(batch: list[dict[str, Any]]) -> list[RowWrite]:
    """Convert a list of mapper row dicts into :class:`RowWrite` objects.

    Rules
    -----
    - The ``"key"`` entry is promoted to the :class:`RowWrite` key field and
      removed from the column dict.
    - ``None`` values are omitted from columns so stored JSON stays clean.
      The existing SQL transformation treats absent columns as ``NULL``.
    - Rows with a missing or empty ``"key"`` are logged and skipped.

    Args:
        batch: List of dicts from :class:`~fiix.mapper.WorkOrderMapper`.

    Returns:
        List of :class:`RowWrite` objects ready for the CDF RAW API.
    """
    result: list[RowWrite] = []
    for row in batch:
        key: str = str(row.get("key") or "")
        if not key:
            log.warning("Skipping row with missing or empty 'key': %s", row)
            continue
        columns: dict[str, Any] = {
            k: v for k, v in row.items() if k != "key" and v is not None
        }
        result.append(RowWrite(key=key, columns=columns))
    return result


def _chunk(items: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive fixed-size sublists of *items*."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
