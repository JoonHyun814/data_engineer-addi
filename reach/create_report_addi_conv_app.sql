CREATE TABLE "prod_addi_conv"."report_addi_conv_app"
WITH (
    external_location = 's3://ptbwa-da/prod/prod_addi_conv/report_addi_conv_app/',
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day']
) AS
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
        AND SUBSTR(third.created_at, 1, 10) BETWEEN '2026-01-01' AND '2026-05-09'
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
    tracker,
    cmp,
    event,
    dt,
    daily_unique_ip,
    revenue,
    SUBSTR(dt, 1, 4) AS year,
    SUBSTR(dt, 6, 2) AS month,
    SUBSTR(dt, 9, 2) AS day
FROM daily
ORDER BY dt, tracker, cmp, event;
