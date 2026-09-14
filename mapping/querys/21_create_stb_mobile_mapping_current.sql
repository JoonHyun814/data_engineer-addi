/*
 * 2-1. 조회용 current Iceberg 테이블 생성
 *
 * 빈 CTAS로 Iceberg 테이블의 스키마만 생성한다.
 * location 경로는 최초 실행 전에 비어 있어야 한다.
 */
CREATE TABLE "dev-ptbwa-dw"."stb_mobile_mapping_current"
WITH (
    table_type = 'ICEBERG',
    format = 'PARQUET',
    location = 's3://ptbwa-dw/dev/stb_mobile_mapping_current/',
    is_external = false
) AS
SELECT
    CAST(NULL AS VARCHAR) AS record_type,
    CAST(NULL AS VARCHAR) AS plattform_id,
    CAST(NULL AS VARCHAR) AS ad_id,
    CAST(NULL AS VARCHAR) AS ip,
    CAST(NULL AS VARCHAR) AS carrier,
    CAST(NULL AS VARCHAR) AS cate,
    CAST(NULL AS TIMESTAMP) AS stb_first_seen_at,
    CAST(NULL AS TIMESTAMP) AS stb_last_seen_at,
    CAST(NULL AS TIMESTAMP) AS mobile_first_seen_at,
    CAST(NULL AS TIMESTAMP) AS mobile_last_seen_at,
    CAST(NULL AS BIGINT) AS stb_observation_count,
    CAST(NULL AS BIGINT) AS mobile_observation_count,
    CAST(NULL AS BIGINT) AS ip_adid_cardinality,
    CAST(NULL AS VARCHAR) AS first_batch_week,
    CAST(NULL AS VARCHAR) AS last_batch_week
WHERE FALSE;

/*
 * Athena Engine 3에서 실행한다.
 * 주간 배치를 오래된 순서부터 1회씩 MERGE한다.
 */
