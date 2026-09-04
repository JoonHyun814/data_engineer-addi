#!/usr/bin/env python
# coding: utf-8

# # Athena 결과를 RDS에 적재

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

from datetime import datetime


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
# - **date**: 집계 날짜. 일자 별이라면 `'%Y-%m-%d'`, 시간 별이라면 `'%Y-%m-%d %H:%M:%S'` 형식
# - **athena_result_base_path**: AWS Data Catalog 테이블 데이터 위치
# - **athena_db**: AWS Data Catalog 데이터베이스 이름
# - **athena_table** = AWS Data Catalog 테이블 이름
# - **rdb_db**: RDB 데이터베이스 이름
# - **rdb_table**: RDB 테이블 이름

# In[49]:


try:
    args = getResolvedOptions(sys.argv, ["athena_result_base_path", "date", "athena_db", "athena_table", "rdb_db", "rdb_table"])
    date = args['date'] # 날짜 형식인지 확인
    athena_result_base_path = args['athena_result_base_path'] if args['athena_result_base_path'][-1] != '/' else args['athena_result_base_path'][:-1] 
    athena_db = args['athena_db']
    athena_table = args['athena_table']
    rdb_db = args['rdb_db']
    rdb_table = args['rdb_table']
    
    logger.info(f"Date: {date}")
    logger.info(f"Athena Result Base Path: {athena_result_base_path}")
    logger.info(f"Athena DB: {athena_db}")
    logger.info(f"Athena Table: {athena_table}")
    logger.info(f"RDS DB: {rdb_db}")
    logger.info(f"RDS Table: {rdb_table}")
except Exception as e:
    logger.error(f"[FAIL] Job Run Parameter Error: {e}")
    raise e


# ## (TEST) Job Run Parameter

# In[8]:


# date = "2025-11-19 06:00:00"
# athena_result_base_path = "s3://ptbwa-da/prod/addi_report_basic_customer_hour"
# athena_db = "prod-ptbwa-da"
# athena_table = "addi_report_basic_customer_hour"
# rdb_db = "addi"
# rdb_table = "report_basic_customer_hour_test"


# In[5]:


# date = "2025-12-01"
# athena_result_base_path = "s3://ptbwa-da/prod/addi_report_basic_customer_daily"
# athena_db = "prod-ptbwa-da"
# athena_table = "addi_report_basic_customer_daily"
# rdb_db = "addi"
# rdb_table = "report_basic_customer_daily_test"


# ## 집계 날짜 설정

# In[6]:


try:
    try:
        date_object = datetime.strptime(date, "%Y-%m-%d")
        year = "{:02d}".format(date_object.year)
        month = "{:02d}".format(date_object.month)
        day = "{:02d}".format(date_object.day)
        if rdb_db == 'addi' and  (rdb_table.startswith('report_basic_customer_daily') or rdb_table.startswith('report_channel_customer_daily') or rdb_table.startswith('report_area_customer_daily') or rdb_table.startswith('report_basic_customer_tax_daily')):
            athena_result_path = f"{athena_result_base_path}/date={year}-{month}-{day}/"
            query_where = f"date='{year}-{month}-{day}'"
        else:
            athena_result_path = f"{athena_result_base_path}/year={year}/month={month}/day={day}/"
            query_where = f"year='{year}' and month='{month}' and day='{day}'"
            
        rdb_delete_query_where = f"day = '{date}'"
        logger.info(f"RDB Delete Query Where: {rdb_delete_query_where}")
    except:
        try:
            date_object = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            year = "{:02d}".format(date_object.year)
            month = "{:02d}".format(date_object.month)
            day = "{:02d}".format(date_object.day)
            hour = "{:02d}".format(date_object.hour)
            
            if rdb_db == 'addi' and rdb_table.startswith('report_basic_customer_hour'):
                athena_result_path = f"{athena_result_base_path}/date={year}-{month}-{day}/hh={hour}"
                query_where = f"date='{year}-{month}-{day}' and hh='{hour}'"    
                rdb_delete_query_where = f"day='{year}-{month}-{day}' and hh='{hour}'"
            else:
                athena_result_path = f"{athena_result_base_path}/year={year}/month={month}/day={day}/hour={hour}"
                query_where = f"year='{year}' and month='{month}' and day='{day}' and hour='{hour}'"
                rdb_delete_query_where = f"datetime = '{date}'"
            
            logger.info(f"RDB Delete Query Where: {rdb_delete_query_where}")            
        except ValueError:
            raise ValueError("지원하지 않는 날짜 형식입니다. '%Y-%m-%d' 또는 '%Y-%m-%d %H:%M:%S' 형식이어야 합니다.")


    logger.info(f"Athena Result Path: {athena_result_path}")
    logger.info(f"Query Where: {query_where}")
    
    # print(f"Athena Result Path: {athena_result_path}")
    # print(f"Query Where: {query_where}")
    
    logger.info(f"[SUCCESS] 집계 날짜 설정 완료! ")
