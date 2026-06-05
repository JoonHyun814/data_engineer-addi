-- 특정 구간 데이터 적재
-- 날짜 범위를 수정 후 실행하세요 (YYYY-MM-DD 형식)

INSERT INTO "prod_addi_conv"."report_addi_conv_gtm_web_imp"
SELECT
    imp_dt,
    CAST(mall_dt AS DATE)  AS mall_dt,
    cmp_no,
    pid,
    ev,
    COUNT(DISTINCT mall_ip) AS daily_unique_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM "prod_addi_conv"."raw_conv_web_imp"
WHERE mall_dt BETWEEN '2026-05-01' AND '2026-05-31'
    AND CAST(mall_datetime AS TIMESTAMP) >= CAST(post_datetime AS TIMESTAMP)
    AND CAST(mall_datetime AS TIMESTAMP) <  CAST(post_datetime AS TIMESTAMP) + INTERVAL '8' DAY
GROUP BY imp_dt, mall_dt, cmp_no, pid, ev;
