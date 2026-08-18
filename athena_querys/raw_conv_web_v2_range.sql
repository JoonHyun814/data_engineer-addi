-- [STEP 2] 구간 데이터 적재
-- 날짜 범위를 수정 후 실행하세요 (YYYY-MM-DD 형식)
-- STEP 1 DELETE 실행 완료 후 실행하세요
-- v1과 달리 stp_id / m_adid / raw_ip / conv_meta / conv_value 컬럼을 추가로 적재한다.

INSERT INTO "prod_addi_conv"."raw_conv_web_v2"

WITH base_date AS (
    SELECT
        DATE '2026-05-01'                                          AS start_dt,
        DATE '2026-05-10'                                          AS end_dt,
        CAST(date_format(DATE '2026-05-01', '%Y%m%d') AS INTEGER)  AS start_yyyymmdd,
        CAST(date_format(DATE '2026-05-10', '%Y%m%d') AS INTEGER)  AS end_yyyymmdd
),

info AS (
    SELECT DISTINCT
        cmp_no,
        pixel_id_web
    FROM "prod_addi_conv"."addi_conv_info"
),

mall AS (
    SELECT DISTINCT
        REPLACE(SUBSTR(g.log_time, 1, 10), '/', '-') AS mall_dt,
        date_parse(g.log_time, '%Y/%m/%d/%H:%i:%s') AS mall_datetime,
        CASE
            WHEN g.ev = 'conversion' THEN COALESCE(CAST(g.conv_type AS VARCHAR), g.ev)
            WHEN g.ev = 'click'      THEN COALESCE(CAST(g.click AS VARCHAR), g.ev)
            ELSE g.ev
        END AS ev,
        g.conv_meta,
        g.conv_value,
        g.pid,
        g.ip,
        i.cmp_no
    FROM "prod-ptbwa-dw"."gtm_logs_hourly" g
    INNER JOIN info i
        ON g.pid = i.pixel_id_web
    CROSS JOIN base_date b
    WHERE 1=1
        AND CAST(
            CONCAT(g.year, LPAD(g.month, 2, '0'), LPAD(g.day, 2, '0'))
            AS INTEGER
        ) BETWEEN b.start_yyyymmdd AND b.end_yyyymmdd
        AND NULLIF(TRIM(g.ip), '') IS NOT NULL
),

-- ==========================================================
-- [Addi] postback.request_ip = mall.ip 직접 매칭
-- ==========================================================

addi_mapping AS (
    SELECT DISTINCT
        post.cmp_no,
        from_iso8601_timestamp(post.created_at) AS post_datetime,
        post.request_ip AS post_ip,
        post.ifa AS stp_id,
        mall.mall_dt,
        mall.ip AS mall_ip,
        mall.mall_datetime,
        mall.pid,
        mall.ev,
        mall.conv_meta,
        mall.conv_value
    FROM "prod-ptbwa-dw"."addi_postback_log" post
    INNER JOIN mall
        ON post.request_ip = mall.ip
        AND post.cmp_no = mall.cmp_no
    CROSS JOIN base_date b
    WHERE 1=1
        AND post.log_type = 'v_complete'
        AND CAST(
            CONCAT(post.year, LPAD(post.month, 2, '0'), LPAD(post.day, 2, '0'))
            AS INTEGER
        ) <= b.end_yyyymmdd
        AND NULLIF(TRIM(post.request_ip), '') IS NOT NULL
),

addi_result AS (
    SELECT
        mall_dt,
        post_datetime,
        mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        CASE WHEN mall_datetime > post_datetime THEN true ELSE false END AS is_mall_later
    FROM addi_mapping
    WHERE mall_ip IS NOT NULL
),

