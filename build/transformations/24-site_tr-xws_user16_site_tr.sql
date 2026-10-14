select
  externalId as externalId,
  externalId as site_id,
  name as site_name,
  node_reference('xws_user16_spc_inst_isa_mfg', parent_externalId) as enterprise
from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
  asset_specific = 'Site'

