-- raw_conv_web 계열 테이블(raw_conv_web, raw_conv_web_home, raw_conv_web_v2,
-- raw_conv_web_v3, raw_conv_web_imp) 특정 날짜 데이터 적재 확인용
-- 아래 target_date CTE의 날짜만 바꿔서 실행하세요

WITH target_date AS (
    SELECT DATE '2026-05-01' AS target_dt
)

SELECT 'raw_conv_web' AS table_name,
    COUNT(*)                AS row_cnt,
    COUNT(DISTINCT mall_ip) AS unique_ip_cnt,
    COUNT(DISTINCT cmp_no)  AS cmp_no_cnt
FROM "prod_addi_conv"."raw_conv_web" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = CAST(t.target_dt AS VARCHAR)

UNION ALL

SELECT 'raw_conv_web_home' AS table_name,
    COUNT(*)                AS row_cnt,
    COUNT(DISTINCT mall_ip) AS unique_ip_cnt,
    COUNT(DISTINCT cmp_no)  AS cmp_no_cnt
FROM "prod_addi_conv"."raw_conv_web_home" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = CAST(t.target_dt AS VARCHAR)

UNION ALL

SELECT 'raw_conv_web_v2' AS table_name,
    COUNT(*)                AS row_cnt,
    COUNT(DISTINCT mall_ip) AS unique_ip_cnt,
    COUNT(DISTINCT cmp_no)  AS cmp_no_cnt
FROM "prod_addi_conv"."raw_conv_web_v2" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = CAST(t.target_dt AS VARCHAR)

UNION ALL

SELECT 'raw_conv_web_v3' AS table_name,
    COUNT(*)                AS row_cnt,
    COUNT(DISTINCT mall_ip) AS unique_ip_cnt,
    COUNT(DISTINCT cmp_no)  AS cmp_no_cnt
FROM "prod_addi_conv"."raw_conv_web_v3" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = CAST(t.target_dt AS VARCHAR)

UNION ALL

SELECT 'raw_conv_web_imp' AS table_name,
    COUNT(*)                AS row_cnt,
    COUNT(DISTINCT mall_ip) AS unique_ip_cnt,
    COUNT(DISTINCT cmp_no)  AS cmp_no_cnt
FROM "prod_addi_conv"."raw_conv_web_imp" r
CROSS JOIN target_date t
WHERE r.year  = SUBSTR(CAST(t.target_dt AS VARCHAR), 1, 4)
    AND r.month = SUBSTR(CAST(t.target_dt AS VARCHAR), 6, 2)
    AND r.day   = SUBSTR(CAST(t.target_dt AS VARCHAR), 9, 2)
    AND r.mall_dt = CAST(t.target_dt AS VARCHAR)

ORDER BY table_name;
