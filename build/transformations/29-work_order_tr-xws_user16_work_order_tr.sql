WITH base AS (
  SELECT
    CAST(externalId AS string) AS externalId,
    CAST(work_order_id AS string) AS work_order_id,
    CAST(work_order_number AS string) AS work_order_number,
    CAST(work_order_name AS string) AS work_order_name,
    CAST(description AS string) AS description,
    CAST(work_type AS string) AS work_type,
    CAST(work_status AS string) AS work_status,
    asset_externalId,
    to_timestamp(planned_start_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS planned_start_time_ts,
    to_timestamp(planned_end_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS planned_end_time_ts,
    to_timestamp(actual_start_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS actual_start_time_ts,
    to_timestamp(actual_end_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS actual_end_time_ts,
    CASE
      WHEN equipment_externalId IS NULL OR equipment_externalId = '' THEN NULL
      ELSE node_reference('xws_user16_spc_inst_isa_mfg', CAST(equipment_externalId AS string))
    END AS assigned_equipment_ref,
    CASE
      WHEN asset_externalId IS NULL OR asset_externalId = '' THEN NULL
      ELSE node_reference('xws_user16_spc_inst_isa_mfg', CAST(asset_externalId AS string))
    END AS asset_ref,
    CASE
      WHEN assigned_personnel_externalId IS NULL OR assigned_personnel_externalId = '' THEN NULL
      ELSE node_reference('xws_user16_spc_inst_isa_mfg', CAST(assigned_personnel_externalId AS string))
    END AS assigned_personnel_ref
  FROM `xws_user16_rawdb_isa_mfg`.`isa_work_order`
)

SELECT
  externalId,
  work_order_id,
  work_order_number,
  work_order_name AS name,
  description,
  work_type,
  work_status,
  planned_start_time_ts AS planned_start_time,
  planned_end_time_ts AS planned_end_time,
  actual_start_time_ts AS actual_start_time,
  actual_end_time_ts AS actual_end_time,
  actual_start_time_ts AS startTime,
  actual_end_time_ts AS endTime,
  planned_start_time_ts AS scheduledStartTime,
  planned_end_time_ts AS scheduledEndTime,
  CASE WHEN assigned_equipment_ref IS NULL THEN NULL ELSE ARRAY(assigned_equipment_ref) END AS equipment,
  CASE WHEN asset_ref IS NULL THEN NULL ELSE ARRAY(asset_ref) END AS assets,
  CASE WHEN assigned_personnel_ref IS NULL THEN NULL ELSE ARRAY(assigned_personnel_ref) END AS assigned_personnel
FROM base
