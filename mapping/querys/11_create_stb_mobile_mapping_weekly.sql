/*
 * 1-1. 주간 셋톱–모바일 매핑 이력 테이블 생성
 *
 * 빈 CTAS로 스키마만 생성한다.
 * Athena CTAS 규칙에 따라 파티션 컬럼 batch_week은 SELECT의 마지막 컬럼이다.
 * external_location 경로는 최초 실행 전에 비어 있어야 한다.
 */
CREATE TABLE "dev-ptbwa-dw"."stb_mobile_mapping_weekly"
WITH (
    format = 'PARQUET',
    external_location = 's3://ptbwa-dw/dev/stb_mobile_mapping_weekly/',
    partitioned_by = ARRAY['batch_week']
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
    CAST(NULL AS ARRAY(VARCHAR)) AS stb_sources,
    CAST(NULL AS VARCHAR) AS batch_week
WHERE FALSE;

/*
 * record_type = 'STB_IP': 전체 셋톱–IP 모집단 행 (APM+ADDI_BID+ADDI_POSTBACK 통합)
 * record_type = 'MAPPING': 동일 IP로 연결된 셋톱–모바일 ADID 행
 * stb_sources: 그 주에 해당 셋톱–IP를 관측한 로그 출처 목록('APM'/'ADDI_BID'/'ADDI_POSTBACK' 중복 제거)
 * batch_week: 주 시작일(월요일), YYYY-MM-DD
 */
