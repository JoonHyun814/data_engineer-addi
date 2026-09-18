-- ABI + STB_MOBILE_MAPPING(ODM) 통합 CTV Reach → Mall 방문 전환 일별 적재
-- raw_conv_new.sql과 로직은 동일하고, athena-insert-data 공용 상태머신(CreateAthenaQuery Lambda)에서
-- 실행하기 위해 날짜 플레이스홀더만 {date} → {input_date}로 바꾼 버전.
-- s3://ptbwa-athena/query/ptbwa/prod-addi_conv_raw_conv_new.sql 로 업로드해서 사용한다.
-- raw_conv_abi_new.sql(ABI) + raw_conv_odm_new.sql(STB_MOBILE_MAPPING)을 UNION ALL로 통합한 버전.
-- 두 원본 쿼리 모두 "STB platform_id → Mobile ADID" 매핑(stb_mobile)까지는 완전히 동일하고,
-- 그 다음 단계에서 ABI는 ab_postback_log의 request_ip로, STB_MOBILE_MAPPING은 같은 테이블 내
-- ip 컬럼으로 각각 확장 IP를 구하는 부분만 다르다. mall / post_base / stb_mobile은 중복 스캔을
-- 피하기 위해 공통 CTE로 한 번만 계산한다.
-- 파티션: year, month, day (Hive-style, 컬럼 순서 마지막에 위치)
INSERT INTO "prod_addi_conv"."raw_conv_new"

WITH base_date AS (
    -- {input_date} 플레이스홀더: CreateAthenaQuery Lambda가 처리 날짜로 치환 (YYYY-MM-DD)
    SELECT
        DATE '{input_date}' AS target_dt,
        CAST(DATE_FORMAT(DATE '{input_date}', '%Y%m%d') AS INTEGER) AS target_yyyymmdd
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
        DATE_PARSE(g.log_time, '%Y/%m/%d/%H:%i:%s') AS mall_datetime,
        CASE
            WHEN g.ev = 'conversion' THEN COALESCE(CAST(g.conv_type AS VARCHAR), g.ev)
            WHEN g.ev = 'click'      THEN COALESCE(CAST(g.click AS VARCHAR), g.ev)
            ELSE g.ev
        END AS ev,
        g.conv_meta,
        g.conv_value,
        g.pid,
        REGEXP_REPLACE(LOWER(TRIM(CAST(g.ip AS VARCHAR))), '^::ffff:', '') AS ip,
        i.cmp_no
    FROM "prod-ptbwa-dw"."gtm_logs_hourly" g
    INNER JOIN info i
        ON g.pid = i.pixel_id_web
    CROSS JOIN base_date b
    WHERE 1=1
        AND CAST(
            CONCAT(g.year, LPAD(g.month, 2, '0'), LPAD(g.day, 2, '0'))
            AS INTEGER
        ) = b.target_yyyymmdd
        AND NULLIF(TRIM(CAST(g.ip AS VARCHAR)), '') IS NOT NULL
),

cmp_list AS (
    -- {input_date} 기준일 Mall 이벤트가 발생한 캠페인만 대상
    SELECT DISTINCT cmp_no FROM mall
),

post_base AS (
    -- CTV 시청 완료 로그
    SELECT DISTINCT
        FROM_ISO8601_TIMESTAMP(post.created_at) AS post_datetime,
        post.cmp_no,
        LOWER(TRIM(CAST(post.ifa AS VARCHAR))) AS stp_id,
        REGEXP_REPLACE(LOWER(TRIM(CAST(post.request_ip AS VARCHAR))), '^::ffff:', '') AS raw_ip
    FROM "prod-ptbwa-dw"."addi_postback_log" post
    INNER JOIN cmp_list c
        ON post.cmp_no = c.cmp_no
    CROSS JOIN base_date b
    WHERE 1=1
        AND post.log_type = 'v_complete'
        AND CAST(
            CONCAT(post.year, LPAD(post.month, 2, '0'), LPAD(post.day, 2, '0'))
            AS INTEGER
        ) <= b.target_yyyymmdd
        AND NULLIF(TRIM(CAST(post.ifa AS VARCHAR)), '') IS NOT NULL
),

stb_mobile AS (
    -- STB platform_id → Mobile ADID (ABI / STB_MOBILE_MAPPING 공통, 비정상 ADID 제외)
    SELECT DISTINCT
        LOWER(TRIM(CAST(plattform_id AS VARCHAR))) AS stp_id,
        LOWER(TRIM(CAST(ad_id AS VARCHAR))) AS m_adid,
        carrier
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_weekly"
    WHERE 1=1
        AND NULLIF(TRIM(CAST(plattform_id AS VARCHAR)), '') IS NOT NULL
        AND NULLIF(TRIM(CAST(ad_id AS VARCHAR)), '') IS NOT NULL
        AND LOWER(TRIM(CAST(ad_id AS VARCHAR))) NOT IN (
            '0000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000',
            'adid_none'
        )
),

-- ==========================================================
-- [ABI] Mobile ADID → ABI request_ip
-- ==========================================================

abi_mobile_ip AS (
    SELECT DISTINCT
        LOWER(TRIM(CAST(abi.ifa AS VARCHAR))) AS m_adid,
        REGEXP_REPLACE(LOWER(TRIM(CAST(abi.request_ip AS VARCHAR))), '^::ffff:', '') AS abi_ip
    FROM "prod-ptbwa-dw"."ab_postback_log" abi
    CROSS JOIN base_date b
    WHERE 1=1
        AND CAST(
            CONCAT(abi.year, LPAD(abi.month, 2, '0'), LPAD(abi.day, 2, '0'))
            AS INTEGER
        ) <= b.target_yyyymmdd
        AND NULLIF(TRIM(CAST(abi.ifa AS VARCHAR)), '') IS NOT NULL
        AND NULLIF(TRIM(CAST(abi.request_ip AS VARCHAR)), '') IS NOT NULL
        AND LOWER(TRIM(CAST(abi.ifa AS VARCHAR))) NOT IN (
            '0000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000',
            'adid_none'
        )
),

