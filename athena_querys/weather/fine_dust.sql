CREATE EXTERNAL TABLE IF NOT EXISTS weather.fine_dust (
    region_id    INT,
    area_name    STRING,
    weather_code STRING,
    pm10Value    DOUBLE,
    pm25Value    DOUBLE,
    pm10Grade    INT,
    pm25Grade    INT,
    pm10Grade1h  INT,
    pm25Grade1h  INT,
    khaiValue    DOUBLE,
    khaiGrade    INT,
    so2Value     DOUBLE,
    coValue      DOUBLE,
    o3Value      DOUBLE,
    no2Value     DOUBLE,
    dataTime     STRING,
    stationName  STRING,
    created_at   STRING
)
PARTITIONED BY (
    dt STRING,
    hr STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/fine_dust/'
TBLPROPERTIES ('has_encrypted_data' = 'false')
