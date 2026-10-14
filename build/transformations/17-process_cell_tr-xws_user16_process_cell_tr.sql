select
  externalId as externalId,
  externalId as process_cell_id,
  name as process_cell_name,
  node_reference('xws_user16_spc_inst_isa_mfg', parent_externalId) as area
from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
  asset_specific = 'ProcessCell'