except Exception as e:
    logger.error(f"[FAIL] 집계 날짜 설정 실패!: {e}")
    raise  e


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


# ## Process

# ### AWS Catalog에서 필요한 컬럼만 가져오기
# - **일 별 테이블** 
#   - 테이블 명 마지막에 `_daily`가 붙여져 있음
#     - ptbwa_propfit.report_summary_daily, ptbwa_propfit.report_summary_channel_daily, ptbwa_propfit.report_summary_reach_daily
#     - addi.report_summary_daily, addi.report_summary_channel_daily, addi.report_summary_reach_daily
#   - AWS Catalog에서는 `day`라는 파티션 컬럼이 있어 날짜 컬럼 명을 `date`으로 변경하였음. 따라서 RDB에 집계 데이터를 넣을 때에는 다시 `date` 컬럼 명을 `day`로 변경해야 함   
#   - 파티션 컬럼 `year`, `month`, `day` 삭제      
# - **시간 별 테이블** 
#   - 테이블 명 마지막에 `_hour`가 붙여져 있음
#     - ptbwa_propfit.report_summary_hour   
#   - 파티션 컬럼 `year`, `month`, `day` 삭제      

# In[9]:


try:
    if athena_table.endswith('daily'):
        all_col_df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` limit 1")
        select_columns = all_col_df.columns  
        if 'date' in select_columns:
            select_columns.remove('date') # -> 컬럼 이름을 day로 변경
            select_columns.append('date as day')
        if 'year' in select_columns:
            select_columns.remove('year')
        if 'month' in select_columns:
            select_columns.remove('month')
        if 'day' in select_columns:
            select_columns.remove('day')    
        # 
        select_query = f"select {','.join(select_columns)} from `{athena_db}`.`{athena_table}` where {query_where}"
        logger.info(f"Select Query: {select_query}")
        df = spark.sql(select_query)
        # 
    elif athena_table.endswith('hour'):
        all_col_df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` limit 1")
        select_columns = all_col_df.columns    
        if 'date' in select_columns:
            select_columns.remove('date') # -> 컬럼 이름을 day로 변경
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
        logger.info(f"Select Query: {select_query}")
        df = spark.sql(select_query)
        
    else:
        df = spark.sql(f"select * from `{athena_db}`.`{athena_table}` where {query_where}")
    
    logger.info(f"[SUCCESS] AWS Data Catalog에서 필요한 컬럼만 추출 성공!")
except Exception as e:
    logger.error(f"[FAIL] AWS Data Catalog에서 필요한 컬럼만 추출 실패!: {e}")
    raise e

# df = spark.sql(f"select * from `{athena_db}`.{athena_table} limit 10")


# In[23]:


# df.show()
# select_query


# ### 기존 데이터 삭제

# In[10]:


try:
    if rdb_db == 'addi' and  (rdb_table.startswith('report_basic_customer_daily') or rdb_table.startswith('report_hourly_customer_daily') or rdb_table.startswith('report_channel_customer_daily') or rdb_table.startswith('report_area_customer_daily') or rdb_table.startswith('report_basic_customer_hour') or rdb_table.startswith('report_basic_customer_tax_daily')):
        delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where} and media_type in (select CODECD from code where CODESETCD = 'SD0064' and ADDCD2='Y')" 
    elif rdb_db =='addi' and (rdb_table.startswith('report_summary_daily') or rdb_table.startswith('report_summary_channel_daily')):
        delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where} and mediacd not in (select CODECD from code where CODESETCD = 'SD0064')"
    else:    
        delete_query = f"DELETE FROM {rdb_db}.{rdb_table} WHERE {rdb_delete_query_where}"
    logger.info(f"Delete Query: {delete_query}")
    # print(delete_query)    

    cur.execute(delete_query)
    conn.commit()
    logger.info(f"[SUCCESS] {rdb_db}.{rdb_table}에 DELETE query 실행 성공!")
except Exception as e:
    logger.error(f"[FAIL] {rdb_db}.{rdb_table}에 DELETE query 실행 실패!: {e}")
    raise e


# ### 데이터 적재

# In[11]:


try:
    for row in df.collect():
        vals = list()
        for col in df.columns:
            val = eval(f"row.{col}")
            vals.append(f"'{val}'")  
        
        insert_query = f"INSERT INTO {rdb_db}.{rdb_table}({','.join(df.columns)}) VALUES ({','.join(vals)})"        
        logger.info(f"Insert Query: {insert_query}")
        cur.execute(insert_query)
        # print(f"Insert Query: {insert_query}")
    conn.commit()
    logger.error(f"[SUCCESS] MySQL 테이블({rdb_db}.{rdb_table})에 데이터 저장 성공!")
except Exception as e:
    logger.error(f"[FAIL] MySQL 테이블({rdb_db}.{rdb_table})에 데이터 저장 실패!: {e}")
    raise e


# ### DB 연결 종료

# In[65]:


cur.close()
conn.close()


# In[ ]:




