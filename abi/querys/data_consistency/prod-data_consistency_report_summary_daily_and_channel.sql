with daily_agg as (
    select 
        coalesce(sum(imps), 0) as imps,
        coalesce(sum(q4)) as q4
    from 
        "prod-ptbwa-da"."report_summary_daily"
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}'
        and inventorynm!=''
), channel_agg as (
    select 
        coalesce(sum(impcnt), 0) as imps,
        coalesce(sum(q4cnt)) as q4
    from 
        "prod-ptbwa-da"."report_summary_channel_daily"
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}'
)
select
     count(*) as error_cnt
 from   
    channel_agg
 cross join
    daily_agg
 where
    coalesce(channel_agg.imps, 0)-coalesce(daily_agg.imps, 0) != 0 
    or coalesce(channel_agg.q4, 0)-coalesce(daily_agg.q4, 0) != 0