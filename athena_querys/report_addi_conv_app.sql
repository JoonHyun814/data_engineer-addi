INSERT INTO "prod_addi_conv"."report_addi_conv_app"
WITH cmp_list AS (
    SELECT
        cmp_no,
        MAX(app_mmp_cd) AS app_mmp_cd
    FROM "prod_addi_conv"."addi_conv_info"
    GROUP BY cmp_no
),
base AS (
    SELECT
        SUBSTR(third.created_at, 1, 10) AS dt,
        third.tracker,
        third.cmp,
        third.event,
        third.ip,
        cmp_list.app_mmp_cd,
        TRY_CAST(NULLIF(TRIM(third.revenue), '') AS DOUBLE) AS revenue
    FROM "prod-ptbwa-dw"."postback_thirdparty_log" third
    INNER JOIN cmp_list
        ON cmp_list.cmp_no = TRY_CAST(NULLIF(TRIM(third.cmp), '') AS BIGINT)
    WHERE 1=1
        AND NULLIF(TRIM(third.ip), '') IS NOT NULL
        AND (third.click_id IS NULL OR TRIM(third.click_id) <> 'TEST')
        AND SUBSTR(third.created_at, 1, 10) = '{date}'
),
daily AS (
    SELECT
        dt,
        tracker,
        cmp,
        event,
        app_mmp_cd,
        COUNT(DISTINCT ip) AS daily_unique_ip,
        COALESCE(SUM(revenue), 0) AS revenue
    FROM base
    GROUP BY 1, 2, 3, 4, 5
)
SELECT
    tracker,
    cmp,
    event,
    dt,
    daily_unique_ip,
    revenue,
    app_mmp_cd,
    SUBSTR(dt, 1, 4) AS year,
    SUBSTR(dt, 6, 2) AS month,
    SUBSTR(dt, 9, 2) AS day
FROM daily
ORDER BY dt, tracker, cmp, event;
