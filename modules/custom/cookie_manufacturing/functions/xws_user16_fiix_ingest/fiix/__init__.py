"""Fiix CMMS integration package.

This package provides the Python foundation for synchronising Fiix data
into Cognite Data Fusion (CDF) RAW tables, from where existing SQL
transformations populate the ISA-95 data model.

Public surface
--------------
FiixConfig          Immutable configuration loaded from the root .env file.
FiixClient          Low-level signed HTTP client (use as a context manager).
FiixAuth            HMAC-SHA256 request signer.
WorkOrder           Immutable domain model for a Fiix Work Order.
get_logger          Package-scoped logger factory.
FiixError           Base exception for all Fiix errors.
FiixAuthError       Authentication / signing failure.
FiixAPIError        Non-2xx or malformed API response.
FiixConnectionError Network-level failure.
FiixRateLimitError  HTTP 429 rate-limit response.

Typical usage::

    from fiix import FiixConfig, FiixClient, WorkOrder
    from fiix.workorders import WorkOrderService

    config = FiixConfig.from_env()
    with FiixClient(config) as client:
        service = WorkOrderService(client)
        for wo in service.find_all():
            print(wo.external_id, wo.description)
"""

from .auth import FiixAuth
from .client import FiixClient
from .config import FiixConfig
from .exceptions import (
    FiixAPIError,
    FiixAuthError,
    FiixConnectionError,
    FiixError,
    FiixRateLimitError,
)
from .logger import get_logger
from .models import WorkOrder

__all__ = [
    "FiixAuth",
    "FiixClient",
    "FiixConfig",
    "WorkOrder",
    "FiixError",
    "FiixAuthError",
    "FiixAPIError",
    "FiixConnectionError",
    "FiixRateLimitError",
    "get_logger",
]
