WITH base AS (
  SELECT
    CAST(product_request_id AS string) AS product_request_id,
    CAST(product_request_id AS string) AS external_id,
    CAST(request_number AS string) AS request_number,
    CAST(product_request_name AS string) AS product_request_name,
    CAST(description AS string) AS description,
    -- CAST(source_system AS string) AS source_system,
    CAST(NULLIF(quantity_requested, '') AS double) AS quantity_requested,
    CAST(quantity_unit AS string) AS quantity_unit,
    CAST(NULLIF(priority, '') AS int) AS priority,
    TO_TIMESTAMP(due_date, "yyyy-MM-dd'T'HH:mm:ss'Z'") AS due_date,
    CAST(request_status AS string) AS request_status,
    SPLIT(COALESCE(unit_externalIds, ''), '\\|') AS unit_ids,
    SPLIT(COALESCE(file_externalIds, ''), '\\|') AS file_ids,
    SPLIT(COALESCE(work_order_externalIds, ''), '\\|') AS work_order_ids
  FROM `xws_user16_rawdb_isa_mfg`.`isa_product_request`
),
request_work_order_ids AS (
  SELECT
    base.external_id,
    TRIM(work_order_id) AS work_order_id
  FROM base
  LATERAL VIEW EXPLODE(base.work_order_ids) exploded_work_orders AS work_order_id
  WHERE TRIM(work_order_id) <> ''
),
work_order_refs AS (
  SELECT
    request_work_order_ids.external_id AS product_request_external_id,
    FILTER(
      COLLECT_SET(node_reference('xws_user16_spc_inst_isa_mfg', CAST(work_orders.externalId AS string))),
      x -> x IS NOT NULL
    ) AS work_orders
  FROM request_work_order_ids
  LEFT JOIN `xws_user16_rawdb_isa_mfg`.`isa_work_order` work_orders
    ON request_work_order_ids.work_order_id = CAST(work_orders.work_order_id AS string)
  GROUP BY request_work_order_ids.external_id
)
SELECT
  base.external_id AS externalId,
  base.product_request_id,
  base.request_number,
  base.product_request_name AS name,
  base.description,
  -- source_system AS source,
  base.quantity_requested,
  base.quantity_unit,
  base.priority,
  base.due_date,
  base.request_status,
  FILTER(
    TRANSFORM(
      base.unit_ids,
      x -> CASE WHEN TRIM(x) = '' THEN NULL ELSE node_reference('xws_user16_spc_inst_isa_mfg', TRIM(x)) END
    ),
    x -> x IS NOT NULL
  ) AS unit,
  FILTER(
    TRANSFORM(
      base.file_ids,
      x -> CASE WHEN TRIM(x) = '' THEN NULL ELSE node_reference('xws_user16_spc_inst_isa_mfg', concat('xws_user16_', TRIM(x))) END
    ),
    x -> x IS NOT NULL
  ) AS files,
  work_order_refs.work_orders AS work_orders
FROM base
LEFT JOIN work_order_refs
  ON base.external_id = work_order_refs.product_request_external_id
