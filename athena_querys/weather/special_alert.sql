-- 2026-06-22: getPwnCd 응답 raw 스키마로 전면 교체 (구 getWthrWrnList 기반 스키마와 호환 불가)
-- 배포 전 기존 weather.special_alert 테이블을 아래 명령으로 먼저 삭제할 것 (메타데이터만 삭제, S3 데이터는 보존됨)
-- DROP TABLE IF EXISTS weather.special_alert
CREATE EXTERNAL TABLE IF NOT EXISTS weather.special_alert (
    stnId        STRING,
    areaCode     STRING,
    areaName     STRING,
    warnVar      INT,
    warnStress   INT,
    command      STRING,
    cancel       STRING,
    tmFc         BIGINT,
    tmSeq        INT,
    startTime    BIGINT,
    endTime      BIGINT,
    allEndTime   BIGINT,
    fetched_at   STRING
)
PARTITIONED BY (
    dt STRING,
    hr STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/special_alert/'
TBLPROPERTIES ('has_encrypted_data' = 'false')
