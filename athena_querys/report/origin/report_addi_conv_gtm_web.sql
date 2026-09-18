INSERT INTO "prod_addi_conv"."report_addi_conv_gtm_web"
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
WHERE mall_dt = '{date}'
GROUP BY cmp_no, pid, ev, mall_dt;