-- 초기 적재용 (CTAS) — 이후 일별 적재는 raw_conv_web_v3.sql, 구간 적재는 raw_conv_web_v3_range.sql 사용
-- 실행 전 date_range CTE의 start_yyyymmdd / end_yyyymmdd 수동 설정
-- v2와 차이: 캠페인+IP당 최초 CTV 시청 접점 이후 발생한 모든 GTM 전환 이벤트를 1:N으로 전부 적재한다.
-- 컬럼도 원본 3개 쿼리(raw_conv_Abi.sql / raw_conv_addi.sql / raw_conv_odm.sql) 기준으로
-- log_time / eid / scroll / click / conv_type을 그대로 유지한다.

CREATE TABLE "prod_addi_conv"."raw_conv_web_v3"
WITH (
    external_location = 's3://ptbwa-da/prod/prod_addi_conv/raw_conv_web_v3/',
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day']
) AS
WITH date_range AS (
    SELECT
        20260101 AS start_yyyymmdd,
        20260510 AS end_yyyymmdd
),

info AS (
    SELECT DISTINCT
        cmp_no,
        pixel_id_web
    FROM "prod_addi_conv"."addi_conv_info"
    WHERE pixel_id_web IS NOT NULL
),

mall AS (
    SELECT DISTINCT
        REPLACE(SUBSTR(g.log_time, 1, 10), '/', '-') AS mall_dt,
        DATE_PARSE(g.log_time, '%Y/%m/%d/%H:%i:%s') AS mall_datetime,
        g.log_time,
        g.eid,
        CASE
            WHEN g.ev = 'conversion' THEN COALESCE(NULLIF(TRIM(CAST(g.conv_type AS VARCHAR)), ''), g.ev)
            WHEN g.ev = 'click'      THEN COALESCE(NULLIF(TRIM(CAST(g.click AS VARCHAR)), ''), g.ev)
            ELSE g.ev
        END AS ev,
        -- 테이블 scroll 컬럼은 bigint(v2 기준)로 고정되어 있으나 gtm_logs_hourly.scroll은
        -- varchar이므로 명시 캐스팅 필요. 공백/비숫자 값은 TRY_CAST로 NULL 처리
        TRY_CAST(NULLIF(TRIM(CAST(g.scroll AS VARCHAR)), '') AS BIGINT) AS scroll,
        g.click,
        g.conv_type,
        g.conv_value,
        g.conv_meta,
        g.pid,
        g.ip,
        i.cmp_no
    FROM "prod-ptbwa-dw"."gtm_logs_hourly" g
    INNER JOIN info i
        ON g.pid = i.pixel_id_web
    CROSS JOIN date_range dr
    WHERE 1=1
        AND CAST(
            CONCAT(g.year, LPAD(g.month, 2, '0'), LPAD(g.day, 2, '0'))
            AS INTEGER
        ) BETWEEN dr.start_yyyymmdd AND dr.end_yyyymmdd
        AND NULLIF(TRIM(g.ip), '') IS NOT NULL
),

cmp_list AS (
    -- 구간 내 Mall 이벤트가 발생한 캠페인만 대상
    SELECT DISTINCT cmp_no FROM mall
),

-- ==========================================================
-- [Addi] postback.request_ip = mall.ip 직접 매칭
-- 캠페인+postback IP별 최초 CTV 시청 접점 이후 발생한 모든 GTM 이벤트를 연결
-- ==========================================================

addi_post_base AS (
    SELECT DISTINCT
        FROM_ISO8601_TIMESTAMP(post.created_at) AS post_datetime,
        post.cmp_no,
        post.ifa AS stp_id,
        post.request_ip AS post_ip
    FROM "prod-ptbwa-dw"."addi_postback_log" post
    INNER JOIN cmp_list c
        ON post.cmp_no = c.cmp_no
    CROSS JOIN date_range dr
    WHERE 1=1
        AND post.log_type = 'v_complete'
        AND CAST(
            CONCAT(post.year, LPAD(post.month, 2, '0'), LPAD(post.day, 2, '0'))
            AS INTEGER
        ) <= dr.end_yyyymmdd
        AND NULLIF(TRIM(post.request_ip), '') IS NOT NULL
),

addi_post_ranked AS (
    SELECT
        post_datetime,
        cmp_no,
        stp_id,
        post_ip,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, post_ip
            ORDER BY post_datetime ASC, stp_id ASC
        ) AS post_rn
    FROM addi_post_base
),

