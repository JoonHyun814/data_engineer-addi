-- 특정 구간 데이터 적재
-- 날짜 범위를 수정 후 실행하세요 (start_date_slash ~ end_date_slash, YYYY/MM/DD 형식)

INSERT INTO "prod_addi_conv"."report_addi_conv_gtm_youtube"

WITH gtm AS (
    SELECT
        DATE_FORMAT(
            DATE_PARSE(SUBSTR(log_time, 1, 10), '%Y/%m/%d'),
            '%Y-%m-%d'
        ) AS dt,
        pid,
        log_time,
        REGEXP_EXTRACT(url, 'utm_campaign=([^&]+)', 1) AS utm_campaign,
        gclid,
        CASE
            WHEN ev = 'conversion' THEN COALESCE(CAST(conv_type AS VARCHAR), ev)
            WHEN ev = 'click'      THEN COALESCE(CAST(click AS VARCHAR), ev)
            ELSE ev
        END AS ev,
        ip
    FROM "prod-ptbwa-dw"."gtm_logs_hourly"
    WHERE SUBSTR(log_time, 1, 10) BETWEEN '2026/05/01' AND '2026/05/10'
),
gclid_list AS (
    SELECT
        cmp_you_no,
        gclid
    FROM "prod_addi_conv"."addi_conv_gclid_youtube"
),
gclid_raw AS (
    SELECT
        gtm.dt,
        info.cmp_no,
        gtm.pid,
        info.cmp_you_no,
        gtm.ev,
        gtm.ip
    FROM gtm
    INNER JOIN gclid_list gcl
        ON gcl.gclid = gtm.gclid
    LEFT JOIN "prod_addi_conv"."addi_conv_info" info
        ON info.cmp_you_no = CAST(gcl.cmp_you_no AS VARCHAR)
),
utm_raw AS (
    SELECT
        gtm.dt,
        info.cmp_no,
        gtm.pid,
        info.cmp_you_no,
        gtm.ev,
        gtm.ip
    FROM gtm
    LEFT JOIN "prod_addi_conv"."addi_conv_info" info
        ON info.pixel_id = gtm.pid
       AND info.cmp_you_no = gtm.utm_campaign
    WHERE info.cmp_no IS NOT NULL
),
result_raw AS (
    SELECT * FROM gclid_raw
    UNION ALL
    SELECT * FROM utm_raw
),
aggregated AS (
    SELECT
        cmp_no,
        pid,
        cmp_you_no,
        ev,
        dt,
        COUNT(DISTINCT ip) AS daily_unique_ip
    FROM result_raw
    WHERE cmp_no IS NOT NULL
    GROUP BY
        cmp_no,
        pid,
        cmp_you_no,
        ev,
        dt
)
SELECT
    cmp_no,
    pid,
    cmp_you_no,
    ev,
    CAST(dt AS DATE) AS dt,
    daily_unique_ip,
    SUBSTR(dt, 1, 4) AS year,
    SUBSTR(dt, 6, 2) AS month,
    SUBSTR(dt, 9, 2) AS day
FROM aggregated
ORDER BY dt, cmp_no, pid, cmp_you_no, ev;
