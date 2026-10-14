select
  externalId as externalId,
  externalId as area_id,
  name as area_name,
  node_reference('{{ isaInstanceSpace }}', parent_externalId) as site
  from `{{ rawDatabaseName }}`.`isa_asset`
where 
	asset_specific = 'Area'