addi_post_first AS (
    -- 캠페인 + postback IP별 최초 CTV 시청 접점 1건
    SELECT post_datetime, cmp_no, stp_id, post_ip
    FROM addi_post_ranked
    WHERE post_rn = 1
),

addi_result AS (
    -- 최초 CTV 시청 이후 발생한 GTM 이벤트 전체 연결(1:N)
    SELECT DISTINCT
        f.cmp_no,
        f.pid,
        f.eid,
        f.log_time,
        f.ev,
        f.scroll,
        f.click,
        f.conv_type,
        f.conv_value,
        f.conv_meta,
        f.mall_dt,
        p.post_datetime,
        f.mall_datetime,
        f.ip AS mall_ip,
        p.stp_id,
        p.post_ip AS raw_ip
    FROM addi_post_first p
    INNER JOIN mall f
        ON p.post_ip = f.ip
        AND p.cmp_no = f.cmp_no
        AND f.mall_datetime > p.post_datetime
),

-- ==========================================================
-- [Abi, ODM] 공통: IFA 기준 CTV 시청 완료 로그 및 6개월 조회 범위
-- ==========================================================

post_base AS (
    SELECT DISTINCT
        FROM_ISO8601_TIMESTAMP(post.created_at) AS post_datetime,
        post.cmp_no,
        post.ifa AS stp_id,
        post.request_ip AS raw_ip
    FROM "prod-ptbwa-dw"."addi_postback_log" post
    INNER JOIN cmp_list c
        ON post.cmp_no = c.cmp_no
    CROSS JOIN date_range dr
    WHERE 1=1
        AND post.log_type = 'v_complete'
        AND CAST(
            CONCAT(post.year, LPAD(post.month, 2, '0'), LPAD(post.day, 2, '0'))
            AS INTEGER
        ) <= dr.end_yyyymmdd
        AND NULLIF(TRIM(post.ifa), '') IS NOT NULL
),

campaign_start AS (
    -- 캠페인별 최초 CTV 시청 완료 시점
    SELECT
        cmp_no,
        MIN(post_datetime) AS ad_start_datetime
    FROM post_base
    GROUP BY 1
),

post_range AS (
    -- 캠페인 시작월을 포함한 최근 6개월 조회 범위
    SELECT
        cmp_no,
        CAST(
            DATE_FORMAT(
                CAST(DATE_ADD('month', -5, DATE_TRUNC('month', ad_start_datetime)) AS TIMESTAMP),
                '%Y%m'
            ) AS INTEGER
        ) AS start_yyyymm,
        CAST(
            DATE_FORMAT(
                CAST(DATE_TRUNC('month', ad_start_datetime) AS TIMESTAMP),
                '%Y%m'
            ) AS INTEGER
        ) AS end_yyyymm
    FROM campaign_start
),

-- ==========================================================
-- [ODM] ptbwa_tg + ptbwa_skb 경유 IP 매핑
-- ==========================================================

odm_ip_list AS (
    -- STP ID ↔ 모바일 ADID ↔ SKP IP 매핑
    SELECT DISTINCT
        r.cmp_no,
        tg.ip AS skp_ip,
        skb.platform_ad_id AS stp_id,
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
    -- CTV STP ID를 이용해 모바일 ADID와 SKP IP 확보
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        list.m_adid,
        p.raw_ip,
        list.skp_ip
    FROM post_base p
    INNER JOIN odm_ip_list list
        ON list.cmp_no = p.cmp_no
        AND list.stp_id = p.stp_id
),

odm_mapping_ranked AS (
    -- 캠페인 + SKP IP별 최초 CTV 시청 접점 순위
    SELECT
        post_datetime, cmp_no, stp_id, m_adid, raw_ip, skp_ip,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, skp_ip
            ORDER BY post_datetime ASC, stp_id ASC, m_adid ASC
        ) AS touch_rn
    FROM odm_mapping
),

odm_mapping_first AS (
    SELECT post_datetime, cmp_no, stp_id, m_adid, raw_ip, skp_ip
    FROM odm_mapping_ranked
    WHERE touch_rn = 1
),

