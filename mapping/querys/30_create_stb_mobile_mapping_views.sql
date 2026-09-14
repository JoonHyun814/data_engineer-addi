/*
 * 3. 조회용 뷰 생성
 *
 * 3-1: stb_mobile_mapping_current_view
 *      셋톱–ADID 상세 관계, 활성 여부, 관측 시점 차이, IP 위험 지표
 *
 * 3-2: stb_summary
 *      셋톱별 IP/ADID/활성 ADID/소스별 ADID 요약
 */

/* =====================================================
   3-1. 상세 매핑 조회 뷰
   ===================================================== */
CREATE OR REPLACE VIEW
    "dev-ptbwa-dw"."stb_mobile_mapping_current_view"
AS
WITH ip_risk AS (
    SELECT
        carrier,
        ip,
        COUNT(DISTINCT CASE
            WHEN record_type = 'STB_IP' THEN plattform_id
        END) AS ip_stb_count,
        COUNT(DISTINCT CASE
            WHEN record_type = 'MAPPING' THEN ad_id
        END) AS ip_adid_count,
        MAX(CASE
            WHEN record_type = 'STB_IP' THEN ip_adid_cardinality
        END) AS ip_adid_cardinality
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_current"
    GROUP BY
        carrier,
        ip
)
SELECT
    m.plattform_id,
    m.ad_id,
    m.ip,
    m.carrier,
    m.cate,
    m.stb_first_seen_at,
    m.stb_last_seen_at,
    m.mobile_first_seen_at,
    m.mobile_last_seen_at,
    m.stb_observation_count,
    m.mobile_observation_count,
    m.first_batch_week,
    m.last_batch_week,

    CASE
        WHEN m.mobile_first_seen_at <= m.stb_last_seen_at
         AND m.stb_first_seen_at <= m.mobile_last_seen_at
            THEN 0
        WHEN m.stb_last_seen_at < m.mobile_first_seen_at
            THEN DATE_DIFF(
                'day',
                DATE(m.stb_last_seen_at),
                DATE(m.mobile_first_seen_at)
            )
        ELSE DATE_DIFF(
            'day',
            DATE(m.mobile_last_seen_at),
            DATE(m.stb_first_seen_at)
        )
    END AS observation_gap_days,

    CASE
        WHEN DATE(m.mobile_last_seen_at)
             >= DATE_ADD('month', -6, CURRENT_DATE)
            THEN true
        ELSE false
    END AS is_active_6m,

    r.ip_stb_count,
    r.ip_adid_count,
    COALESCE(r.ip_adid_cardinality, 0) AS ip_adid_cardinality

FROM "dev-ptbwa-dw"."stb_mobile_mapping_current" m
LEFT JOIN ip_risk r
    ON m.carrier = r.carrier
   AND m.ip = r.ip
WHERE m.record_type = 'MAPPING'
  AND COALESCE(r.ip_adid_cardinality, 0) <= 20;

/* 3-1-2. 최근 6개월 내 관측된 활성 매핑만 조회 */
CREATE OR REPLACE VIEW
    "dev-ptbwa-dw"."stb_mobile_mapping_active"
AS
SELECT *
FROM "dev-ptbwa-dw"."stb_mobile_mapping_current_view"
WHERE is_active_6m = true;


/* =====================================================
   3-2. 셋톱별 요약 조회 뷰
   ===================================================== */
CREATE OR REPLACE VIEW
    "dev-ptbwa-dw"."stb_summary"
AS
WITH population AS (
    SELECT
        carrier,
        plattform_id,
        COUNT(DISTINCT ip) AS ip_count,
        MIN(stb_first_seen_at) AS stb_first_seen_at,
        MAX(stb_last_seen_at) AS stb_last_seen_at,
        SUM(stb_observation_count) AS stb_observation_count
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_current"
    WHERE record_type = 'STB_IP'
    GROUP BY
        carrier,
        plattform_id
),

mapping_summary AS (
    SELECT
        m.carrier,
        m.plattform_id,
        COUNT(DISTINCT m.ad_id) AS ad_id_count,
        COUNT(DISTINCT CASE
            WHEN DATE(m.mobile_last_seen_at)
                 >= DATE_ADD('month', -6, CURRENT_DATE)
                THEN m.ad_id
        END) AS active_ad_id_count,
        COUNT(DISTINCT CASE
            WHEN m.cate = 'NHN' THEN m.ad_id
        END) AS nhn_ad_id_count,
        COUNT(DISTINCT CASE
            WHEN m.cate = 'TG' THEN m.ad_id
        END) AS tg_ad_id_count,
        COUNT(DISTINCT m.ip) AS mapped_ip_count,
        MIN(m.mobile_first_seen_at) AS mobile_first_seen_at,
        MAX(m.mobile_last_seen_at) AS mobile_last_seen_at
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_current" m
    LEFT JOIN (
        SELECT
            carrier,
            ip,
            MAX(ip_adid_cardinality) AS latest_ip_adid_cardinality
        FROM "dev-ptbwa-dw"."stb_mobile_mapping_current"
        WHERE record_type = 'STB_IP'
        GROUP BY carrier, ip
    ) c
        ON m.carrier = c.carrier
       AND m.ip = c.ip
    WHERE m.record_type = 'MAPPING'
      AND COALESCE(c.latest_ip_adid_cardinality, m.ip_adid_cardinality, 0)
          <= 20
    GROUP BY
        m.carrier,
        m.plattform_id
)

SELECT
    p.carrier,
    p.plattform_id,
    p.ip_count,
    COALESCE(m.mapped_ip_count, 0) AS mapped_ip_count,
    COALESCE(m.ad_id_count, 0) AS ad_id_count,
    COALESCE(m.active_ad_id_count, 0) AS active_ad_id_count,
    COALESCE(m.nhn_ad_id_count, 0) AS nhn_ad_id_count,
    COALESCE(m.tg_ad_id_count, 0) AS tg_ad_id_count,
    p.stb_first_seen_at,
    p.stb_last_seen_at,
    m.mobile_first_seen_at,
    m.mobile_last_seen_at,
    p.stb_observation_count,
    CASE
        WHEN COALESCE(m.ad_id_count, 0) > 0 THEN true
        ELSE false
    END AS is_mapped,
    CASE
        WHEN COALESCE(m.active_ad_id_count, 0) > 0 THEN true
        ELSE false
    END AS has_active_mapping

FROM population p
LEFT JOIN mapping_summary m
    ON p.carrier = m.carrier
   AND p.plattform_id = m.plattform_id;


/* 사용 예시

-- 특정 셋톱의 상세 매핑
SELECT *
FROM "dev-ptbwa-dw"."stb_mobile_mapping_current_view"
WHERE plattform_id = '조회할-셋톱-ID';

-- 셋톱별 요약
SELECT *
FROM "dev-ptbwa-dw"."stb_summary"
ORDER BY carrier, plattform_id;

*/
