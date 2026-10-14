SELECT
  cast(externalId as string) AS externalId,
  cast(control_module_name as string) AS name,
  cast(description as string) as description,
  CASE
    WHEN equipment_module_externalId IS NULL OR equipment_module_externalId = '' THEN NULL
    ELSE node_reference('{{ isaInstanceSpace }}', cast(equipment_module_externalId as string))
  END AS parent
FROM `{{ rawDatabaseName }}`.`isa_control_module`
