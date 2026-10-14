SELECT
  cast(externalId as string) AS externalId,
  cast(control_module_id as string) AS control_module_id,
  cast(control_module_name as string) AS name,
  cast(description as string) as description,
  cast(control_type as string) AS control_type,
  cast(controller_address as string) AS controller_address,
  CASE
    WHEN equipment_module_externalId IS NULL OR equipment_module_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', cast(equipment_module_externalId as string))
  END AS equipment_module
FROM `xws_user16_rawdb_isa_mfg`.`isa_control_module`
