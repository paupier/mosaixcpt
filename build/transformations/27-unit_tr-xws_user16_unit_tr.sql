select
  externalId as externalId,
  externalId as unit_id,
  name as unit_name,
  node_reference('xws_user16_spc_inst_isa_mfg', parent_externalId) as process_cell
from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
  asset_specific = 'Unit'

