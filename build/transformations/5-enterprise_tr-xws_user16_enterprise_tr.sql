select
  externalId as externalId,
  externalId as enterprise_id,
  name as enterprise_name
from `xws_user16_rawdb_isa_mfg`.`isa_asset`
where 
  asset_specific = 'Enterprise'

