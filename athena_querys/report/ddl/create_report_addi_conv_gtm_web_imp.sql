-- 초기 적재용 (CTAS) — 이후 일별 적재는 report_addi_conv_gtm_web_imp.sql 사용
-- 실행 전 WHERE 절의 날짜 범위 수동 설정

CREATE TABLE "prod_addi_conv"."report_addi_conv_gtm_web_imp"
WITH (
    external_location = 's3://ptbwa-da/prod/prod_addi_conv/report_addi_conv_gtm_web_imp/',
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day']
) AS
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
WHERE mall_dt BETWEEN '2026-01-01' AND '2026-05-31'
    AND CAST(mall_datetime AS TIMESTAMP) >= CAST(post_datetime AS TIMESTAMP)
    AND CAST(mall_datetime AS TIMESTAMP) <  CAST(post_datetime AS TIMESTAMP) + INTERVAL '8' DAY
GROUP BY imp_dt, mall_dt, cmp_no, pid, ev;
