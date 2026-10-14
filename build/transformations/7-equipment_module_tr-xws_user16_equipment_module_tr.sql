select
  externalId as externalId,
  externalId as equipment_module_id,
  name as equipment_module_name,
  node_reference('xws_user16_spc_inst_isa_mfg', parent_externalId) as unit
from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
  asset_specific = 'EquipmentModule'

