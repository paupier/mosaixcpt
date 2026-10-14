WITH src AS (
  SELECT
  concat('xws_user16_', externalId) as externalId,
  	array(node_reference('xws_user16_spc_inst_isa_mfg', `asset_externalId`)) as assets,
    CAST(name AS STRING) AS name,
    CAST(directory AS STRING) AS directory,
    CAST(mimeType AS STRING) AS mimeType
  FROM `xws_user16_rawdb_isa_mfg`.`isa_file`
)
SELECT
  externalId,
  name,
  directory,
  mimeType,
  assets
FROM src
