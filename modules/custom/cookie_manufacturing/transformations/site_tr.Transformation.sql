select
  externalId as externalId,
  externalId as site_id,
  name as site_name,
  node_reference('{{ isaInstanceSpace }}', parent_externalId) as enterprise
from `{{ rawDatabaseName }}`.`isa_asset`
where 
  asset_specific = 'Site'

