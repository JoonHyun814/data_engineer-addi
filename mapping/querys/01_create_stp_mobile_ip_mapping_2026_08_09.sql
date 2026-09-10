/*
 * 1~5단계: APM 셋톱과 NHN/TG 모바일 ADID를 동일 IP로 매핑하여 테이블 생성
 * 대상 기간: 2026년 08월, 09월
 *
 * 주의:
 * - Athena CTAS는 대상 테이블과 S3 경로가 비어 있어야 실행할 수 있다.
 * - 결과는 동일 사용자 확정값이 아니라 동일 IP 기반 후보 매핑이다.
 * - plattform_id는 요청된 컬럼명을 그대로 사용했다.
 */
CREATE TABLE "dev-ptbwa-dw"."stp_mobile_ip_mapping_2026_08_09"
WITH (
    format = 'PARQUET',
    external_location = 's3://ptbwa-dw/dev/stp_mobile_ip_mapping_2026_08_09/'
) AS
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
      AND LOWER(TRIM(CAST(ifa AS VARCHAR))) NOT IN (
          'null',
          'undefined',
          '00000000-0000-0000-0000-000000000000'
      )
      AND LOWER(TRIM(CAST(ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

apm_pool AS (
    SELECT DISTINCT
        carrier,
        stp_id,
        apm_ip
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
      AND LOWER(TRIM(CAST(device_ifa AS VARCHAR))) NOT IN (
          'null',
          'undefined',
          '00000000-0000-0000-0000-000000000000'
      )
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
      AND LOWER(TRIM(CAST(uuid AS VARCHAR))) NOT IN (
          'null',
          'undefined',
          '00000000-0000-0000-0000-000000000000'
      )
      AND LOWER(TRIM(CAST(ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

mobile_reference AS (
    /* 4. NHN과 TG를 동일 구조로 통합 */
    SELECT source_name, match_ip, mobile_adid
    FROM nhn_mobile

    UNION ALL

    SELECT source_name, match_ip, mobile_adid
    FROM tg_mobile
),

matched AS (
    /* 5. 동일 IP 기반 셋톱–모바일 ADID 후보 매핑 */
    SELECT DISTINCT
        a.stp_id AS plattform_id,
        m.mobile_adid AS ad_id,
        a.apm_ip AS ip,
        a.carrier,
        m.source_name AS cate
    FROM apm_pool a
    INNER JOIN mobile_reference m
        ON a.apm_ip = m.match_ip
)

SELECT
    plattform_id,
    ad_id,
    ip,
    carrier,
    cate
FROM matched;
