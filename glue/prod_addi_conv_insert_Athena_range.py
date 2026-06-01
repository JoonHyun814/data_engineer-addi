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
# - s3_query_path      : S3 SQL 파일 경로 (필수, {start_date}/{end_date} 플레이스홀더 사용)
# - start_date         : 시작 날짜 YYYY-MM-DD (필수)
# - end_date           : 종료 날짜 YYYY-MM-DD (필수)
# - athena_db          : Athena 데이터베이스 (기본값: prod_addi_conv)
# - athena_table       : Athena 테이블명 (필수)
# - s3_output_location : Athena 쿼리 결과 경로 (기본값: s3://ptbwa-da/prod/athena-query-results/)
def get_optional_arg(name, default=None):
    if f'--{name}' in sys.argv:
        return getResolvedOptions(sys.argv, [name])[name]
    return default

s3_query_path      = get_optional_arg('s3_query_path')
start_date         = get_optional_arg('start_date')
end_date           = get_optional_arg('end_date')
athena_db          = get_optional_arg('athena_db', 'prod_addi_conv')
athena_table       = get_optional_arg('athena_table')
s3_output_location = get_optional_arg('s3_output_location', 's3://ptbwa-da/prod/athena-query-results/')

if not s3_query_path:
    raise ValueError("s3_query_path 파라미터가 필요합니다.")
if not athena_table:
    raise ValueError("athena_table 파라미터가 필요합니다.")
if not start_date or not end_date:
    raise ValueError("start_date, end_date 파라미터가 필요합니다.")

start_obj = datetime.strptime(start_date, '%Y-%m-%d')
end_obj   = datetime.strptime(end_date,   '%Y-%m-%d')
date_list = [(start_obj + timedelta(days=i)).strftime('%Y-%m-%d')
             for i in range((end_obj - start_obj).days + 1)]

logger.info(f"s3_query_path: {s3_query_path}")
logger.info(f"athena_db: {athena_db}")
logger.info(f"athena_table: {athena_table}")
logger.info(f"처리 날짜: {start_date} ~ {end_date} ({len(date_list)}일)")

# 3. AWS 클라이언트 초기화
region        = 'ap-northeast-2'
s3_client     = boto3.client('s3', region_name=region)
athena_client = boto3.client('athena', region_name=region)
glue_client   = boto3.client('glue', region_name=region)

# 4. S3에서 SQL 템플릿 읽기
try:
    path = s3_query_path.replace('s3://', '')
    bucket, key = path.split('/', 1)
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    sql_template = obj['Body'].read().decode('utf-8').strip()
    logger.info("[SUCCESS] SQL 템플릿 읽기 완료")
except Exception as e:
    logger.error(f"[FAIL] SQL 읽기 실패: {e}")
    raise e

# 5. Glue Catalog에서 테이블 S3 위치 조회
try:
    table_info     = glue_client.get_table(DatabaseName=athena_db, Name=athena_table)
    table_location = table_info['Table']['StorageDescriptor']['Location'].rstrip('/')
    part_bucket    = table_location.replace('s3://', '').split('/')[0]
    part_prefix    = table_location.replace(f's3://{part_bucket}/', '').rstrip('/') + '/'
    logger.info(f"테이블 위치: {table_location}")
except Exception as e:
    logger.error(f"[FAIL] 테이블 위치 조회 실패: {e}")
    raise e

# 6. Athena 쿼리 실행 + 완료 대기
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
            state  = result['QueryExecution']['Status']['State']
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

# ── Step 1: 전체 날짜 범위 S3 오브젝트 일괄 삭제 ──────────────────────────────
logger.info(f"===== Step 1: S3 일괄 삭제 ({start_date} ~ {end_date}) =====")
all_delete_keys = []
for current_date in date_list:
    date_obj  = datetime.strptime(current_date, '%Y-%m-%d')
    prefix    = f"{part_prefix}year={date_obj.strftime('%Y')}/month={date_obj.strftime('%m')}/day={date_obj.strftime('%d')}/"
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=part_bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            all_delete_keys.append({'Key': obj['Key']})

if all_delete_keys:
    for i in range(0, len(all_delete_keys), 1000):
        s3_client.delete_objects(
            Bucket=part_bucket,
            Delete={'Objects': all_delete_keys[i:i+1000]}
        )
    logger.info(f"[SUCCESS] S3 삭제 완료: {len(all_delete_keys)}개 오브젝트")
else:
    logger.info("삭제할 S3 오브젝트 없음")

# ── Step 2: 전체 파티션 메타데이터 일괄 DROP ─────────────────────────────────
logger.info(f"===== Step 2: Athena 파티션 일괄 DROP ({len(date_list)}개) =====")
def _partition_spec(d):
    obj = datetime.strptime(d, '%Y-%m-%d')
    return f"PARTITION (year='{obj.strftime('%Y')}', month='{obj.strftime('%m')}', day='{obj.strftime('%d')}')"

partition_specs = ', '.join(_partition_spec(d) for d in date_list)
drop_sql = f"ALTER TABLE `{athena_db}`.`{athena_table}` DROP IF EXISTS {partition_specs}"
run_athena_query(drop_sql, f"파티션 일괄 DROP ({len(date_list)}개)")

# ── Step 3: 전체 범위 INSERT 1회 실행 ────────────────────────────────────────
logger.info(f"===== Step 3: INSERT ({start_date} ~ {end_date}) =====")
sql = sql_template.replace('{start_date}', start_date).replace('{end_date}', end_date)
run_athena_query(sql, f"INSERT ({athena_db}.{athena_table} / {start_date} ~ {end_date})")

logger.info(f"[DONE] 전체 완료: {athena_db}.{athena_table} / {start_date} ~ {end_date}")
job.commit()
