select
  externalId as externalId,
  externalId as area_id,
  name as area_name,
  node_reference('xws_user16_spc_inst_isa_mfg', parent_externalId) as site
  from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
	asset_specific = 'Area'