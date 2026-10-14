with work_orders as (
  select 
    externalId,work_order_id,work_order_number 
  from 
    cdf_data_models('xws_user16_spc_dm_isa_mfg', 'xws_user16_dm_isa_mfg', 'v1', 'WorkOrder')
),
wo_ts as (
  SELECT
    cast(work_orders.externalId as string) AS externalId,
    collect_set(node_reference('xws_user16_spc_inst_isa_mfg', concat('xws_user16_', cast(time_series.externalId as string)))) AS timeSeries
  FROM `xws_user16_rawdb_isa_mfg`.`isa_timeseries` time_series
  JOIN `xws_user16_rawdb_isa_mfg`.`isa_work_order` work_orders
    ON cast(time_series.work_order_id as string) = cast(work_orders.work_order_id as string)
   AND cast(time_series.equipment_externalId as string) = cast(work_orders.equipment_externalId as string)
  WHERE time_series.work_order_id IS NOT NULL AND time_series.work_order_id <> ''
  GROUP BY work_orders.externalId
)
select 
  work_orders.externalId as externalId,
  work_orders.work_order_id as work_order_id,
  work_orders.work_order_number as work_order_number,
  wo_ts.timeSeries as timeSeries
from work_orders left join wo_ts on work_orders.externalId=wo_ts.externalId
