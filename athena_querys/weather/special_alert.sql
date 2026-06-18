CREATE EXTERNAL TABLE IF NOT EXISTS weather.special_alert (
    region_id    INT,
    area_name    STRING,
    stn_id       STRING,
    weather_code STRING,
    keyword      STRING,
    status       STRING,
    title        STRING,
    tmFc         STRING,
    tmSeq        STRING,
    created_at   STRING
)
PARTITIONED BY (
    dt STRING,
    hr STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/special_alert/'
TBLPROPERTIES ('has_encrypted_data' = 'false')
