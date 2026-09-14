/*
 * 1-2. 특정 주간 데이터를 주간 누적 테이블에 추가
 *
 * 실행 전 params.week_start와 아래 APM/NHN의 YYYYMMDD 리터럴 범위를
 * 대상 주 월요일~일요일로 함께 변경한다.
 * week_end_exclusive는 week_start + 7일로 자동 계산된다.
 * 같은 batch_week을 두 번 INSERT하면 중복되므로 배치별 1회만 실행한다.
 *
 * TG는 현재 저장소 기준으로 year/month만 확인되어 월 단위 관측 범위를 사용한다.
 * 따라서 TG의 first/last_seen은 실제 발생 시각이 아닌 해당 월의 시작/끝이다.
 */
INSERT INTO "dev-ptbwa-dw"."stb_mobile_mapping_weekly"
WITH params_base AS (
    /* 실행할 주의 월요일만 변경 */
    SELECT DATE '2026-09-07' AS week_start
),

params AS (
    SELECT
        week_start,
        DATE_ADD('day', 7, week_start) AS week_end_exclusive,
        DATE_FORMAT(week_start, '%Y-%m-%d') AS batch_week
    FROM params_base
),

apm_base AS (
    SELECT
        CASE
            WHEN LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))) LIKE '%skb%' THEN 'SKB'
            WHEN LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))) LIKE '%uplus%'
              OR LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))) LIKE '%u+%'
              OR LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))) LIKE '%lguplus%'
              OR LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))) LIKE '%lg+%' THEN 'U+'
            WHEN REGEXP_LIKE(
                LOWER(TRIM(CAST(a.app_bundle AS VARCHAR))),
                '(^|[._ -])kt([._ -]|$)'
            ) THEN 'KT'
            ELSE NULL
        END AS carrier,
        LOWER(TRIM(CAST(a.ifa AS VARCHAR))) AS plattform_id,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(a.ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS ip,
        DATE_PARSE(
            CONCAT(
                a.year, '-', LPAD(CAST(a.month AS VARCHAR), 2, '0'), '-',
                LPAD(CAST(a.day AS VARCHAR), 2, '0'), ' ',
                LPAD(CAST(a.hour AS VARCHAR), 2, '0'), ':00:00'
            ),
            '%Y-%m-%d %H:%i:%s'
        ) AS observed_at
    FROM "prod-ptbwa-dw"."apm_bid_log_flatten" a
    CROSS JOIN params p
    /* 2026-09-07 ~ 2026-09-13: 확인된 0-padding 파티션의 정적 프루닝 */
    WHERE CAST(CONCAT(a.year, a.month, a.day) AS BIGINT)
              BETWEEN 20260907 AND 20260913
      AND NULLIF(TRIM(CAST(a.ifa AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(a.ip AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(a.ifa AS VARCHAR))) NOT IN (
          'null', 'undefined', '00000000-0000-0000-0000-000000000000'
      )
      AND LOWER(TRIM(CAST(a.ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

apm_weekly AS (
    SELECT
        carrier,
        plattform_id,
        ip,
        MIN(observed_at) AS stb_first_seen_at,
        MAX(observed_at) AS stb_last_seen_at,
        COUNT(*) AS stb_observation_count
    FROM apm_base
    WHERE carrier IS NOT NULL
    GROUP BY
        carrier,
        plattform_id,
        ip
),

nhn_base AS (
    SELECT
        'NHN' AS cate,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(n.device_ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS ip,
        LOWER(TRIM(CAST(n.device_ifa AS VARCHAR))) AS ad_id,
        DATE_PARSE(
            CONCAT(
                n.year, '-', LPAD(CAST(n.month AS VARCHAR), 2, '0'), '-',
                LPAD(CAST(n.day AS VARCHAR), 2, '0'), ' ',
                LPAD(CAST(n.hour AS VARCHAR), 2, '0'), ':00:00'
            ),
            '%Y-%m-%d %H:%i:%s'
        ) AS observed_at
    FROM "prod-ptbwa-dw"."nhn_bid_log_flatten" n
    CROSS JOIN params p
    /* 2026-09-07 ~ 2026-09-13: 확인된 0-padding 파티션의 정적 프루닝 */
    WHERE CAST(CONCAT(n.year, n.month, n.day) AS BIGINT)
              BETWEEN 20260907 AND 20260913
      AND NULLIF(TRIM(CAST(n.device_ip AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(n.device_ifa AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(n.device_ifa AS VARCHAR))) NOT IN (
          'null', 'undefined', '00000000-0000-0000-0000-000000000000'
      )
      AND LOWER(TRIM(CAST(n.device_ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

nhn_weekly AS (
    SELECT
        cate,
        ip,
        ad_id,
        MIN(observed_at) AS mobile_first_seen_at,
        MAX(observed_at) AS mobile_last_seen_at,
        COUNT(*) AS mobile_observation_count
    FROM nhn_base
    GROUP BY cate, ip, ad_id
),

tg_base AS (
    SELECT
        'TG' AS cate,
        REGEXP_REPLACE(
            LOWER(TRIM(CAST(t.ip AS VARCHAR))),
            '^::ffff:',
            ''
        ) AS ip,
        LOWER(TRIM(CAST(t.uuid AS VARCHAR))) AS ad_id,
        DATE_PARSE(
            CONCAT(t.year, '-', LPAD(CAST(t.month AS VARCHAR), 2, '0'), '-01'),
            '%Y-%m-%d'
        ) AS mobile_first_seen_at,
        DATE_ADD(
            'second',
            -1,
            DATE_ADD(
                'month',
                1,
                DATE_PARSE(
                    CONCAT(t.year, '-', LPAD(CAST(t.month AS VARCHAR), 2, '0'), '-01'),
                    '%Y-%m-%d'
                )
            )
        ) AS mobile_last_seen_at
    FROM "propfit"."ptbwa_tg" t
    CROSS JOIN params p
    WHERE CAST(DATE_PARSE(
              CONCAT(t.year, '-', LPAD(CAST(t.month AS VARCHAR), 2, '0'), '-01'),
              '%Y-%m-%d'
          ) AS DATE) < p.week_end_exclusive
      AND DATE_ADD(
              'month',
              1,
              CAST(DATE_PARSE(
                  CONCAT(t.year, '-', LPAD(CAST(t.month AS VARCHAR), 2, '0'), '-01'),
                  '%Y-%m-%d'
              ) AS DATE)
          ) > p.week_start
      AND NULLIF(TRIM(CAST(t.ip AS VARCHAR)), '') IS NOT NULL
      AND NULLIF(TRIM(CAST(t.uuid AS VARCHAR)), '') IS NOT NULL
      AND LOWER(TRIM(CAST(t.uuid AS VARCHAR))) NOT IN (
          'null', 'undefined', '00000000-0000-0000-0000-000000000000'
      )
      AND LOWER(TRIM(CAST(t.ip AS VARCHAR))) NOT IN (
          'null', 'undefined', '0.0.0.0', '127.0.0.1', '::', '::1'
      )
),

tg_monthly AS (
    SELECT
        cate,
        ip,
        ad_id,
        MIN(mobile_first_seen_at) AS mobile_first_seen_at,
        MAX(mobile_last_seen_at) AS mobile_last_seen_at,
        COUNT(*) AS mobile_observation_count
    FROM tg_base
    GROUP BY cate, ip, ad_id
),

mobile_reference AS (
    SELECT * FROM nhn_weekly
    UNION ALL
    SELECT * FROM tg_monthly
),

weekly_rows AS (
    /* APM 전체 모집단: 셋톱–IP별 한 행 */
    SELECT
        'STB_IP' AS record_type,
        a.plattform_id,
        CAST(NULL AS VARCHAR) AS ad_id,
        a.ip,
        a.carrier,
        CAST(NULL AS VARCHAR) AS cate,
        a.stb_first_seen_at,
        a.stb_last_seen_at,
        CAST(NULL AS TIMESTAMP) AS mobile_first_seen_at,
        CAST(NULL AS TIMESTAMP) AS mobile_last_seen_at,
        a.stb_observation_count,
        CAST(0 AS BIGINT) AS mobile_observation_count
    FROM apm_weekly a

    UNION ALL

    /* 동일 IP 기반 상세 후보 매핑 */
    SELECT
        'MAPPING' AS record_type,
        a.plattform_id,
        m.ad_id,
        a.ip,
        a.carrier,
        m.cate,
        a.stb_first_seen_at,
        a.stb_last_seen_at,
        m.mobile_first_seen_at,
        m.mobile_last_seen_at,
        a.stb_observation_count,
        m.mobile_observation_count
    FROM apm_weekly a
    INNER JOIN mobile_reference m
        ON a.ip = m.ip
)

SELECT
    record_type,
    plattform_id,
    ad_id,
    ip,
    carrier,
    cate,
    stb_first_seen_at,
    stb_last_seen_at,
    mobile_first_seen_at,
    mobile_last_seen_at,
    stb_observation_count,
    mobile_observation_count,
    (SELECT batch_week FROM params) AS batch_week
FROM weekly_rows;
