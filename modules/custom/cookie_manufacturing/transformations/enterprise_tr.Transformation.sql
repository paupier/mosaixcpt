select
  externalId as externalId,
  externalId as enterprise_id,
  name as enterprise_name
from `{{ rawDatabaseName }}`.`isa_asset`
where 
  asset_specific = 'Enterprise'

