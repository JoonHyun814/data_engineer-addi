CREATE TABLE "prod_addi_conv"."report_addi_conv_gtm_web"
WITH (
    external_location = 's3://ptbwa-da/prod/prod_addi_conv/report_addi_conv_gtm_web/',
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day']
) AS
SELECT
    cmp_no,
    pid,
    ev,
    CAST(mall_dt AS DATE) AS dt,
    COUNT(DISTINCT mall_ip) AS daily_unique_ip,
    SUBSTR(mall_dt, 1, 4) AS year,
    SUBSTR(mall_dt, 6, 2) AS month,
    SUBSTR(mall_dt, 9, 2) AS day
FROM "prod_addi_conv"."raw_conv_web"
WHERE mall_dt BETWEEN '2026-01-01' AND '2026-05-11'
GROUP BY cmp_no, pid, ev, mall_dt
ORDER BY mall_dt, cmp_no, pid, ev;
