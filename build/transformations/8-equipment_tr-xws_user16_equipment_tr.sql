WITH src AS (
  SELECT
    cast(externalId as string)         AS externalId,
    cast(equipment_id as string)       AS equipment_id,
    cast(equipment_name as string)     AS name,
    cast(description as string)        AS description,
    cast(unit_externalId as string)    AS unit_externalId,
    cast(manufacturer as string)       AS manufacturer,
    cast(model as string)              AS model,
    cast(serial_number as string)      AS serial_number,
    node_reference('xws_user16_spc_inst_isa_mfg', cast(asset_externalId as string)) AS asset
  FROM `xws_user16_rawdb_isa_mfg`.`isa_equipment`
),
files as (
  SELECT
  CAST(equipment_externalId AS STRING) AS externalId,
  COLLECT_SET(node_reference('xws_user16_spc_inst_isa_mfg', concat('xws_user16_', externalId) )) AS files
FROM `xws_user16_rawdb_isa_mfg`.`isa_file`
WHERE equipment_externalId IS NOT NULL AND equipment_externalId <> ''
GROUP BY equipment_externalId
)
SELECT
  src.externalId,
  src.equipment_id,
  src.name,
  src.description,
  CASE
    WHEN src.unit_externalId IS NULL OR src.unit_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', src.unit_externalId)
  END AS unit,
  src.manufacturer,
  src.model,
  src.serial_number,
  src.asset,
  files.files
FROM src left join files on src.externalId = files.externalId
