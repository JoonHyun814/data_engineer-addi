/*
 * 2-2. 특정 주간 이력을 current Iceberg 테이블에 반영
 *
 * params.batch_week을 1-2에서 적재한 주 시작일로 변경한다.
 * 주간 배치는 오래된 순서대로 반영한다.
 * 같은 batch_week을 재실행하면 WHEN MATCHED 조건에서 건너뛴다.
 */
MERGE INTO "dev-ptbwa-dw"."stb_mobile_mapping_current" AS target
USING (
    SELECT
        record_type,
        plattform_id,
        ad_id,
        ip,
        carrier,
        cate,
        MIN(stb_first_seen_at) AS stb_first_seen_at,
        MAX(stb_last_seen_at) AS stb_last_seen_at,
        MIN(mobile_first_seen_at) AS mobile_first_seen_at,
        MAX(mobile_last_seen_at) AS mobile_last_seen_at,
        MAX(stb_observation_count) AS stb_observation_count,
        MAX(mobile_observation_count) AS mobile_observation_count,
        MAX(ip_adid_cardinality) AS ip_adid_cardinality,
        ARRAY_DISTINCT(
            FLATTEN(ARRAY_AGG(COALESCE(stb_sources, CAST(ARRAY[] AS ARRAY(VARCHAR)))))
        ) AS stb_sources,
        batch_week
    FROM "dev-ptbwa-dw"."stb_mobile_mapping_weekly"
    WHERE batch_week = '2026-09-07'
    GROUP BY
        record_type,
        plattform_id,
        ad_id,
        ip,
        carrier,
        cate,
        batch_week
) AS source

ON  target.record_type = source.record_type
AND target.carrier = source.carrier
AND target.plattform_id = source.plattform_id
AND target.ip = source.ip
AND COALESCE(target.ad_id, '') = COALESCE(source.ad_id, '')
AND COALESCE(target.cate, '') = COALESCE(source.cate, '')

WHEN MATCHED
 AND source.batch_week > target.last_batch_week
THEN UPDATE SET
    stb_first_seen_at = LEAST(
        target.stb_first_seen_at,
        source.stb_first_seen_at
    ),
    stb_last_seen_at = GREATEST(
        target.stb_last_seen_at,
        source.stb_last_seen_at
    ),
    mobile_first_seen_at = CASE
        WHEN target.mobile_first_seen_at IS NULL
            THEN source.mobile_first_seen_at
        WHEN source.mobile_first_seen_at IS NULL
            THEN target.mobile_first_seen_at
        ELSE LEAST(
            target.mobile_first_seen_at,
            source.mobile_first_seen_at
        )
    END,
    mobile_last_seen_at = CASE
        WHEN target.mobile_last_seen_at IS NULL
            THEN source.mobile_last_seen_at
        WHEN source.mobile_last_seen_at IS NULL
            THEN target.mobile_last_seen_at
        ELSE GREATEST(
            target.mobile_last_seen_at,
            source.mobile_last_seen_at
        )
    END,
    stb_observation_count =
        target.stb_observation_count + source.stb_observation_count,
    mobile_observation_count = CASE
        /* TG는 월 단위 데이터가 주마다 참조되므로 중복 합산하지 않는다. */
        WHEN source.cate = 'TG' THEN GREATEST(
            target.mobile_observation_count,
            source.mobile_observation_count
        )
        ELSE target.mobile_observation_count + source.mobile_observation_count
    END,
    ip_adid_cardinality = source.ip_adid_cardinality,
    stb_sources = ARRAY_DISTINCT(
        COALESCE(target.stb_sources, CAST(ARRAY[] AS ARRAY(VARCHAR)))
        || COALESCE(source.stb_sources, CAST(ARRAY[] AS ARRAY(VARCHAR)))
    ),
    last_batch_week = source.batch_week

WHEN NOT MATCHED
THEN INSERT (
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
    ip_adid_cardinality,
    stb_sources,
    first_batch_week,
    last_batch_week
)
VALUES (
    source.record_type,
    source.plattform_id,
    source.ad_id,
    source.ip,
    source.carrier,
    source.cate,
    source.stb_first_seen_at,
    source.stb_last_seen_at,
    source.mobile_first_seen_at,
    source.mobile_last_seen_at,
    source.stb_observation_count,
    source.mobile_observation_count,
    source.ip_adid_cardinality,
    source.stb_sources,
    source.batch_week,
    source.batch_week
);
