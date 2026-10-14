SELECT
  cast(externalId as string) AS externalId,
  cast(personnel_id as string) AS personnel_id,
  cast(name as string) AS name,
  cast(role as string) AS role,
  CASE
    WHEN site_externalId IS NULL OR site_externalId = '' THEN NULL
    ELSE node_reference('xws_user16_spc_inst_isa_mfg', cast(site_externalId as string))
  END AS site
FROM `xws_user16_rawdb_isa_mfg`.`isa_personnel`