addi_dedup AS (
    SELECT
        mall_dt,
        date_format(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
        date_format(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, mall_dt, mall_ip
            ORDER BY post_datetime ASC, mall_datetime ASC
        ) AS rn
    FROM addi_result
    WHERE is_mall_later = true
),

-- ==========================================================
-- [Abi, ODM] 공통: IFA 기준 CTV 시청 완료 로그
-- ==========================================================

cmp_list AS (
    SELECT DISTINCT cmp_no FROM mall
),

post_base AS (
    SELECT DISTINCT
        from_iso8601_timestamp(post.created_at) AS post_datetime,
        post.cmp_no,
        post.ifa AS stp_id,
        post.request_ip AS raw_ip
    FROM "prod-ptbwa-dw"."addi_postback_log" post
    INNER JOIN cmp_list c
        ON post.cmp_no = c.cmp_no
    CROSS JOIN base_date b
    WHERE 1=1
        AND post.log_type = 'v_complete'
        AND CAST(
            CONCAT(post.year, LPAD(post.month, 2, '0'), LPAD(post.day, 2, '0'))
            AS INTEGER
        ) <= b.end_yyyymmdd
        AND NULLIF(TRIM(post.ifa), '') IS NOT NULL
),

campaign_start AS (
    SELECT
        cmp_no,
        MIN(post_datetime) AS ad_start_datetime
    FROM post_base
    GROUP BY 1
),

post_range AS (
    SELECT
        cmp_no,
        CAST(
            date_format(
                CAST(date_add('month', -5, date_trunc('month', ad_start_datetime)) AS timestamp),
                '%Y%m'
            ) AS INTEGER
        ) AS start_yyyymm,
        CAST(
            date_format(
                CAST(date_trunc('month', ad_start_datetime) AS timestamp),
                '%Y%m'
            ) AS INTEGER
        ) AS end_yyyymm
    FROM campaign_start
),

-- ==========================================================
-- [ODM] ptbwa_tg + ptbwa_skb 경유 IP 매핑
-- ==========================================================

odm_ip_list AS (
    SELECT DISTINCT
        r.cmp_no,
        tg.ip AS skp_ip,
        skb.platform_ad_id AS skp_ad_id,
        skb.ad_id AS m_adid
    FROM "propfit"."ptbwa_tg" tg
    INNER JOIN "propfit"."ptbwa_skb" skb
        ON skb.ad_id = tg.uuid
    INNER JOIN post_range r
        ON CAST(CONCAT(skb.year, LPAD(skb.month, 2, '0')) AS INTEGER)
            BETWEEN r.start_yyyymm AND r.end_yyyymm
        AND CAST(CONCAT(tg.year, LPAD(tg.month, 2, '0')) AS INTEGER)
            BETWEEN r.start_yyyymm AND r.end_yyyymm
    WHERE 1=1
        AND NULLIF(TRIM(tg.ip), '') IS NOT NULL
        AND NULLIF(TRIM(skb.platform_ad_id), '') IS NOT NULL
        AND NULLIF(TRIM(skb.ad_id), '') IS NOT NULL
),

odm_mapping AS (
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        p.raw_ip,
        list.m_adid,
        list.skp_ip
    FROM post_base p
    INNER JOIN odm_ip_list list
        ON list.cmp_no = p.cmp_no
        AND list.skp_ad_id = p.stp_id
),

odm_result AS (
    SELECT
        f.mall_dt,
        m.post_datetime,
        f.mall_datetime,
        f.ip AS mall_ip,
        f.cmp_no,
        f.pid,
        f.ev,
        f.conv_meta,
        f.conv_value,
        m.stp_id,
        m.m_adid,
        m.raw_ip,
        CASE WHEN f.mall_datetime > m.post_datetime THEN true ELSE false END AS is_mall_later
    FROM odm_mapping m
    INNER JOIN mall f
        ON m.skp_ip = f.ip
        AND m.cmp_no = f.cmp_no
),

odm_first_touch AS (
    SELECT
        mall_dt,
        date_format(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
        date_format(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        m_adid,
        raw_ip,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, mall_dt, mall_ip
            ORDER BY post_datetime ASC, mall_datetime ASC, stp_id ASC, m_adid ASC
        ) AS rn
    FROM odm_result
    WHERE is_mall_later = true
),

-- ==========================================================
-- [Abi] ab_postback_log + ptbwa_skb 경유 IP 매핑
-- ==========================================================

abi_ip_list AS (
    SELECT DISTINCT
        r.cmp_no,
        from_iso8601_timestamp(abi.created_at) AS abi_visit_datetime,
        abi.request_ip AS abi_request_ip,
        abi.ifa AS m_adid,
        skb.platform_ad_id AS skp_ad_id
    FROM "prod-ptbwa-dw"."ab_postback_log" abi
    INNER JOIN "propfit"."ptbwa_skb" skb
        ON skb.ad_id = abi.ifa
    INNER JOIN post_range r
        ON CAST(CONCAT(skb.year, LPAD(skb.month, 2, '0')) AS INTEGER)
            BETWEEN r.start_yyyymm AND r.end_yyyymm
        AND CAST(CONCAT(abi.year, LPAD(abi.month, 2, '0')) AS INTEGER)
            BETWEEN r.start_yyyymm AND r.end_yyyymm
    WHERE 1=1
        AND NULLIF(TRIM(abi.request_ip), '') IS NOT NULL
        AND NULLIF(TRIM(abi.ifa), '') IS NOT NULL
        AND NULLIF(TRIM(skb.platform_ad_id), '') IS NOT NULL
),

abi_mapping AS (
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        p.raw_ip,
        i.m_adid,
        i.abi_visit_datetime,
        i.abi_request_ip
    FROM post_base p
    INNER JOIN abi_ip_list i
        ON i.cmp_no = p.cmp_no
        AND i.skp_ad_id = p.stp_id
        AND i.abi_visit_datetime BETWEEN date_add('day', -180, p.post_datetime) AND p.post_datetime
),

abi_result AS (
    SELECT
        f.mall_dt,
        m.post_datetime,
        f.mall_datetime,
        f.ip AS mall_ip,
        f.cmp_no,
        f.pid,
        f.ev,
        f.conv_meta,
        f.conv_value,
        m.stp_id,
        m.m_adid,
        m.raw_ip,
        CASE WHEN f.mall_datetime > m.post_datetime THEN true ELSE false END AS is_mall_later
    FROM abi_mapping m
    INNER JOIN mall f
        ON m.abi_request_ip = f.ip
        AND m.cmp_no = f.cmp_no
),

abi_first_touch AS (
    SELECT
        mall_dt,
        date_format(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
        date_format(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        m_adid,
        raw_ip,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, mall_dt, mall_ip
            ORDER BY post_datetime ASC, mall_datetime ASC, stp_id ASC, m_adid ASC
        ) AS rn
    FROM abi_result
    WHERE is_mall_later = true
)

SELECT
    cmp_no, pid, ev, conv_meta, conv_value, mall_dt, post_datetime, mall_datetime, mall_ip,
    'Addi'                 AS cate,
    stp_id,
    CAST(NULL AS VARCHAR)  AS m_adid,
    mall_ip                AS raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM addi_dedup
WHERE rn = 1
UNION ALL
SELECT
    cmp_no, pid, ev, conv_meta, conv_value, mall_dt, post_datetime, mall_datetime, mall_ip,
    'Abi'                  AS cate,
    stp_id,
    m_adid,
    raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM abi_first_touch
WHERE rn = 1
UNION ALL
SELECT
    cmp_no, pid, ev, conv_meta, conv_value, mall_dt, post_datetime, mall_datetime, mall_ip,
    'ODM'                  AS cate,
    stp_id,
    m_adid,
    raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM odm_first_touch
WHERE rn = 1
;
