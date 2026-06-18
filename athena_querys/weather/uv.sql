CREATE EXTERNAL TABLE IF NOT EXISTS weather.uv (
    region_id    INT,
    area_name    STRING,
    weather_code STRING,
    h0_value     INT,
    created_at   STRING
)
PARTITIONED BY (
    dt STRING,
    hr STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/uv/'
TBLPROPERTIES ('has_encrypted_data' = 'false')
