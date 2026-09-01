-- CREATE TABLE "prod-ptbwa-da"."report_summary_channel_daily"
-- WITH (
--     format = 'Parquet',
--     external_location = 's3://ptbwa-da/prod/report_summary_channel_daily/',
--     partitioned_by = ARRAY['year', 'month', 'day']
-- ) AS
INSERT INTO "prod-ptbwa-da"."report_summary_channel_daily"
WITH media as (
    select 
        mediacd
    from
        "ptbwa-metadata"."media"
    where
        lower(logparsefg) = 'y'
),apm_bid  AS (
    SELECT 
        req.req_id as req_id,
        case 
            when lower(req.app_bundle) like '%kt%' then 'KT'
            when lower(req.app_bundle) like '%uplus%' then 'LGU'
            when lower(req.app_bundle) like '%skb%' then 'SKB'
            else req.app_bundle
        end as carrier,
        req.content_id as contentid
    from
        "propfit"."bid_log"  as bid
    where (
			(year='{input_year}' and month='{input_month}' and day = '{input_day}')
			or (year='{input_yesterday_year}' and month='{input_yesterday_month}' and day = '{input_yesterday_day}')
		) and req.media_id in (select mediacd from media)
), apm_postback as (
    select 
        distinct
            concat(year, '-', month, '-', day) as date,
            req_id,
            cmp_no as cmpno, 
            ag_no as agno,
            media_id as mediacd,
            log_type,
            year,
            month,
            day
    from 
        "prod-ptbwa-dw"."postback_log" as postback
    where
        year='{input_year}' and month='{input_month}' and day = '{input_day}'
        and cmp_no is not null and ag_no is not null 
        and media_id in (select mediacd from media)
), apm_report as (
    select 
        postback.date,
        postback.cmpno,
        postback.agno,
        bid.carrier,
        bid.contentid,
        postback.mediacd,
        count(distinct postback.req_id) as reqidcnt,
        sum(case when postback.log_type='i' then 1 else 0 end) as impcnt,
        sum(case when postback.log_type='v_complete' then 1 else 0 end) as q4cnt,
        year,
        month,
        day
    from 
        apm_postback as postback
    left join
        apm_bid as bid
    on
        bid.req_id=postback.req_id
    group by 
        postback.date,
        bid.carrier,
        bid.contentid,
        postback.cmpno,
        postback.agno,
        postback.mediacd,
        year,
        month,
        day
), abi_postback as (
    select 
        distinct 
            concat(year, '-', month, '-', day) as date,
            req_id,
            media_id as mediacd,
            cmp_no as cmpno,
            ag_no as agno,
            log_type,
			case 
				when lower(ctv_media) like '%kt%' then 'KT'
				when lower(ctv_media) like '%lguplus%' then 'LGU'
				when lower(ctv_media) like '%skb%' then 'SKB'
				else ctv_media
			end as carrier,
            content_id as contentid,
            year,
            month,
            day
    from
        "prod-ptbwa-dw"."ab_postback_log" as postback
    where
        year='{input_year}' and month='{input_month}' and day = '{input_day}'
        and cmp_no is not null and ag_no is not null 
        and media_id in (select mediacd from media)
        and g_targetid='174297362776'
), abi_report as (
    select 
        date,
        cmpno,
        agno,
        carrier,
        contentid,
        mediacd,
        count(distinct req_id) as reqidcnt,
        sum(case when log_type='i' then 1 else 0 end) as impcnt,
        sum(case when log_type='v_complete' then 1 else 0 end) as q4cnt,
        year,
        month,
        day
    from 
        abi_postback
    group by 
        date,
        cmpno,
        agno,
        carrier,
        contentid,
        mediacd,
        year,
        month,
        day
)
select
    *
from
    abi_report
union all
select
    *
from
    apm_report
