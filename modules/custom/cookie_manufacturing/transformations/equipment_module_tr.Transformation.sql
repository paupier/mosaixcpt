select
  externalId as externalId,
  externalId as equipment_module_id,
  name as equipment_module_name,
  node_reference('{{ isaInstanceSpace }}', parent_externalId) as unit
from `{{ rawDatabaseName }}`.`isa_asset`
where 
  asset_specific = 'EquipmentModule'

