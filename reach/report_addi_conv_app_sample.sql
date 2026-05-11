WITH cmp_list AS (
    SELECT DISTINCT 
        cmp_no
    FROM "prod_addi_conv"."addi_conv_info"
),
base AS (
    SELECT
        SUBSTR(third.created_at, 1, 10) AS dt, 
        third.tracker,
        third.cmp,
        third.event,
        third.ip,
        TRY_CAST(NULLIF(TRIM(third.revenue), '') AS DOUBLE) AS revenue
    FROM "prod-ptbwa-dw"."postback_thirdparty_log" third
    INNER JOIN cmp_list 
        ON cmp_list.cmp_no = TRY_CAST(NULLIF(TRIM(third.cmp), '') AS BIGINT)
    WHERE 1=1
        AND NULLIF(TRIM(third.ip), '') IS NOT NULL
        AND SUBSTR(third.created_at, 1, 10) = date_format(current_date - INTERVAL '1' DAY, '%Y-%m-%d')
),
daily AS (
    SELECT
        dt,
        tracker,
        cmp,
        event,
        COUNT(DISTINCT ip) AS daily_unique_ip,
        SUM(revenue) AS revenue
    FROM base
    GROUP BY 1, 2, 3, 4
)
SELECT
    dt AS Date,
    tracker,
    cmp,
    event,
    daily_unique_ip,
    revenue
FROM daily
ORDER BY 1, 2, 3, 4
;