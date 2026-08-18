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
# - s3_query_path      : S3 SQL 파일 경로 (필수)
# - start_date         : 시작 날짜 YYYY-MM-DD (end_date 와 함께 범위 지정)
# - end_date           : 종료 날짜 YYYY-MM-DD (start_date 와 함께 범위 지정)
# - date               : 단일 날짜 YYYY-MM-DD (legacy, start_date/end_date 없을 때)
# - athena_db          : Athena 데이터베이스 (기본값: prod_addi_conv)
# - athena_table       : Athena 테이블명 (필수)
# - s3_output_location : Athena 쿼리 결과 경로 (기본값: s3://ptbwa-da/prod/athena-query-results/)
def get_optional_arg(name, default=None):
    if f'--{name}' in sys.argv:
        return getResolvedOptions(sys.argv, [name])[name]
    return default

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

s3_query_path      = get_optional_arg('s3_query_path')
start_date         = get_optional_arg('start_date')
end_date           = get_optional_arg('end_date')
date               = get_optional_arg('date')
athena_db          = get_optional_arg('athena_db', 'prod_addi_conv')
athena_table       = get_optional_arg('athena_table')
s3_output_location = get_optional_arg('s3_output_location', 's3://ptbwa-da/prod/athena-query-results/')

if not s3_query_path:
    raise ValueError("s3_query_path 파라미터가 필요합니다.")
if not athena_table:
    raise ValueError("athena_table 파라미터가 필요합니다.")

# 날짜 범위 결정: start_date/end_date > date > 어제
if start_date and end_date:
    pass
elif date:
    start_date = date
    end_date   = date
else:
    start_date = yesterday
    end_date   = yesterday

# 날짜 리스트 생성
start_obj = datetime.strptime(start_date, '%Y-%m-%d')
end_obj   = datetime.strptime(end_date,   '%Y-%m-%d')
date_list = [(start_obj + timedelta(days=i)).strftime('%Y-%m-%d')
             for i in range((end_obj - start_obj).days + 1)]

logger.info(f"s3_query_path: {s3_query_path}")
logger.info(f"athena_db: {athena_db}")
logger.info(f"athena_table: {athena_table}")
logger.info(f"처리 날짜: {start_date} ~ {end_date} ({len(date_list)}일)")

# 3. AWS 클라이언트 초기화
region = 'ap-northeast-2'
s3_client     = boto3.client('s3', region_name=region)
athena_client = boto3.client('athena', region_name=region)
glue_client   = boto3.client('glue', region_name=region)

# 4. S3에서 SQL 템플릿 읽기 (1회)
try:
    path = s3_query_path.replace('s3://', '')
    bucket, key = path.split('/', 1)
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    sql_template = obj['Body'].read().decode('utf-8').strip()
    logger.info("[SUCCESS] SQL 템플릿 읽기 완료")
except Exception as e:
    logger.error(f"[FAIL] SQL 읽기 실패: {e}")
    raise e

# 5. Glue Catalog에서 테이블 S3 위치 조회 (1회)
try:
    table_info = glue_client.get_table(DatabaseName=athena_db, Name=athena_table)
    table_location = table_info['Table']['StorageDescriptor']['Location'].rstrip('/')
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

# 6-1. COUNT(*) 실행 + 결과값 파싱
# INSERT 쿼리는 SUCCEEDED여도 0건일 수 있어(예: 조인 대상 테이블이 비어있는 경우)
# 별도로 실제 적재 건수를 세어 로그에 남긴다.
def run_athena_count_query(query, description):
    execution_id = run_athena_query(query, description)
    result = athena_client.get_query_results(QueryExecutionId=execution_id)
    rows = result['ResultSet']['Rows']
    return int(rows[1]['Data'][0]['VarCharValue'])

# 7. 날짜별 루프
for current_date in date_list:
    logger.info(f"===== 처리 중: {current_date} =====")

    date_obj   = datetime.strptime(current_date, '%Y-%m-%d')
    year       = date_obj.strftime('%Y')
    month      = date_obj.strftime('%m')
    day        = date_obj.strftime('%d')
    date_slash = f"{year}/{month}/{day}"

    sql = sql_template.replace('{date}', current_date).replace('{date_slash}', date_slash)
    partition_s3_path = f"{table_location}/year={year}/month={month}/day={day}/"

    # S3 파티션 데이터 삭제
    try:
        part_bucket, part_prefix = partition_s3_path.replace('s3://', '').split('/', 1)
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=part_bucket, Prefix=part_prefix)

        delete_keys = []
        for page in pages:
            for obj in page.get('Contents', []):
                delete_keys.append({'Key': obj['Key']})

        if delete_keys:
            for i in range(0, len(delete_keys), 1000):
                s3_client.delete_objects(
                    Bucket=part_bucket,
                    Delete={'Objects': delete_keys[i:i+1000]}
                )
            logger.info(f"[SUCCESS] S3 파티션 삭제 완료: {len(delete_keys)}개 ({current_date})")
        else:
            logger.info(f"삭제할 파일 없음: {partition_s3_path}")
    except Exception as e:
        logger.error(f"[FAIL] S3 파티션 삭제 실패 ({current_date}): {e}")
        raise e

    # Athena 파티션 메타데이터 삭제
    drop_partition_sql = f"ALTER TABLE `{athena_db}`.`{athena_table}` DROP IF EXISTS PARTITION (year='{year}', month='{month}', day='{day}')"
    run_athena_query(drop_partition_sql, f"파티션 삭제 ({current_date})")

    # INSERT 실행
    run_athena_query(sql, f"INSERT ({athena_db}.{athena_table} / {current_date})")

    # 적재 건수 확인
    # SELECT는 DDL(ALTER TABLE 등)과 달리 Presto 파서를 타서 백틱이 아닌 큰따옴표로 식별자를 감싸야 한다.
    # 이 카운트 체크 자체가 실패해도 INSERT는 이미 끝난 상태이므로, job을 죽이지 않고 로그만 남긴다.
    try:
        count_sql = (
            f'SELECT COUNT(*) AS cnt FROM "{athena_db}"."{athena_table}" '
            f"WHERE year='{year}' AND month='{month}' AND day='{day}'"
        )
        row_count = run_athena_count_query(count_sql, f"COUNT ({athena_db}.{athena_table} / {current_date})")
        if row_count == 0:
            logger.warning(f"[ROW_COUNT] {athena_db}.{athena_table} / {current_date}: 0건 적재됨 (INSERT는 SUCCEEDED)")
        else:
            logger.info(f"[ROW_COUNT] {athena_db}.{athena_table} / {current_date}: {row_count}건 적재")
    except Exception as e:
        logger.error(f"[ROW_COUNT] 건수 확인 실패 ({athena_db}.{athena_table} / {current_date}): {e}")

logger.info(f"[DONE] 전체 완료: {athena_db}.{athena_table} / {start_date} ~ {end_date}")
job.commit()
