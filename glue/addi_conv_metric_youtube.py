import sys
import boto3
import pickle
import os
from datetime import datetime, timedelta
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from google.ads.googleads.client import GoogleAdsClient

# 1. 필수 파라미터(JOB_NAME) 수신
args = getResolvedOptions(sys.argv, ['JOB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# 2. 동적 파라미터 파싱 (파라미터가 없으면 '어제' 날짜를 기본값으로 사용)
def get_optional_argument(param_name, default_value):
    if f'--{param_name}' in sys.argv:
        return getResolvedOptions(sys.argv, [param_name])[param_name]
    return default_value

yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

start_date_str = get_optional_argument('start_date', yesterday_str)
end_date_str = get_optional_argument('end_date', yesterday_str)

START_DATE = datetime.strptime(start_date_str, "%Y-%m-%d").date()
END_DATE = datetime.strptime(end_date_str, "%Y-%m-%d").date()

print(f"조회 기간: {START_DATE} ~ {END_DATE}")

# 3. 기본 변수 설정
S3_BUCKET = "ptbwa-da"
S3_CONFIG_KEY = "prod/config/google_ads_api_client.pickle"
LOCAL_CONFIG_PATH = "/tmp/google_ads_api_client.pickle"
API_VERSION = "v23"
customer_id = "6884951170"

# 4. S3에서 Pickle 파일 다운로드
s3_client = boto3.client('s3')
print(f"Downloading config from s3://{S3_BUCKET}/{S3_CONFIG_KEY}...")
s3_client.download_file(S3_BUCKET, S3_CONFIG_KEY, LOCAL_CONFIG_PATH)

# 5. Google Ads Client 초기화
with open(LOCAL_CONFIG_PATH, "rb") as f:
    config = pickle.load(f)

config["api_version"] = API_VERSION
client = GoogleAdsClient.load_from_dict(config)
ga_service = client.get_service("GoogleAdsService", version=API_VERSION)
print("Google Ads client initialized.")

# 6. 데이터 추출 로직
all_rows = []
current_date = START_DATE

while current_date <= END_DATE:
    date_str = current_date.strftime("%Y-%m-%d")
    query = f"""
        SELECT
            segments.date,
            campaign.id,
            campaign.name,
            metrics.interactions,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions
        FROM campaign
        WHERE
            segments.date = '{date_str}'
    """

    stream = ga_service.search_stream(customer_id=customer_id, query=query)

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    rows = []
    for batch in stream:
        for row in batch.results:
            rows.append({
                "Date": date_str,
                "campaign_no": row.campaign.id,
                "campaign_name": row.campaign.name,
                "impressions": row.metrics.impressions,
                "interactions": row.metrics.interactions,
                "clicks": row.metrics.clicks,
                "conversions": row.metrics.conversions,
                "created_at": created_at,
                "year": current_date.strftime("%Y"),
                "month": current_date.strftime("%m"),
                "day": current_date.strftime("%d"),
            })

    print(f"[{date_str}] rows fetched: {len(rows)}")
    all_rows.extend(rows)
    current_date += timedelta(days=1)

print(f"Total rows fetched: {len(all_rows)}")

# 7. 데이터 저장 (S3 -> Athena 갱신)
if not all_rows:
    print("No data found to process.")
else:
    df = spark.createDataFrame(all_rows)

    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    s3_output_path = f"s3://{S3_BUCKET}/prod/addi_conv_metric_youtube"
    df.write.mode("overwrite").partitionBy("year", "month", "day").format("parquet").save(s3_output_path)
    print(f"Data successfully saved to {s3_output_path}")

    db_name = "prod_addi_conv"
    table_name = "addi_conv_metric_youtube"

    spark.sql(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    spark.sql(f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS `{db_name}`.`{table_name}` (
      Date STRING,
      campaign_no BIGINT,
      campaign_name STRING,
      impressions BIGINT,
      interactions BIGINT,
      clicks BIGINT,
      conversions DOUBLE,
      created_at STRING
    )
    PARTITIONED BY (year STRING, month STRING, day STRING)
    STORED AS PARQUET
    LOCATION '{s3_output_path}'
    TBLPROPERTIES ("parquet.compress"="SNAPPY")
    """)
    spark.sql(f"MSCK REPAIR TABLE `{db_name}`.`{table_name}`")
    print("Athena/Glue Catalog partition update completed successfully.")

job.commit()
