/*
 * 매핑 테이블 기반 통신사별 리포트
 *
 * 전제:
 * - 생성 테이블은 APM 전체 셋톱 ID–IP 모집단을 보존한다.
 * - 매핑 성공 행은 ad_id/cate가 존재한다.
 * - 미매핑 행은 ad_id/cate가 NULL이다.
 * - 셋톱에 IP가 여러 개면 하나라도 매핑된 경우 매핑 셋톱으로 계산한다.
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

/* 셋톱별 최종 매핑 여부 */
stp_flag AS (
    SELECT
        carrier,
        plattform_id,
        MAX(CASE WHEN ad_id IS NOT NULL THEN 1 ELSE 0 END) AS matched_flag,
        MAX(CASE WHEN cate = 'NHN' THEN 1 ELSE 0 END) AS nhn_flag,
        MAX(CASE WHEN cate = 'TG' THEN 1 ELSE 0 END) AS tg_flag
    FROM mapping
    GROUP BY
        carrier,
        plattform_id
),

/* IP별 최종 매핑 여부 */
ip_flag AS (
    SELECT
        carrier,
        ip,
        MAX(CASE WHEN ad_id IS NOT NULL THEN 1 ELSE 0 END) AS matched_flag,
        MAX(CASE WHEN cate = 'NHN' THEN 1 ELSE 0 END) AS nhn_flag,
        MAX(CASE WHEN cate = 'TG' THEN 1 ELSE 0 END) AS tg_flag
    FROM mapping
    GROUP BY
        carrier,
        ip
),

/* 셋톱 모집단 및 NHN/TG 단독·중복 분포 */
stp_summary AS (
    SELECT
        carrier,
        COUNT(*) AS total_apm_stp_count,
        SUM(matched_flag) AS matched_stp_count,
        SUM(CASE WHEN matched_flag = 0 THEN 1 ELSE 0 END)
            AS unmatched_stp_count,
        SUM(nhn_flag) AS nhn_matched_stp_count,
        SUM(tg_flag) AS tg_matched_stp_count,
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
),

/* IP 모집단 및 소스별 매핑 분포 */
ip_summary AS (
    SELECT
        carrier,
        COUNT(*) AS total_apm_ip_count,
        SUM(matched_flag) AS matched_ip_count,
        SUM(CASE WHEN matched_flag = 0 THEN 1 ELSE 0 END)
            AS unmatched_ip_count,
        SUM(nhn_flag) AS nhn_matched_ip_count,
        SUM(tg_flag) AS tg_matched_ip_count
    FROM ip_flag
    GROUP BY carrier
),

/* 고유 ADID 및 상세 관계 규모 */
mobile_summary AS (
    SELECT
        carrier,
        COUNT(DISTINCT ad_id) AS final_mobile_adid_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'NHN' THEN ad_id
        END) AS nhn_mobile_adid_count,
        COUNT(DISTINCT CASE
            WHEN cate = 'TG' THEN ad_id
        END) AS tg_mobile_adid_count,
        COUNT(CASE WHEN ad_id IS NOT NULL THEN 1 END)
            AS matched_mapping_row_count,
        COUNT(*) AS total_table_row_count
    FROM mapping
    GROUP BY carrier
)

SELECT
    s.carrier,

    /* 전체 APM 셋톱 모집단 */
    s.total_apm_stp_count,
    s.matched_stp_count,
    s.unmatched_stp_count,
    ROUND(
        100.0 * s.matched_stp_count
        / NULLIF(s.total_apm_stp_count, 0),
        2
    ) AS stp_mapping_rate_pct,

    /* 전체 APM IP 모집단 */
    i.total_apm_ip_count,
    i.matched_ip_count,
    i.unmatched_ip_count,
    ROUND(
        100.0 * i.matched_ip_count
        / NULLIF(i.total_apm_ip_count, 0),
        2
    ) AS ip_mapping_rate_pct,

    /* NHN */
    s.nhn_matched_stp_count,
    ROUND(
        100.0 * s.nhn_matched_stp_count
        / NULLIF(s.total_apm_stp_count, 0),
        2
    ) AS nhn_stp_mapping_rate_pct,
    i.nhn_matched_ip_count,
    ROUND(
        100.0 * i.nhn_matched_ip_count
        / NULLIF(i.total_apm_ip_count, 0),
        2
    ) AS nhn_ip_mapping_rate_pct,
    m.nhn_mobile_adid_count,

    /* TG */
    s.tg_matched_stp_count,
    ROUND(
        100.0 * s.tg_matched_stp_count
        / NULLIF(s.total_apm_stp_count, 0),
        2
    ) AS tg_stp_mapping_rate_pct,
    i.tg_matched_ip_count,
    ROUND(
        100.0 * i.tg_matched_ip_count
        / NULLIF(i.total_apm_ip_count, 0),
        2
    ) AS tg_ip_mapping_rate_pct,
    m.tg_mobile_adid_count,

    /* 셋톱 기준 NHN/TG 분포 */
    s.both_matched_stp_count,
    s.nhn_only_stp_count,
    s.tg_only_stp_count,

    /* 통합 모바일 및 테이블 규모 */
    m.final_mobile_adid_count,
    m.matched_mapping_row_count,
    m.total_table_row_count,

    CASE
        WHEN m.nhn_mobile_adid_count > m.tg_mobile_adid_count THEN 'NHN'
        WHEN m.tg_mobile_adid_count > m.nhn_mobile_adid_count THEN 'TG'
        WHEN m.nhn_mobile_adid_count = 0
         AND m.tg_mobile_adid_count = 0 THEN 'NO_MATCH'
        ELSE 'SIMILAR'
    END AS dominant_mobile_source

FROM stp_summary s
INNER JOIN ip_summary i
    ON s.carrier = i.carrier
INNER JOIN mobile_summary m
    ON s.carrier = m.carrier
ORDER BY
    CASE s.carrier
        WHEN 'SKB' THEN 1
        WHEN 'U+' THEN 2
        WHEN 'KT' THEN 3
        ELSE 9
    END;
