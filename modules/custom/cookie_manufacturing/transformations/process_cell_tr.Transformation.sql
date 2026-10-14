select
  externalId as externalId,
  externalId as process_cell_id,
  name as process_cell_name,
  node_reference('{{ isaInstanceSpace }}', parent_externalId) as area
from `{{ rawDatabaseName }}`.`isa_asset`
where 
  asset_specific = 'ProcessCell'

