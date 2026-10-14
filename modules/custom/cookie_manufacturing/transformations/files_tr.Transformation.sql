WITH src AS (
  SELECT
  concat('{{ userPrefix }}', externalId) as externalId,
  	array(node_reference('{{ isaInstanceSpace }}', `asset_externalId`)) as assets,
    CAST(name AS STRING) AS name,
    CAST(directory AS STRING) AS directory,
    CAST(mimeType AS STRING) AS mimeType
  FROM `{{ rawDatabaseName }}`.`isa_file`
)
SELECT
  externalId,
  name,
  directory,
  mimeType,
  assets
FROM src
