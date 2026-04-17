-- CREATE TABLE "prod-ptbwa-da"."report_summary_reach_daily"
--  WITH (
--       format = 'Parquet',
--       external_location = 's3://ptbwa-da/prod/report_summary_reach_daily/',
--       partitioned_by = ARRAY['year', 'month', 'day']
--   ) AS
 
INSERT INTO "prod-ptbwa-da"."report_summary_reach_daily"

with acp as (
    select
        *
    from

        "ptbwa-metadata"."adcampaign"
    where
        '{input_date}' between cast(date_format(CAST(startdt AS timestamp), '%Y-%m-%d') as varchar) and cast(date_format(CAST(enddt AS timestamp), '%Y-%m-%d') as varchar)
        and logparsefg='Y'

), ag_min AS (
    SELECT
        MIN(startdt) AS min_startdt
    FROM
        acp
), reach_sum as (
    SELECT
        acp.agno AS AGNO,
        CASE
            WHEN SUM(REACH1) IS NULL THEN 0
            ELSE SUM(REACH1)
        END AS SUM_REACH1,
        CASE
            WHEN SUM(REACH2) IS NULL THEN 0
            ELSE SUM(REACH2)
        END AS SUM_REACH2,
        CASE
            WHEN SUM(REACH3) IS NULL THEN 0
            ELSE SUM(REACH3)
        END AS SUM_REACH3
    FROM
        "prod-ptbwa-da"."report_summary_reach_daily" as summary
    INNER JOIN
        acp
    on
        summary.agno=acp.agno
    WHERE
        date BETWEEN cast(date_format(CAST(startdt AS timestamp), '%Y-%m-%d') as varchar) AND cast(date_add('day', -1, cast('{input_date}' as date)) as varchar)
    GROUP BY 
        1
), reach_postback AS (
    SELECT
        CONCAT(year, '-', month, '-', day) AS day,
        cmp_no,
        ag_no,
        log_type,
        ifa,
    FROM 
		"prod-ptbwa-dw".postback_log
    inner join
        acp
    on
        acp.agno=postback_log.ag_no
    CROSS JOIN
        ag_min
    WHERE
        CONCAT(year, '-', month, '-', day) between cast(date_format(CAST(ag_min.min_startdt AS timestamp), '%Y-%m-%d') as varchar) and '{input_date}'
        -- AND ag_no IN ({','.join(adgroups)})
		and media_id in ('CX3NWBJED7HA', '9P4XDTQ81FPZ', '1FWMMFN3QDZ3')
		
	union all
	
	SELECT
        CONCAT(year, '-', month, '-', day) AS day,
        cmp_no,
        ag_no,
        log_type,
        ifa,
        CASE
            WHEN ag_no=688 THEN 'tv.anypoint.uplus.pp'
            WHEN ag_no=689 THEN 'tv.anypoint.kt'
            WHEN ag_no=691 THEN 'tv.anypoint.skb.pp'  
            WHEN ab_postback_log.media_id IN ('CX3NWBJED7HA', '9P4XDTQ81FPZ') THEN ab_postback_log.app_id 
            WHEN ab_postback_log.media_id='1FWMMFN3QDZ3' THEN 'test'
            ELSE NULL
        END AS INVENTORYNM
    FROM 
		"prod-ptbwa-dw".ab_postback_log
    inner join
        acp
    on
        acp.agno=ab_postback_log.ag_no
    CROSS JOIN
        ag_min
    WHERE
        CONCAT(year, '-', month, '-', day) between cast(date_format(CAST(ag_min.min_startdt AS timestamp), '%Y-%m-%d') as varchar) and '{input_date}'
        -- AND ag_no IN ({','.join(adgroups)})
		and ctv_media is not null and ctv_media!=''
	
	
), daily_counts AS (
    SELECT
        cmp_no,
        ag_no,
        CASE
            WHEN ag_no=688 THEN 'tv.anypoint.uplus.pp'
            WHEN ag_no=689 THEN 'tv.anypoint.kt'
            WHEN ag_no=691 THEN 'tv.anypoint.skb.pp'  
            WHEN media_id IN ('CX3NWBJED7HA', '9P4XDTQ81FPZ') THEN app_id 
            WHEN media_id='1FWMMFN3QDZ3' THEN 'test'
            ELSE NULL
        END AS INVENTORYNM,
        COUNT(CASE WHEN log_type = 'i' THEN 1 END) AS impressions,
        COUNT(CASE WHEN log_type = 'v_complete' THEN 1 END) AS views,
        COUNT(DISTINCT CASE WHEN log_type = 'v_complete' THEN ifa END) AS unique_reach
    FROM (
        SELECT
            cmp_no,
            ag_no,
            log_type,
            ifa,
            media_id,
            app_id
        FROM (
			select cmp_no, ag_no, log_type, ifa, media_id, app_id from "prod-ptbwa-dw".postback_log WHERE year='{input_year}' AND month='{input_month}' AND day='{input_day}' and media_id = 'CX3NWBJED7HA'
			union all
			select cmp_no, ag_no, log_type, ifa, media_id, app_id from "prod-ptbwa-dw".ab_postback_log WHERE year='{input_year}' AND month='{input_month}' AND day='{input_day}' and ctv_media is not null and ctv_media!=''
		 )
            
    )
    GROUP BY
        1, 2, 3
), daily_reach AS (
    SELECT
        day,
        cmp_no,
        ag_no,
        ifa,
        ROW_NUMBER() OVER (PARTITION BY ifa, ag_no, cmp_no ORDER BY day) AS view_rank
    FROM 
        reach_postback
    WHERE
        log_type = 'v_complete'
    ),
    daily_reach_aggregated AS (
    SELECT
        ag_no,
        cmp_no,
        COUNT(DISTINCT CASE WHEN view_rank = 1 THEN ifa END) AS view_rank_1,
        COUNT(DISTINCT CASE WHEN view_rank = 2 THEN ifa END) AS view_rank_2,
        COUNT(DISTINCT CASE WHEN view_rank = 3 THEN ifa END) AS view_rank_3
    FROM
        daily_reach
    GROUP BY
        1, 2
), final_cumulative_reach AS (
    SELECT
        ag_no,
        cmp_no,
        SUM(view_rank_1) OVER (PARTITION BY cmp_no, ag_no) AS cumulative_reach_1_plus,
        SUM(view_rank_2) OVER (PARTITION BY cmp_no, ag_no) AS cumulative_reach_2_plus,
        SUM(view_rank_3) OVER (PARTITION BY cmp_no, ag_no) AS cumulative_reach_3_plus
    FROM
        daily_reach_aggregated
)
SELECT
    '{input_date}' AS DATE,
    d.cmp_no AS CMPNO,
    d.ag_no AS AGNO,
    --  CASE
    --     WHEN d.unique_reach IS NULL THEN 0
    --     ELSE d.unique_reach
    -- END AS UNIQUEREACH, 
     coalesce(d.unique_reach, 0) as UNIQUEREACH,
    '' AS INVENTORYNM,
    coalesce(CAST(d.views AS DOUBLE)/nullif(d.unique_reach, 0), 0) as DAILYFREQUENCY,
    --  CASE
    --      WHEN CAST(d.views AS DOUBLE) / d.unique_reach IS NULL THEN 0
    --      ELSE CAST(d.views AS DOUBLE) / d.unique_reach
    --  END AS DAILYFREQUENCY,
    --CAST(d.views AS DOUBLE) / d.unique_reach AS DAILYFREQUENCY,
    fcr.cumulative_reach_1_plus-0 AS REACH1,
    fcr.cumulative_reach_2_plus-0 AS REACH2,
    fcr.cumulative_reach_3_plus-0 AS REACH3,
	'{input_year}' as year,
    '{input_month}' as month,
    '{input_day}' as day
FROM
    daily_counts d
JOIN
    final_cumulative_reach fcr
ON
    d.ag_no = fcr.ag_no
    AND d.cmp_no = fcr.cmp_no
LEFT JOIN
    reach_sum
ON
    reach_sum.agno=d.ag_no
    and reach_sum.agno=fcr.ag_no
ORDER BY 
    1, 2, 3, 4, 5