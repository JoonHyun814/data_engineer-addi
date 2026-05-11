import sys
import boto3
import time
from datetime import datetime, timedelta
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions

# 1. Job 초기화
args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)
logger = glueContext.get_logger()

# 2. 파라미터 파싱
# - s3_query_path : S3 SQL 파일 경로 (e.g. s3://ptbwa-da/prod/sql/report_addi_conv_app.sql)
# - date          : 적재 날짜 YYYY-MM-DD (기본값: 어제)
# - athena_db     : Athena 데이터베이스 (기본값: prod_addi_conv)
# - athena_table  : Athena 테이블명 (필수)
# - s3_output_location : Athena 쿼리 결과 저장 경로 (기본값: s3://ptbwa-athena/query-results/)
def get_optional_arg(name, default=None):
    if f'--{name}' in sys.argv:
        return getResolvedOptions(sys.argv, [name])[name]
    return default

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

s3_query_path      = get_optional_arg('s3_query_path')
date               = get_optional_arg('date', yesterday)
athena_db          = get_optional_arg('athena_db', 'prod_addi_conv')
athena_table       = get_optional_arg('athena_table')
s3_output_location = get_optional_arg('s3_output_location', 's3://ptbwa-da/prod/athena-query-results/')

if not s3_query_path:
    raise ValueError("s3_query_path 파라미터가 필요합니다.")
if not athena_table:
    raise ValueError("athena_table 파라미터가 필요합니다.")

logger.info(f"s3_query_path: {s3_query_path}")
logger.info(f"date: {date}")
logger.info(f"athena_db: {athena_db}")
logger.info(f"athena_table: {athena_table}")

# 3. 날짜 파싱
try:
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    year  = date_obj.strftime('%Y')
    month = date_obj.strftime('%m')
    day   = date_obj.strftime('%d')
    date_slash = f"{year}/{month}/{day}"
    logger.info(f"파티션: year={year}, month={month}, day={day}")
except ValueError:
    raise ValueError(f"날짜 형식 오류: {date}. YYYY-MM-DD 형식이어야 합니다.")

# 4. AWS 클라이언트 초기화
region = 'ap-northeast-2'
s3_client     = boto3.client('s3', region_name=region)
athena_client = boto3.client('athena', region_name=region)
glue_client   = boto3.client('glue', region_name=region)

# 5. S3에서 SQL 읽기
try:
    path = s3_query_path.replace('s3://', '')
    bucket, key = path.split('/', 1)
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    sql = obj['Body'].read().decode('utf-8').strip()
    # {date}, {date_slash} 플레이스홀더 치환
    sql = sql.replace('{date}', date)
    sql = sql.replace('{date_slash}', date_slash)
    logger.info(f"[SUCCESS] SQL 읽기 완료 (date={date})")
except Exception as e:
    logger.error(f"[FAIL] SQL 읽기 실패: {e}")
    raise e

# 6. Glue Catalog에서 테이블 S3 위치 조회
try:
    table_info = glue_client.get_table(DatabaseName=athena_db, Name=athena_table)
    table_location = table_info['Table']['StorageDescriptor']['Location'].rstrip('/')
    partition_s3_path = f"{table_location}/year={year}/month={month}/day={day}/"
    logger.info(f"테이블 위치: {table_location}")
    logger.info(f"파티션 경로: {partition_s3_path}")
except Exception as e:
    logger.error(f"[FAIL] 테이블 위치 조회 실패: {e}")
    raise e

# 7. Athena 쿼리 실행 + 완료 대기
def run_athena_query(query, description):
    try:
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': athena_db},
            ResultConfiguration={'OutputLocation': s3_output_location}
        )
        execution_id = response['QueryExecutionId']
        logger.info(f"[{description}] ExecutionId: {execution_id}")

        while True:
            result = athena_client.get_query_execution(QueryExecutionId=execution_id)
            state = result['QueryExecution']['Status']['State']
            if state == 'SUCCEEDED':
                logger.info(f"[SUCCESS] {description} 완료")
                return execution_id
            elif state in ('FAILED', 'CANCELLED'):
                reason = result['QueryExecution']['Status'].get('StateChangeReason', '')
                raise Exception(f"Query {state}: {reason}")
            time.sleep(5)
    except Exception as e:
        logger.error(f"[FAIL] {description} 실패: {e}")
        raise e

# 8. 파티션 S3 데이터 삭제 (외부 테이블이므로 직접 삭제 필요)
try:
    part_bucket, part_prefix = partition_s3_path.replace('s3://', '').split('/', 1)
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=part_bucket, Prefix=part_prefix)

    delete_keys = []
    for page in pages:
        for obj in page.get('Contents', []):
            delete_keys.append({'Key': obj['Key']})

    if delete_keys:
        # S3 delete_objects는 한 번에 최대 1000개
        for i in range(0, len(delete_keys), 1000):
            s3_client.delete_objects(
                Bucket=part_bucket,
                Delete={'Objects': delete_keys[i:i+1000]}
            )
        logger.info(f"[SUCCESS] S3 파티션 데이터 삭제 완료: {len(delete_keys)}개 파일")
    else:
        logger.info(f"삭제할 S3 파일 없음: {partition_s3_path}")
except Exception as e:
    logger.error(f"[FAIL] S3 파티션 데이터 삭제 실패: {e}")
    raise e

# 9. Athena 카탈로그 파티션 메타데이터 삭제
drop_partition_sql = f"""
    ALTER TABLE `{athena_db}`.`{athena_table}`
    DROP IF EXISTS PARTITION (year='{year}', month='{month}', day='{day}')
"""
run_athena_query(drop_partition_sql.strip(), "파티션 메타데이터 삭제")

# 10. INSERT 쿼리 실행
run_athena_query(sql, f"INSERT INTO {athena_db}.{athena_table} ({date})")

logger.info(f"[DONE] {athena_db}.{athena_table} / {date} 적재 완료")
job.commit()
