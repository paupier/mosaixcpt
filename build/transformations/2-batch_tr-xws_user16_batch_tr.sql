WITH work_order_refs AS (
  SELECT
    CAST(work_order_id AS string) AS work_order_id,
    COLLECT_SET(node_reference('xws_user16_spc_inst_isa_mfg', CAST(externalId AS string))) AS work_orders
  FROM `xws_user16_rawdb_isa_mfg`.`isa_work_order`
  WHERE work_order_id IS NOT NULL AND work_order_id <> ''
  GROUP BY work_order_id
)
SELECT
  CAST(batch.batch_id AS string) AS externalId,
  CAST(batch.batch_id AS string) AS batch_id,
  CAST(batch.batch_number AS string) AS batch_number,
  CAST(batch.batch_state AS string) AS batch_state,
  CAST(batch.batch_size AS double) AS batch_size,
  CAST(batch.batch_size_unit AS string) AS batch_size_unit,
  TO_TIMESTAMP(batch.start_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS startTime,
  TO_TIMESTAMP(batch.end_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS endTime,
  TO_TIMESTAMP(batch.start_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS scheduledStartTime,
  TO_TIMESTAMP(batch.end_time, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS scheduledEndTime,
  CASE
    WHEN batch.recipe_externalId IS NULL OR batch.recipe_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', CAST(batch.recipe_externalId AS string))
  END AS recipe,
  CASE
    WHEN batch.site_externalId IS NULL OR batch.site_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', CAST(batch.site_externalId AS string))
  END AS site,
  work_order_refs.work_orders AS work_orders
FROM `xws_user16_rawdb_isa_mfg`.`isa_batch` batch
LEFT JOIN work_order_refs
  ON CAST(batch.primary_work_order_externalId AS string) = work_order_refs.work_order_id
