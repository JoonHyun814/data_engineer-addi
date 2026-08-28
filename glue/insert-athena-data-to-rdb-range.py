#!/usr/bin/env python
# coding: utf-8

# # Athena 결과를 RDS에 적재 (날짜 범위)

# ## Session 설정
# - 원격으로 푸쉬할 때에는 꼭 주석처리 할 것!

# In[21]:


# %iam_role arn:aws:iam::170217667865:role/AWSGlueServiceRole
# %idle_timeout 60
# %glue_version 4.0
# %worker_type G.1X
# %number_of_workers 2
# %extra_jars s3://ptbwa-basic/glue-job/json-serde.jar,s3://ptbwa-basic/glue-job/delta-core_2.12-1.0.1.jar


# ## Load Package

# In[1]:


import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job


# In[2]:


import boto3
import pymysql
import json

from datetime import datetime, timedelta


# ## Spark, Job, Logger 설정

# In[3]:


sc = SparkContext.getOrCreate()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
logger = glueContext.get_logger()


# ## AWS Boto Client 생성

# In[4]:


region_name = "ap-northeast-2"

s3_client = boto3.client('s3')
glue_client = boto3.client("glue")
lambda_client = boto3.client("lambda")
secret_manager_client = boto3.client(service_name='secretsmanager', region_name=region_name)


# ## Job Run Parameter
# - **start_date**: 시작 날짜 `'%Y-%m-%d'` 형식
# - **end_date**: 종료 날짜 `'%Y-%m-%d'` 형식
# - **athena_result_base_path**: AWS Data Catalog 테이블 데이터 위치
# - **athena_db**: AWS Data Catalog 데이터베이스 이름
# - **athena_table** = AWS Data Catalog 테이블 이름
# - **rdb_db**: RDB 데이터베이스 이름
# - **rdb_table**: RDB 테이블 이름

# In[49]:


try:
    args = getResolvedOptions(sys.argv, ["athena_result_base_path", "start_date", "end_date", "athena_db", "athena_table", "rdb_db", "rdb_table"])
    start_date = args['start_date']
    end_date   = args['end_date']
    athena_result_base_path = args['athena_result_base_path'] if args['athena_result_base_path'][-1] != '/' else args['athena_result_base_path'][:-1]
    athena_db  = args['athena_db']
    athena_table = args['athena_table']
    rdb_db     = args['rdb_db']
    rdb_table  = args['rdb_table']

    logger.info(f"Start Date: {start_date}")
    logger.info(f"End Date: {end_date}")
    logger.info(f"Athena Result Base Path: {athena_result_base_path}")
    logger.info(f"Athena DB: {athena_db}")
    logger.info(f"Athena Table: {athena_table}")
    logger.info(f"RDS DB: {rdb_db}")
    logger.info(f"RDS Table: {rdb_table}")
except Exception as e:
    logger.error(f"[FAIL] Job Run Parameter Error: {e}")
    raise e


# ## (TEST) Job Run Parameter

# In[5]:


# start_date = "2026-01-01"
# end_date   = "2026-05-10"
# athena_result_base_path = "s3://ptbwa-da/prod/prod_addi_conv/report_addi_conv_app"
# athena_db  = "prod_addi_conv"
# athena_table = "report_addi_conv_app"
# rdb_db     = "addi"
# rdb_table  = "report_addi_conv_app"


# ## 날짜 범위 생성

# In[6]:


