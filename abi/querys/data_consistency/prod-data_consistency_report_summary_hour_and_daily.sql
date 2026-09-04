with hourly_agg as (
    select 
        coalesce(sum(imps), 0) as imps,
        coalesce(sum(clicks), 0) as clicks,
        coalesce(sum(q1)) as q1,
        coalesce(sum(q2)) as q2,
        coalesce(sum(q3)) as q3,
        coalesce(sum(q4)) as q4
    from 
        "prod-ptbwa-da"."report_summary_hour"
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}'
), daily_agg as (
    select 
        coalesce(sum(imps), 0) as imps,
        coalesce(sum(clicks), 0) as clicks,
        coalesce(sum(q1)) as q1,
        coalesce(sum(q2)) as q2,
        coalesce(sum(q3)) as q3,
        coalesce(sum(q4)) as q4
    from 
        "prod-ptbwa-da"."report_summary_daily"
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}'
)
select
     count(*) as error_cnt
 from   
    hourly_agg
 cross join
    daily_agg
 where
    coalesce(hourly_agg.imps, 0)-coalesce(daily_agg.imps, 0) != 0 
    or coalesce(hourly_agg.clicks, 0)-coalesce(daily_agg.clicks, 0) != 0
    or coalesce(hourly_agg.q1, 0)-coalesce(daily_agg.q1, 0) != 0
    or coalesce(hourly_agg.q2, 0)-coalesce(daily_agg.q2, 0) != 0
    or coalesce(hourly_agg.q3, 0)-coalesce(daily_agg.q3, 0) != 0
    or coalesce(hourly_agg.q4, 0)-coalesce(daily_agg.q4, 0) != 0