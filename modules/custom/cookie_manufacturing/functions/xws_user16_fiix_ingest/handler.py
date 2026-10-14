import os

from fiix.config import FiixConfig
from fiix.client import FiixClient
from fiix.scheduled_maintenance import ScheduledMaintenanceService
from fiix.workorders import WorkOrderService, WorkOrderFilter
from fiix.assets import AssetService
from fiix.mapper import WorkOrderMapper
from cognite.client.data_classes import RowWrite


def handle(data, client, secrets):
    # Inject Fiix secrets into env so FiixConfig.from_env() works
    os.environ["FIIX_SUBDOMAIN"] = secrets["fiix-subdomain"]
    os.environ["FIIX_APP_KEY"]   = secrets["fiix-app-key"]
    os.environ["FIIX_ACCESS_KEY"] = secrets["fiix-access-key"]
    os.environ["FIIX_SECRET_KEY"] = secrets["fiix-secret-key"]

    raw_database = secrets["cdf-raw-db"]  # KeyError if missing — fail fast
    fiix_user_code = secrets["fiix-user-code"]  # strCode of the ScheduledMaintenance to filter by
    raw_table = "isa_work_order"

    fiix_config = FiixConfig.from_env()
    mapper = WorkOrderMapper()
    rows = []

    with FiixClient(fiix_config) as fc:
        # Step 1: Fetch the ScheduledMaintenance linked to the user code
        sm_id = ScheduledMaintenanceService(fc).find_id_by_code(fiix_user_code)
        print(f"Fetched ScheduledMaintenance linked to strCode='{fiix_user_code}': id={sm_id}")

        # Step 2: fetch only work orders linked to that scheduled maintenance
        sm_filter = [WorkOrderFilter("intScheduledMaintenanceID", [sm_id])]
        asset_service = AssetService(fc)

        for wo in WorkOrderService(fc).find_all(filters=sm_filter):
            # Look up the Asset using strAssetIds as intAssetParentID
            # to resolve equipment_externalId = Asset.strCode
            asset_code: str | None = None
            if wo.asset_ids:
                first_id_str = wo.asset_ids.split(",")[0].strip()
                if first_id_str.isdigit():
                    assets = asset_service.find_by_parent_id(int(first_id_str))
                    if assets:
                        asset_code = assets[0].code
                        print(f"Fetched asset strCode='{asset_code}' for WO {wo.fiix_id}")

            rows.append(mapper.to_raw_row(wo, asset_code=asset_code))

    cdf_rows = [
        RowWrite(key=r["key"], columns={k: v for k, v in r.items() if k != "key"})
        for r in rows
    ]
    client.raw.rows.insert(
        db_name=raw_database,
        table_name=raw_table,
        row=cdf_rows,
        ensure_parent=True,
    )
    print(f"Uploaded {len(cdf_rows)} rows.")