abi_ip_list AS (
    SELECT DISTINCT
        sm.stp_id,
        sm.m_adid,
        abi.abi_ip,
        sm.carrier
    FROM stb_mobile sm
    INNER JOIN abi_mobile_ip abi
        ON sm.m_adid = abi.m_adid
),

abi_mapping AS (
    -- 실제 광고 시청 STB만 매핑
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        list.m_adid,
        p.raw_ip,
        list.abi_ip,
        list.carrier
    FROM post_base p
    INNER JOIN abi_ip_list list
        ON p.stp_id = list.stp_id
),

abi_touch AS (
    -- ABI 확장 IP ↔ Mall IP 연결
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
        m.carrier,
        CASE WHEN f.mall_datetime > m.post_datetime THEN true ELSE false END AS is_mall_later
    FROM abi_mapping m
    INNER JOIN mall f
        ON m.abi_ip = f.ip
        AND m.cmp_no = f.cmp_no
),

abi_first_touch AS (
    -- 캠페인 + Mall IP 기준 최초 Touch
    SELECT
        mall_dt,
        DATE_FORMAT(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
        DATE_FORMAT(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        m_adid,
        raw_ip,
        carrier,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, mall_ip
            ORDER BY post_datetime ASC, mall_datetime ASC, stp_id ASC, m_adid ASC
        ) AS rn
    FROM abi_touch
    WHERE is_mall_later = true
),

-- ==========================================================
-- [STB_MOBILE_MAPPING] Mobile ADID → Mobile IP (같은 테이블 내 ip 컬럼 사용)
-- ==========================================================

mobile_ip AS (
    SELECT DISTINCT
        LOWER(TRIM(CAST(ad_id AS VARCHAR))) AS m_adid,
        REGEXP_REPLACE(LOWER(TRIM(CAST(ip AS VARCHAR))), '^::ffff:', '') AS skp_ip
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_weekly"
    WHERE 1=1
        AND NULLIF(TRIM(CAST(ad_id AS VARCHAR)), '') IS NOT NULL
        AND LOWER(TRIM(CAST(ad_id AS VARCHAR))) NOT IN (
            '0000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000',
            'adid_none'
        )
        AND NULLIF(TRIM(CAST(ip AS VARCHAR)), '') IS NOT NULL
),

odm_ip_list AS (
    SELECT DISTINCT
        sm.stp_id,
        sm.m_adid,
        mi.skp_ip,
        sm.carrier
    FROM stb_mobile sm
    INNER JOIN mobile_ip mi
        ON sm.m_adid = mi.m_adid
),

odm_mapping AS (
    -- 실제 광고 시청 STB만 매핑
    SELECT DISTINCT
        p.post_datetime,
        p.cmp_no,
        p.stp_id,
        list.m_adid,
        p.raw_ip,
        list.skp_ip,
        list.carrier
    FROM post_base p
    INNER JOIN odm_ip_list list
        ON p.stp_id = list.stp_id
),

odm_touch AS (
    -- 확장 IP ↔ Mall IP 연결
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
        m.carrier,
        CASE WHEN f.mall_datetime > m.post_datetime THEN true ELSE false END AS is_mall_later
    FROM odm_mapping m
    INNER JOIN mall f
        ON m.skp_ip = f.ip
        AND m.cmp_no = f.cmp_no
),

odm_first_touch AS (
    -- 캠페인 + Mall IP 기준 최초 Touch
    SELECT
        mall_dt,
        DATE_FORMAT(post_datetime, '%Y-%m-%d %H:%i:%s') AS post_datetime,
        DATE_FORMAT(mall_datetime, '%Y-%m-%d %H:%i:%s') AS mall_datetime,
        mall_ip,
        cmp_no,
        pid,
        ev,
        conv_meta,
        conv_value,
        stp_id,
        m_adid,
        raw_ip,
        carrier,
        ROW_NUMBER() OVER (
            PARTITION BY cmp_no, mall_ip
            ORDER BY post_datetime ASC, mall_datetime ASC, stp_id ASC, m_adid ASC
        ) AS rn
    FROM odm_touch
    WHERE is_mall_later = true
)

SELECT
    cmp_no, pid, ev, conv_meta, conv_value,
    mall_dt, post_datetime, mall_datetime, mall_ip,
    'ABI' AS cate,
    stp_id, m_adid, raw_ip, carrier,
    SUBSTR(mall_dt, 1, 4) AS year,
    SUBSTR(mall_dt, 6, 2) AS month,
    SUBSTR(mall_dt, 9, 2) AS day
FROM abi_first_touch
WHERE rn = 1
UNION ALL
SELECT
    cmp_no, pid, ev, conv_meta, conv_value,
    mall_dt, post_datetime, mall_datetime, mall_ip,
    'STB_MOBILE_MAPPING' AS cate,
    stp_id, m_adid, raw_ip, carrier,
    SUBSTR(mall_dt, 1, 4) AS year,
    SUBSTR(mall_dt, 6, 2) AS month,
    SUBSTR(mall_dt, 9, 2) AS day
FROM odm_first_touch
WHERE rn = 1
;
