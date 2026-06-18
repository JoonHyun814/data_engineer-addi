CREATE EXTERNAL TABLE IF NOT EXISTS weather.regions (
    id                INT,
    area_name         STRING,
    area_name_new     STRING,
    dust_area_name    STRING,
    dust_station_name STRING,
    stn_id            INT,
    grid_x            INT,
    grid_y            INT,
    adm_code          BIGINT
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
    'separatorChar' = ',',
    'quoteChar'     = '"'
)
STORED AS TEXTFILE
LOCATION 's3://ptbwa-da/prod/weather/regions/'
TBLPROPERTIES ('skip.header.line.count' = '1');
