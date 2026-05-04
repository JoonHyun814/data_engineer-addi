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

# 1. Glue 초기화 및 파라미터 수신
# Glue 파라미터 창에서 입력한 값들을 가져옵니다.
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'start_date',
    'end_date',
    'campaign_ids'
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# 2. 동적 파라미터 파싱
# 날짜 문자열(YYYY-MM-DD)을 datetime.date 객체로 변환
START_DATE = datetime.strptime(args['start_date'], "%Y-%m-%d").date()
END_DATE = datetime.strptime(args['end_date'], "%Y-%m-%d").date()

# 쉼표로 구분된 캠페인 ID 문자열 (그대로 SQL IN 절에 사용 가능)
campaign_ids_str = args['campaign_ids']

print(f"조회 기간: {START_DATE} ~ {END_DATE}")
print(f"타겟 캠페인: {campaign_ids_str}")

# 3. 기본 변수 설정
S3_BUCKET = "ptbwa-da"
S3_CONFIG_KEY = "prod/config/google_ads_api_client.pickle" # S3에 업로드된 pickle 경로
LOCAL_CONFIG_PATH = "/tmp/google_ads_api_client.pickle"
API_VERSION = "v23"
customer_id = "6884951170" # addirect_youtube

# 4. S3에서 Pickle 파일 다운로드 (dbfs 대체)
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
            AND campaign.id IN ({campaign_ids_str})
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

# 7. S3 저장 및 Athena 카탈로그 업데이트
if not all_rows:
    print("No data found to process.")
else:
    # DataFrame 생성
    df = spark.createDataFrame(all_rows)
    
    # S3 Parquet 저장 (s3:// 프로토콜 사용)
    s3_output_path = f"s3://{S3_BUCKET}/prod/addi_conv_gclid_youtube"
    df.write.mode("append") \
        .partitionBy("date") \
        .format("parquet") \
        .save(s3_output_path)
    
    print(f"Data successfully saved to {s3_output_path}")

    # Spark SQL을 이용한 데이터베이스, 테이블 생성 및 파티션 갱신
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
    
    # MSCK REPAIR를 통해 새 파티션 인식
    spark.sql(f"MSCK REPAIR TABLE `{db_name}`.`{table_name}`")
    print("Athena/Glue Catalog partition update completed successfully.")

job.commit()