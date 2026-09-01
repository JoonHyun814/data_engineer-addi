INSERT INTO "prod-ptbwa-da"."report_summary_hour"
with abi_price as (
    select 
        req_id,
        element_at(array_sort(array_agg(price)), -1) as price
    from 
        "prod-ptbwa-dw"."ab_postback_log" as postback

    left join
        "ptbwa-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
		and TRY_CAST(price AS DOUBLE) IS NOT NULL
    group by 
        1
), abi_raw as (
    select 
        concat(postback.year, '-', postback.month, '-', postback.day, ' ', postback.hour, ':00:00') as DATETIME,
        postback.media_id as MEDIACD,
        cast(postback.cmp_no as int) as CMPNO,
        cast(postback.ag_no as int) as AGNO,
        cast(postback.creative_no as int) as CREATIVENO,
        COALESCE (
            (
                SELECT 
                    CAST(exchangerate AS DOUBLE)
                FROM 
                    "ptbwa-metadata"."exchangerate"
                WHERE
                    date_parse(cast(regd AS varchar), '%Y%m%d')  between date_parse('{exchange_first_day}', '%Y-%m-%d') and date_parse('{exchange_last_day}', '%Y-%m-%d')
                ORDER BY 
                    regd DESC 
                LIMIT 1
            ),
        0) as EXCHANGEWON,
        postback.req_id,
        postback.log_type,
        postback.is_cpvc,
        cast(abi_price.price as double) as price,
        year,
        month,
        day,
        hour
    from 
        "prod-ptbwa-dw"."ab_postback_log" as postback
    left join
        "ptbwa-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    left join 
        abi_price
    on
        abi_price.req_id=postback.req_id
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
), abi_report as (
    select 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO, 
        EXCHANGEWON,
        MEDIACD,
        count(distinct case when log_type='i' then req_id else null end) as IMPS,
        count(case when log_type='c' then req_id else null end) as CLICKS,
        sum(case when log_type='i' then CAST(price AS DOUBLE) else 0 end) as PAYMENT,
        count(distinct case when log_type!='e_i' and is_cpvc='1' then req_id else null end) as PAYMENTCNT,
        count(distinct case when log_type='v_firstQ' then req_id else null end) as Q1,
        count(distinct case when log_type='v_mid' then req_id else null end) as Q2,
        count(distinct case when log_type='v_thirdQ' then req_id else null end) as Q3,
        count(distinct case when log_type='v_complete' then req_id else null end) as Q4,
        count(case when log_type='e_i' then req_id else null end) as ERRORIMPS,
        sum(case when log_type='e_i' then CAST(price AS DOUBLE) else 0 end) as ERRORPAYMENT,
        year,
        month,
        day,
        hour
    from 
        abi_raw
    GROUP BY 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO, 
        EXCHANGEWON,
        MEDIACD,
        year,
        month,
        day,
        hour
), apm_raw as (
    select 
        distinct
            concat(postback.year, '-', postback.month, '-', postback.day, ' ', postback.hour, ':00:00') as DATETIME,
            req_id,
            cast(cmp_no as int) as CMPNO,
            cast(ag_no as int) as AGNO,
            cast(creative_no as int) as CREATIVENO,
            media_id as MEDIACD,
            COALESCE (
                (
                    SELECT 
                        CAST(exchangerate AS DOUBLE)
                    FROM 
                        "ptbwa-metadata"."exchangerate"
                    WHERE
                        date_parse(cast(regd AS varchar), '%Y%m%d')  between date_parse('{exchange_first_day}', '%Y-%m-%d') and date_parse('{exchange_last_day}', '%Y-%m-%d')
                    ORDER BY 
                        regd DESC 
                    LIMIT 1
                ),
            0) as EXCHANGEWON,
            log_type,
            is_cpvc,
            price,
            year,
            month,
            day,
            hour
    from 
        "prod-ptbwa-dw"."postback_log" as postback
    left join
        "ptbwa-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    where
        postback.req_id is not null
        and year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
), apm_report as (
    select 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        sum(case when log_type='i' then 1 else 0 end) as IMPS,
        sum(case when log_type='c' then 1 else 0 end) as CLICKS,
        sum(case when is_cpvc='1' then cast(price as double) else 0 end) as PAYMENT,
        sum(case when log_type!='e_i' then cast(is_cpvc as double) else 0 end) as PAYMENTCNT,
        sum(case when log_type='v_firstQ' then 1 else 0 end) as Q1,
        sum(case when log_type='v_mid' then 1 else 0 end) as Q2,
        sum(case when log_type='v_thirdQ' then 1 else 0 end) as Q3,
        sum(case when log_type='v_complete' then 1 else 0 end) as Q4,
        0 AS ERRORIMPS,
        0 AS ERRORPAYMENT,
        year,
        month,
        day,
        hour
    from 
        apm_raw
    GROUP BY 
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        year,
        month,
        day,
        hour
)
), nhn_price as (
    select
        req_id,
        element_at(array_sort(array_agg(price)), -1) as price
    from
        "prod-ptbwa-dw"."nhn_postback_log" as postback

    left join
        "ptbwa-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
		and TRY_CAST(price AS DOUBLE) IS NOT NULL
    group by
        1
), nhn_raw as (
    select
        concat(postback.year, '-', postback.month, '-', postback.day, ' ', postback.hour, ':00:00') as DATETIME,
        postback.media_id as MEDIACD,
        cast(postback.cmp_no as int) as CMPNO,
        cast(postback.ag_no as int) as AGNO,
        cast(postback.creative_no as int) as CREATIVENO,
        COALESCE (
            (
                SELECT
                    CAST(exchangerate AS DOUBLE)
                FROM
                    "ptbwa-metadata"."exchangerate"
                WHERE
                    date_parse(cast(regd AS varchar), '%Y%m%d')  between date_parse('{exchange_first_day}', '%Y-%m-%d') and date_parse('{exchange_last_day}', '%Y-%m-%d')
                ORDER BY
                    regd DESC
                LIMIT 1
            ),
        0) as EXCHANGEWON,
        postback.req_id,
        postback.log_type,
        postback.is_cpvc,
        cast(nhn_price.price as double) as price,
        year,
        month,
        day,
        hour
    from
        "prod-ptbwa-dw"."nhn_postback_log" as postback
    left join
        "ptbwa-metadata"."media"
    on
        media.mediacd=postback.media_id
        and media.logparsefg='Y'
    left join
        nhn_price
    on
        nhn_price.req_id=postback.req_id
    where
        year='{input_year}' and month='{input_month}' and day='{input_day}' and hour='{input_hour}'
        and cmp_no is not null and ag_no is not null and creative_no is not null
), nhn_report as (
    select
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        count(distinct case when log_type='i' then req_id else null end) as IMPS,
        count(case when log_type='c' then req_id else null end) as CLICKS,
        sum(case when log_type='i' then CAST(price AS DOUBLE) else 0 end) as PAYMENT,
        count(distinct case when log_type!='e_i' and is_cpvc='1' then req_id else null end) as PAYMENTCNT,
        count(distinct case when log_type='v_firstQ' then req_id else null end) as Q1,
        count(distinct case when log_type='v_mid' then req_id else null end) as Q2,
        count(distinct case when log_type='v_thirdQ' then req_id else null end) as Q3,
        count(distinct case when log_type='v_complete' then req_id else null end) as Q4,
        count(case when log_type='e_i' then req_id else null end) as ERRORIMPS,
        sum(case when log_type='e_i' then CAST(price AS DOUBLE) else 0 end) as ERRORPAYMENT,
        year,
        month,
        day,
        hour
    from
        nhn_raw
    GROUP BY
        DATETIME,
        CMPNO,
        AGNO,
        CREATIVENO,
        EXCHANGEWON,
        MEDIACD,
        year,
        month,
        day,
        hour
)
SELECT
    *
FROM
    abi_report
UNION ALL
SELECT
    *
FROM
    apm_report
UNION ALL
SELECT
    *
FROM
    nhn_report