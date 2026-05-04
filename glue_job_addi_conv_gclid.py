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

# 3. 기본 변수 설정 (S3 버킷 및 파일 경로 주의)
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
            click_view.gclid,
            click_view.ad_group_ad,
            click_view.resource_name,
            ad_group.campaign,
            ad_group.name,
            campaign.name,
            campaign.id,
            segments.date,
            ad_group.id
        FROM click_view
        WHERE
            segments.date = '{date_str}'
    """

    stream = ga_service.search_stream(customer_id=customer_id, query=query)

    rows = []
    for batch in stream:
        for row in batch.results:
            rows.append({
                "gclid": row.click_view.gclid,
                "ad_group_ad": row.click_view.ad_group_ad,
                "resource_name": row.click_view.resource_name,
                "campaign": row.ad_group.campaign,
                "ad_group_id": row.ad_group.id,
                "ad_group_name": row.ad_group.name,
                "c_id": row.campaign.id,
                "c_name": row.campaign.name,
                "date": row.segments.date,
            })

    print(f"[{date_str}] rows fetched: {len(rows)}")
    all_rows.extend(rows)
    current_date += timedelta(days=1)

print(f"Total rows fetched: {len(all_rows)}")

# 7. 데이터 저장 (S3 -> Athena 갱신 -> RDS 적재)
if not all_rows:
    print("No data found to process.")
else:
    # Spark DataFrame 생성
    df = spark.createDataFrame(all_rows)
    
    # [A] S3 Parquet 저장 및 Athena 파티션 갱신
    s3_output_path = f"s3://{S3_BUCKET}/prod/addi_conv_gclid_youtube"
    df.write.mode("append").partitionBy("date").format("parquet").save(s3_output_path)
    print(f"Data successfully saved to {s3_output_path}")

    db_name = "prod_addi_conv"
    table_name = "addi_conv_gclid_youtube"

    spark.sql(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    spark.sql(f"""
    CREATE EXTERNAL TABLE IF NOT EXISTS `{db_name}`.`{table_name}` (
      gclid STRING,
      ad_group_ad STRING,
      resource_name STRING,
      campaign STRING,
      ad_group_id BIGINT,
      ad_group_name STRING,
      c_id BIGINT,
      c_name STRING
    )
    PARTITIONED BY (date STRING)
    STORED AS PARQUET
    LOCATION '{s3_output_path}'
    TBLPROPERTIES ("parquet.compress"="SNAPPY")
    """)
    spark.sql(f"MSCK REPAIR TABLE `{db_name}`.`{table_name}`")
    print("Athena/Glue Catalog partition update completed successfully.")

    # [B] RDS (MySQL) 적재
    db_url = "jdbc:mysql://database-addi.ckmngphs6qfc.ap-northeast-2.rds.amazonaws.com:3306/addi"
    db_properties = {
        "user": "propfit",
        "password": "Ptbw1234",
        "driver": "com.mysql.cj.jdbc.Driver"
    }
    
    # RDS에 데이터를 Append 모드로 추가합니다.
    df.write.jdbc(url=db_url, table=table_name, mode="append", properties=db_properties)
    print("RDS database data insertion completed successfully.")

job.commit()