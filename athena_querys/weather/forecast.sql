CREATE EXTERNAL TABLE IF NOT EXISTS weather.forecast (
    region_id       INT,
    area_name       STRING,
    weather_code    STRING,
    discomfort_code STRING,
    pop             INT,
    pty             INT,
    pcp             STRING,
    reh             DOUBLE,
    sno             STRING,
    sky             INT,
    tmp             DOUBLE,
    tmn             DOUBLE,
    tmx             DOUBLE,
    uuu             DOUBLE,
    vvv             DOUBLE,
    wav             DOUBLE,
    vec             INT,
    wsd             DOUBLE,
    di              DOUBLE,
    fcst_date       STRING,
    fcst_time       STRING,
    created_at      STRING
)
PARTITIONED BY (
    dt STRING,
    hr STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/forecast/'
TBLPROPERTIES ('has_encrypted_data' = 'false')