try:
    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj   = datetime.strptime(end_date,   "%Y-%m-%d")
    date_list = [(start_obj + timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range((end_obj - start_obj).days + 1)]
    logger.info(f"처리 날짜 수: {len(date_list)}일 ({start_date} ~ {end_date})")
except Exception as e:
    logger.error(f"[FAIL] 날짜 범위 생성 실패: {e}")
    raise e


# ## RDB

# ### RDB 연결 정보

# In[7]:


try:
    if rdb_db == "ptbwa_propfit":
        secret_name = "propfit_rds_startwith_P_1234"
        driver = "com.mysql.cj.jdbc.Driver"
    elif rdb_db == "addi":
        secret_name = "rds-addi"
        driver = "com.mysql.cj.jdbc.Driver"
    else:
        raise Exception("Secret Manager에 등록되지 않은 DB 연결 정보입니다")

    secret_value_response = secret_manager_client.get_secret_value(SecretId=secret_name)
    secret = secret_value_response['SecretString']
    db_config = json.loads(secret)
    db_name = db_config['db']

    logger.info("[SUCCESS] DB 연결 정보 찾기 완료!")
except Exception as e:
    logger.error(f"[FAIL] DB 연결 정보 찾기 실패!: {e}")
    raise e


# ### RDB 연결

# In[8]:


try:
    conn = pymysql.connect(
        host=db_config['db_host'],
        user=db_config['db_user'],
        password=db_config['db_password'],
        db=rdb_db,
        charset="utf8",
        cursorclass=pymysql.cursors.DictCursor
    )
    cur = conn.cursor()
    logger.info(f"[SUCCESS] RDB({rdb_db}) 연결 성공!")
except Exception as e:
    logger.error(f"[FAIL] RDB({rdb_db}) 연결 실패!: {e}")
    raise e


# ## Process (날짜 루프)

# In[9]:


for date in date_list:
    logger.info(f"===== 처리 중: {date} =====")

    # ### 집계 날짜 설정
    try:
        date_object = datetime.strptime(date, "%Y-%m-%d")
        year  = "{:02d}".format(date_object.year)
        month = "{:02d}".format(date_object.month)
        day   = "{:02d}".format(date_object.day)

        if rdb_db == 'addi' and (rdb_table.startswith('report_basic_customer_daily') or rdb_table.startswith('report_channel_customer_daily') or rdb_table.startswith('report_area_customer_daily')):
            athena_result_path = f"{athena_result_base_path}/date={year}-{month}-{day}/"
            query_where = f"date='{year}-{month}-{day}'"
        else:
            athena_result_path = f"{athena_result_base_path}/year={year}/month={month}/day={day}/"
            query_where = f"year='{year}' and month='{month}' and day='{day}'"

        rdb_delete_query_where = f"year = '{year}' AND month = '{month}' AND day = '{day}'"
        logger.info(f"Query Where: {query_where}")
    except Exception as e:
        logger.error(f"[FAIL] 집계 날짜 설정 실패 ({date}): {e}")
        raise e

    # ### AWS Catalog에서 데이터 추출
    try:
        if athena_table.endswith('daily'):
            all_col_df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` limit 1")
            select_columns = all_col_df.columns
            if 'date' in select_columns:
                select_columns.remove('date')
                select_columns.append('date as day')
            if 'year' in select_columns:
                select_columns.remove('year')
            if 'month' in select_columns:
                select_columns.remove('month')
            if 'day' in select_columns:
                select_columns.remove('day')
            select_query = f"select {','.join(select_columns)} from `{athena_db}`.`{athena_table}` where {query_where}"
            df = spark.sql(select_query)
        elif athena_table.endswith('hour'):
            all_col_df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` limit 1")
            select_columns = all_col_df.columns
            if 'date' in select_columns:
                select_columns.remove('date')
                select_columns.append('date as day')
            if 'year' in select_columns:
                select_columns.remove('year')
            if 'month' in select_columns:
                select_columns.remove('month')
            if 'day' in select_columns:
                select_columns.remove('day')
            if 'hour' in select_columns:
                select_columns.remove('hour')
            select_query = f"select {','.join(select_columns)} from `{athena_db}`.`{athena_table}` where {query_where}"
            df = spark.sql(select_query)
        else:
            df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` where {query_where}")

        logger.info(f"[SUCCESS] Athena 데이터 추출 완료 ({date})")
    except Exception as e:
        logger.error(f"[FAIL] Athena 데이터 추출 실패 ({date}): {e}")
        raise e

    # ### 기존 데이터 삭제
    try:
        if rdb_db == 'addi' and (rdb_table.startswith('report_basic_customer_daily') or rdb_table.startswith('report_hourly_customer_daily') or rdb_table.startswith('report_channel_customer_daily') or rdb_table.startswith('report_area_customer_daily') or rdb_table.startswith('report_basic_customer_hour')):
            delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where} and media_type in (select CODECD from code where CODESETCD = 'SD0064' and ADDCD2='Y')"
        elif rdb_db == 'addi' and (rdb_table.startswith('report_summary_daily') or rdb_table.startswith('report_summary_channel_daily')):
            delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where} and mediacd not in (select CODECD from code where CODESETCD = 'SD0064')"
        else:
            delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where}"

        cur.execute(delete_query)
        conn.commit()
        logger.info(f"[SUCCESS] DELETE 완료 ({date})")
    except Exception as e:
        logger.error(f"[FAIL] DELETE 실패 ({date}): {e}")
        raise e

    # ### 데이터 적재
    try:
        for row in df.collect():
            vals = list()
            for col in df.columns:
                val = eval(f"row.{col}")
                # Athena에서 NULL로 채운 값이 df.collect() 시 Python None이 아니라
                # 문자열 'None'으로 넘어오는 경우가 있어 (예: revenue 전체가 NULL인 파티션),
                # 'None'인 str.을 그냥 f-string 처리하면 MySQL에 문자열 'None'이 그대로 들어가
                # DataError(Incorrect double value)가 난다. 명시적으로 같이 걸러준다.
                vals.append("NULL" if val is None or val == 'None' else f"'{val}'")
            insert_query = f"INSERT INTO {rdb_db}.{rdb_table}({','.join(df.columns)}) VALUES ({','.join(vals)})"
            cur.execute(insert_query)
        conn.commit()
        logger.info(f"[SUCCESS] INSERT 완료 ({date})")
    except Exception as e:
        logger.error(f"[FAIL] INSERT 실패 ({date}): {e}")
        raise e


# ### DB 연결 종료

# In[65]:


cur.close()
conn.close()
