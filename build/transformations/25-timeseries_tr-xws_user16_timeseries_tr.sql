WITH src AS (
  SELECT
    -- RAW keeps unprefixed TimeSeries IDs; the transformation applies userPrefix to match deployed TimeSeries resources.
    concat('xws_user16_', cast(externalId as string)) AS externalId,
    cast(name as string)               AS name,
    cast(description as string)        AS description,
    if(try_get_unit(`unit`) IS NOT NULL, node_reference('cdf_cdm_units', try_get_unit(`unit`)), NULL) as unit,
    `unit` as sourceUnit,
    CASE lower(isString)
      WHEN 'true' THEN 'string'
      ELSE 'numeric'
    END AS type,
    array(node_reference('xws_user16_spc_inst_isa_mfg', `asset_externalId`)) as assets,
    array(node_reference('xws_user16_spc_inst_isa_mfg', `equipment_externalId`)) as equipment,
    CASE lower(isStep)
      WHEN 'true' THEN true
      ELSE false
    END AS isStep
  FROM `xws_user16_rawdb_isa_mfg`.`isa_timeseries`
)
SELECT
  externalId,
  name,
  description,
  unit,
  sourceUnit,
  type,
  isStep,
  assets,
  equipment
FROM src
