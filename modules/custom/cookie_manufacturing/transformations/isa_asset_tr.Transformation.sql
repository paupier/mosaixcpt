WITH src AS (
  SELECT
    cast(externalId as string)         AS externalId,
    cast(name as string)               AS name,
    cast(parent_externalId as string)  AS parent_externalId,
    cast(erp_id as string)             AS erpId,
    cast(cmms_id as string)            AS cmmsId,
  	cast(description as string)        AS description
  FROM `{{ rawDatabaseName }}`.`isa_asset`
)
SELECT
  src.externalId,
  src.name,
  src.description,
  src.erpId,
  src.cmmsId,
  CASE
    WHEN src.parent_externalId IS NULL OR src.parent_externalId = '' THEN NULL
    ELSE node_reference('{{ isaInstanceSpace }}', src.parent_externalId)
  END
  AS parent
FROM src
