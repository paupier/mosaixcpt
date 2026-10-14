WITH src AS (
  SELECT
    cast(externalId as string)         AS externalId,
    cast(name as string)               AS name,
    cast(parent_externalId as string)  AS parent_externalId,
    cast(erp_id as string)             AS erpId,
    cast(cmms_id as string)            AS cmmsId,
  	cast(description as string)        AS description
  FROM `xws_user16_rawdb_isa_mfg`.`isa_asset`
)
SELECT
  src.externalId,
  src.name,
  src.description,
  src.erpId,
  src.cmmsId,
  CASE
    WHEN src.parent_externalId IS NULL OR src.parent_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', src.parent_externalId)
  END
  AS parent
FROM src
