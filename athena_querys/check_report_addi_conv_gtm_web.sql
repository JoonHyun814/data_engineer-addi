-- report_addi_conv_* 테이블(report_addi_conv_gtm_web, report_addi_conv_gtm_web_imp,
-- report_addi_conv_app, report_addi_conv_gtm_youtube, report_addi_conv_metric_youtube)
-- 특정 날짜 데이터 적재 확인용
-- 아래 target_date CTE의 날짜만 바꿔서 실행하세요
-- metric_sum 의미는 테이블마다 다름: daily_unique_ip 합계(gtm_web/gtm_web_imp/app/gtm_youtube),
-- conversions 합계(metric_youtube)
-- campaign_cnt 의미도 다름: cmp_no 기준(gtm_web/gtm_web_imp/gtm_youtube/metric_youtube),
-- cmp(원본 캠페인 식별자) 기준(app)

WITH target_date AS (
    SELECT DATE '2026-05-01' AS target_dt
)

SELECT 'report_addi_conv_gtm_web' AS table_name,
    COUNT(*)               AS row_cnt,
    SUM(r.daily_unique_ip) AS metric_sum,
    COUNT(DISTINCT r.cmp_no) AS campaign_cnt
FROM "prod_addi_conv"."report_addi_conv_gtm_web" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.dt = t.target_dt

UNION ALL

SELECT 'report_addi_conv_gtm_web_imp' AS table_name,
    COUNT(*)               AS row_cnt,
    SUM(r.daily_unique_ip) AS metric_sum,
    COUNT(DISTINCT r.cmp_no) AS campaign_cnt
FROM "prod_addi_conv"."report_addi_conv_gtm_web_imp" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = t.target_dt

UNION ALL

SELECT 'report_addi_conv_app' AS table_name,
    COUNT(*)               AS row_cnt,
    SUM(r.daily_unique_ip) AS metric_sum,
    COUNT(DISTINCT r.cmp)  AS campaign_cnt
FROM "prod_addi_conv"."report_addi_conv_app" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.dt = CAST(t.target_dt AS VARCHAR)

UNION ALL

SELECT 'report_addi_conv_gtm_youtube' AS table_name,
    COUNT(*)               AS row_cnt,
    SUM(r.daily_unique_ip) AS metric_sum,
    COUNT(DISTINCT r.cmp_no) AS campaign_cnt
FROM "prod_addi_conv"."report_addi_conv_gtm_youtube" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.dt = t.target_dt

UNION ALL

SELECT 'report_addi_conv_metric_youtube' AS table_name,
    COUNT(*)               AS row_cnt,
    SUM(r.conversions)     AS metric_sum,
    COUNT(DISTINCT r.cmp_no) AS campaign_cnt
FROM "prod_addi_conv"."report_addi_conv_metric_youtube" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.date = CAST(t.target_dt AS VARCHAR)

ORDER BY table_name;
