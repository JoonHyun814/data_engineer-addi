/*
 * 1번에서 생성한 매핑 테이블 기반 통신사별 리포트
 *
 * 계산 가능:
 * - 매핑된 셋톱/IP/ADID 수
 * - NHN/TG별 매핑 규모
 * - 셋톱 기준 NHN 단독/TG 단독/양쪽 중복 분포
 *
 * 계산 불가:
 * - 전체 APM 모집단 및 미매핑 셋톱 수
 * - 전체 모집단 대비 IP/셋톱 매핑률
 *   (매핑 테이블에는 5단계에서 성공한 행만 저장되기 때문)
 */
WITH mapping AS (
    SELECT
        plattform_id,
        ad_id,
        ip,
        carrier,
        cate
    FROM "dev-ptbwa-dw"."stp_mobile_ip_mapping_2026_08_09"
),

stp_flag AS (
    SELECT
        carrier,
        plattform_id,
        MAX(CASE WHEN cate = 'NHN' THEN 1 ELSE 0 END) AS nhn_flag,
        MAX(CASE WHEN cate = 'TG' THEN 1 ELSE 0 END) AS tg_flag
    FROM mapping
    GROUP BY
        carrier,
        plattform_id
),

mapping_summary AS (
    SELECT
        carrier,

        COUNT(DISTINCT plattform_id) AS matched_stp_count,
        COUNT(DISTINCT ip) AS matched_ip_count,
        COUNT(DISTINCT ad_id) AS final_mobile_adid_count,
        COUNT(*) AS mapping_row_count,

        COUNT(DISTINCT CASE
            WHEN cate = 'NHN' THEN plattform_id
        END) AS nhn_matched_stp_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'NHN' THEN ip
        END) AS nhn_matched_ip_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'NHN' THEN ad_id
        END) AS nhn_mobile_adid_count,

        COUNT(DISTINCT CASE
            WHEN cate = 'TG' THEN plattform_id
        END) AS tg_matched_stp_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'TG' THEN ip
        END) AS tg_matched_ip_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'TG' THEN ad_id
        END) AS tg_mobile_adid_count

    FROM mapping
    GROUP BY carrier
),

stp_distribution AS (
    SELECT
        carrier,
        SUM(CASE
            WHEN nhn_flag = 1 AND tg_flag = 1 THEN 1 ELSE 0
        END) AS both_matched_stp_count,
        SUM(CASE
            WHEN nhn_flag = 1 AND tg_flag = 0 THEN 1 ELSE 0
        END) AS nhn_only_stp_count,
        SUM(CASE
            WHEN nhn_flag = 0 AND tg_flag = 1 THEN 1 ELSE 0
        END) AS tg_only_stp_count
    FROM stp_flag
    GROUP BY carrier
)

SELECT
    m.carrier,

    m.matched_stp_count,
    m.matched_ip_count,
    m.final_mobile_adid_count,
    m.mapping_row_count,

    m.nhn_matched_stp_count,
    m.nhn_matched_ip_count,
    m.nhn_mobile_adid_count,

    m.tg_matched_stp_count,
    m.tg_matched_ip_count,
    m.tg_mobile_adid_count,

    d.both_matched_stp_count,
    d.nhn_only_stp_count,
    d.tg_only_stp_count,

    ROUND(
        100.0 * m.nhn_matched_stp_count
        / NULLIF(m.matched_stp_count, 0),
        2
    ) AS nhn_share_of_matched_stp_pct,
    ROUND(
        100.0 * m.tg_matched_stp_count
        / NULLIF(m.matched_stp_count, 0),
        2
    ) AS tg_share_of_matched_stp_pct,

    CASE
        WHEN m.nhn_mobile_adid_count > m.tg_mobile_adid_count THEN 'NHN'
        WHEN m.tg_mobile_adid_count > m.nhn_mobile_adid_count THEN 'TG'
        WHEN m.nhn_mobile_adid_count = 0
         AND m.tg_mobile_adid_count = 0 THEN 'NO_MATCH'
        ELSE 'SIMILAR'
    END AS dominant_mobile_source

FROM mapping_summary m
LEFT JOIN stp_distribution d
    ON m.carrier = d.carrier
ORDER BY
    CASE m.carrier
        WHEN 'SKB' THEN 1
        WHEN 'U+' THEN 2
        WHEN 'KT' THEN 3
        ELSE 9
    END;
