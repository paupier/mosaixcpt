select
  externalId as externalId,
  externalId as unit_id,
  name as unit_name,
  node_reference('{{ isaInstanceSpace }}', parent_externalId) as process_cell
from `{{ rawDatabaseName }}`.`isa_asset`
where 
  asset_specific = 'Unit'

