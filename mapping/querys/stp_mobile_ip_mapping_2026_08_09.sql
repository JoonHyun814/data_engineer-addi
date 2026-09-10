/*
 * 셋톱–모바일 ADID IP 후보 매핑 및 통계 요약
 * 대상 기간: 2026년 08월, 09월
 */
WITH apm AS (
    /* 1. APM-TV 셋톱 ID–IP 정규화 */
    SELECT DISTINCT
        CASE
            WHEN LOWER(TRIM(CAST(app_bundle AS VARCHAR))) LIKE '%skb%' THEN 'SKB'
            WHEN LOWER(TRIM(CAST(app_bundle AS VARCHAR))) LIKE '%uplus%'
              OR LOWER(TRIM(CAST(app_bundle AS VARCHAR))) LIKE '%u+%'
              OR LOWER(TRIM(CAST(app_bundle AS VARCHAR))) LIKE '%lguplus%'
              OR LOWER(TRIM(CAST(app_bundle AS VARCHAR))) LIKE '%lg+%' THEN 'U+'
            WHEN REGEXP_LIKE(
                LOWER(TRIM(CAST(app_bundle AS VARCHAR))),
                '(^|[._ -])kt([._ -]|$)'
            ) THEN 'KT'
            ELSE NULL
        END AS carrier,
        LOWER(TRIM(CAST(ifa AS VARCHAR))) AS stp_id,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS apm_ip
    FROM "prod-ptbwa-dw"."apm_bid_log_flatten"
    WHERE year = '2026'
      AND CAST(month AS VARCHAR) IN ('8', '08', '9', '09')
      AND NULLIF(TRIM(CAST(ifa AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(ip AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(ifa AS VARCHAR)))
            <> '00000000-0000-0000-0000-000000000000'
      AND LOWER(TRIM(CAST(ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

apm_pool AS (
    SELECT DISTINCT carrier, stp_id, apm_ip
    FROM apm
    WHERE carrier IS NOT NULL
),

nhn_mobile AS (
    /* 2. NHN IP–모바일 ADID 정규화 */
    SELECT DISTINCT
        'NHN' AS source_name,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(device_ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS match_ip,
        LOWER(TRIM(CAST(device_ifa AS VARCHAR))) AS mobile_adid
    FROM "prod-ptbwa-dw"."nhn_bid_log_flatten"
    WHERE year = '2026'
      AND CAST(month AS VARCHAR) IN ('8', '08', '9', '09')
      AND NULLIF(TRIM(CAST(device_ip AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(device_ifa AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(device_ifa AS VARCHAR)))
            <> '00000000-0000-0000-0000-000000000000'
      AND LOWER(TRIM(CAST(device_ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

tg_mobile AS (
    /* 3. TG IP–모바일 ADID 정규화 */
    SELECT DISTINCT
        'TG' AS source_name,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS match_ip,
        LOWER(TRIM(CAST(uuid AS VARCHAR))) AS mobile_adid
    FROM "propfit"."ptbwa_tg"
    WHERE year = '2026'
      AND CAST(month AS VARCHAR) IN ('8', '08', '9', '09')
      AND NULLIF(TRIM(CAST(ip AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(uuid AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(uuid AS VARCHAR)))
            <> '00000000-0000-0000-0000-000000000000'
      AND LOWER(TRIM(CAST(ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

mobile_reference AS (
    /* 4. NHN과 TG를 동일 구조로 통합 */
    SELECT source_name, match_ip, mobile_adid FROM nhn_mobile
    UNION ALL
    SELECT source_name, match_ip, mobile_adid FROM tg_mobile
),

matched AS (
    /* 5. 동일 IP 기반 셋톱–모바일 ADID 후보 매핑 */
    SELECT DISTINCT
        a.carrier,
        a.stp_id,
        a.apm_ip,
        m.source_name,
        m.mobile_adid
    FROM apm_pool a
    INNER JOIN mobile_reference m
        ON a.apm_ip = m.match_ip
),

stp_flag AS (
    /* 6. 셋톱별 NHN/TG 매핑 여부 */
    SELECT
        a.carrier,
        a.stp_id,
        MAX(CASE WHEN m.source_name = 'NHN' THEN 1 ELSE 0 END) AS nhn_flag,
        MAX(CASE WHEN m.source_name = 'TG' THEN 1 ELSE 0 END) AS tg_flag
    FROM (
        SELECT DISTINCT carrier, stp_id
        FROM apm_pool
    ) a
    LEFT JOIN matched m
        ON a.carrier = m.carrier
       AND a.stp_id = m.stp_id
    GROUP BY a.carrier, a.stp_id
),

apm_summary AS (
    /* 7. 통신사별 APM 모집단 */
    SELECT
        carrier,
        COUNT(DISTINCT stp_id) AS total_apm_ifa,
        COUNT(DISTINCT apm_ip) AS total_apm_ip
    FROM apm_pool
    GROUP BY carrier
),

ip_summary AS (
    /* 8. 통신사별 IP 기준 매핑 분포 */
    SELECT
        a.carrier,
        COUNT(DISTINCT CASE
            WHEN m.source_name = 'NHN' THEN a.apm_ip
        END) AS nhn_matched_apm_ip,
        COUNT(DISTINCT CASE
            WHEN m.source_name = 'TG' THEN a.apm_ip
        END) AS tg_matched_apm_ip,
        COUNT(DISTINCT CASE
            WHEN m.source_name IS NOT NULL THEN a.apm_ip
        END) AS union_matched_apm_ip
    FROM apm_pool a
    LEFT JOIN matched m
        ON a.carrier = m.carrier
       AND a.stp_id = m.stp_id
       AND a.apm_ip = m.apm_ip
    GROUP BY a.carrier
),

stp_summary AS (
    /* 9. 통신사별 셋톱 기준 매핑 분포 */
    SELECT
        carrier,
        SUM(nhn_flag) AS nhn_matched_apm_ifa,
        SUM(tg_flag) AS tg_matched_apm_ifa,
        SUM(CASE WHEN nhn_flag = 1 AND tg_flag = 1 THEN 1 ELSE 0 END)
            AS both_matched_ifa,
        SUM(CASE WHEN nhn_flag = 1 AND tg_flag = 0 THEN 1 ELSE 0 END)
            AS nhn_only_ifa,
        SUM(CASE WHEN nhn_flag = 0 AND tg_flag = 1 THEN 1 ELSE 0 END)
            AS tg_only_ifa,
        SUM(CASE WHEN nhn_flag = 1 OR tg_flag = 1 THEN 1 ELSE 0 END)
            AS union_matched_apm_ifa
    FROM stp_flag
    GROUP BY carrier
),

mobile_summary AS (
    /* 10. 통신사별 고유 모바일 ADID 분포 */
    SELECT
        carrier,
        COUNT(DISTINCT CASE
            WHEN source_name = 'NHN' THEN mobile_adid
        END) AS nhn_mobile_adid_count,
        COUNT(DISTINCT CASE
            WHEN source_name = 'TG' THEN mobile_adid
        END) AS tg_mobile_adid_count,
        COUNT(DISTINCT mobile_adid) AS final_mobile_adid_count
    FROM matched
    GROUP BY carrier
),

/* 11. 통신사별 최종 매핑 요약 */
SELECT
    a.carrier,
    a.total_apm_ifa,
    a.total_apm_ip,

    COALESCE(i.nhn_matched_apm_ip, 0) AS nhn_matched_apm_ip,
    ROUND(
        100.0 * COALESCE(i.nhn_matched_apm_ip, 0)
        / NULLIF(a.total_apm_ip, 0), 2
    ) AS nhn_ip_mapping_rate_pct,
    COALESCE(s.nhn_matched_apm_ifa, 0) AS nhn_matched_apm_ifa,
    ROUND(
        100.0 * COALESCE(s.nhn_matched_apm_ifa, 0)
        / NULLIF(a.total_apm_ifa, 0), 2
    ) AS nhn_stp_mapping_rate_pct,
    COALESCE(m.nhn_mobile_adid_count, 0) AS nhn_mobile_adid_count,

    COALESCE(i.tg_matched_apm_ip, 0) AS tg_matched_apm_ip,
    ROUND(
        100.0 * COALESCE(i.tg_matched_apm_ip, 0)
        / NULLIF(a.total_apm_ip, 0), 2
    ) AS tg_ip_mapping_rate_pct,
    COALESCE(s.tg_matched_apm_ifa, 0) AS tg_matched_apm_ifa,
    ROUND(
        100.0 * COALESCE(s.tg_matched_apm_ifa, 0)
        / NULLIF(a.total_apm_ifa, 0), 2
    ) AS tg_stp_mapping_rate_pct,
    COALESCE(m.tg_mobile_adid_count, 0) AS tg_mobile_adid_count,

    COALESCE(s.both_matched_ifa, 0) AS both_matched_ifa,
    COALESCE(s.nhn_only_ifa, 0) AS nhn_only_ifa,
    COALESCE(s.tg_only_ifa, 0) AS tg_only_ifa,

    COALESCE(i.union_matched_apm_ip, 0) AS union_matched_apm_ip,
    ROUND(
        100.0 * COALESCE(i.union_matched_apm_ip, 0)
        / NULLIF(a.total_apm_ip, 0), 2
    ) AS union_ip_mapping_rate_pct,
    COALESCE(s.union_matched_apm_ifa, 0) AS union_matched_apm_ifa,
    ROUND(
        100.0 * COALESCE(s.union_matched_apm_ifa, 0)
        / NULLIF(a.total_apm_ifa, 0), 2
    ) AS union_stp_mapping_rate_pct,
    COALESCE(m.final_mobile_adid_count, 0) AS final_mobile_adid_count,

    CASE
        WHEN COALESCE(m.nhn_mobile_adid_count, 0)
           > COALESCE(m.tg_mobile_adid_count, 0) THEN 'NHN'
        WHEN COALESCE(m.tg_mobile_adid_count, 0)
           > COALESCE(m.nhn_mobile_adid_count, 0) THEN 'TG'
        WHEN COALESCE(m.nhn_mobile_adid_count, 0) = 0
         AND COALESCE(m.tg_mobile_adid_count, 0) = 0 THEN 'NO_MATCH'
        ELSE 'SIMILAR'
    END AS dominant_mobile_source

FROM apm_summary a
LEFT JOIN ip_summary i
    ON a.carrier = i.carrier
LEFT JOIN stp_summary s
    ON a.carrier = s.carrier
LEFT JOIN mobile_summary m
    ON a.carrier = m.carrier
ORDER BY
    CASE a.carrier
        WHEN 'SKB' THEN 1
        WHEN 'U+' THEN 2
        WHEN 'KT' THEN 3
        ELSE 9
    END;