odm_result AS (
    -- 최초 CTV 시청 이후 발생한 GTM 이벤트 전체 연결(1:N)
    SELECT DISTINCT
        f.cmp_no,
        f.pid,
        f.eid,
        f.log_time,
        f.ev,
        f.scroll,
        f.click,
        f.conv_type,
        f.conv_value,
        f.conv_meta,
        f.mall_dt,
        m.post_datetime,
        f.mall_datetime,
        f.ip AS mall_ip,
        m.stp_id,
        m.m_adid,
        m.raw_ip
    FROM odm_mapping_first m
    INNER JOIN mall f
        ON m.skp_ip = f.ip
        AND m.cmp_no = f.cmp_no
        AND f.mall_datetime > m.post_datetime
),

-- ==========================================================
-- [Abi] ab_postback_log + ptbwa_skb 경유 IP 매핑
-- ==========================================================

abi_ip_list AS (
    -- ABI IFA를 모바일 ADID로, SKB platform_ad_id를 STP ID로 사용
    SELECT DISTINCT
        r.cmp_no,
        FROM_ISO8601_TIMESTAMP(abi.created_at) AS abi_visit_datetime,
        abi.ifa AS m_adid,
        abi.request_ip AS abi_request_ip,
        skb.platform_ad_id AS stp_id
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
    -- CTV 시청 완료 IFA와 ABI IP 매핑
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        i.m_adid,
        p.raw_ip,
        i.abi_visit_datetime,
        i.abi_request_ip
    FROM post_base p
    INNER JOIN abi_ip_list i
        ON i.cmp_no = p.cmp_no
        AND i.stp_id = p.stp_id
        -- CTV 시청일 기준 이전 180일 이내 ABI 접점
        AND i.abi_visit_datetime BETWEEN DATE_ADD('day', -180, p.post_datetime) AND p.post_datetime
),

abi_mapping_ranked AS (
    -- 캠페인 + ABI IP별 대표 CTV 매핑 선정
    SELECT
        post_datetime, cmp_no, stp_id, m_adid, raw_ip, abi_visit_datetime, abi_request_ip,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, abi_request_ip
            ORDER BY
                -- 최초 CTV 시청 접점 우선
                post_datetime ASC,
                -- 동일 시청 시점이면 가장 가까운 ABI 접점 우선
                abi_visit_datetime DESC,
                stp_id ASC,
                m_adid ASC
        ) AS mapping_rn
    FROM abi_mapping
),

abi_mapping_first AS (
    SELECT post_datetime, cmp_no, stp_id, m_adid, raw_ip, abi_visit_datetime, abi_request_ip
    FROM abi_mapping_ranked
    WHERE mapping_rn = 1
),

abi_result AS (
    -- 최초 CTV 시청 이후 발생한 GTM 이벤트 전체 연결(1:N)
    SELECT DISTINCT
        f.cmp_no,
        f.pid,
        f.eid,
        f.log_time,
        f.ev,
        f.scroll,
        f.click,
        f.conv_type,
        f.conv_value,
        f.conv_meta,
        f.mall_dt,
        m.post_datetime,
        f.mall_datetime,
        f.ip AS mall_ip,
        m.stp_id,
        m.m_adid,
        m.raw_ip
    FROM abi_mapping_first m
    INNER JOIN mall f
        ON m.abi_request_ip = f.ip
        AND m.cmp_no = f.cmp_no
        AND f.mall_datetime > m.post_datetime
)

SELECT
    cmp_no, pid, eid, log_time, ev, scroll, click, conv_type, conv_value, conv_meta,
    mall_dt,
    DATE_FORMAT(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
    DATE_FORMAT(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
    mall_ip,
    'Addi'                 AS cate,
    stp_id,
    CAST(NULL AS VARCHAR)  AS m_adid,
    raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM addi_result
UNION ALL
SELECT
    cmp_no, pid, eid, log_time, ev, scroll, click, conv_type, conv_value, conv_meta,
    mall_dt,
    DATE_FORMAT(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
    DATE_FORMAT(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
    mall_ip,
    'Abi'                  AS cate,
    stp_id,
    m_adid,
    raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM abi_result
UNION ALL
SELECT
    cmp_no, pid, eid, log_time, ev, scroll, click, conv_type, conv_value, conv_meta,
    mall_dt,
    DATE_FORMAT(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
    DATE_FORMAT(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
    mall_ip,
    'ODM'                  AS cate,
    stp_id,
    m_adid,
    raw_ip,
    SUBSTR(mall_dt, 1, 4)  AS year,
    SUBSTR(mall_dt, 6, 2)  AS month,
    SUBSTR(mall_dt, 9, 2)  AS day
FROM odm_result
;
