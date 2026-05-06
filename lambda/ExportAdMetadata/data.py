import pymysql
import pandas as pd
import boto3
import json
import csv
import dateutil
from datetime import datetime
from retry import retry
from botocore.exceptions import ClientError
from dbutils.pooled_db import PooledDB
from utils.aws import s3
from utils.logger import logger


class ExportData:
    def __init__(self, db_cluster_name: str, db_name: str):
        self.db_cluster_name = db_cluster_name
        self.db_name=db_name
        self.conn = self.connect_db()

    def proc_all(self, table_name: str, alias: str = None):
        try:
            def clean_text_field(text):
                if pd.isna(text) or not isinstance(text, str):
                    return text
                # 모든 줄바꿈과 특수문자를 안전하게 처리
                text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').replace('|', ' ')
                text = text.replace('"', "'")
                # 연속된 공백 제거
                text = ' '.join(text.split())
                return text
            current = datetime.now(dateutil.tz.gettz('Asia/Seoul'))
            s3_name = alias if alias else table_name
            lambda_file_path = f"/tmp/{self.db_name}_{s3_name}_{str(current)}.csv"
            target_bucket='ptbwa-propfit'
            target_file_path = f"aws_rds/{self.db_cluster_name}/{self.db_name}/{s3_name}"

            logger.info(f"Table Name: {table_name}")
            logger.info(f"Lambda Temp File Path: {lambda_file_path}")
            logger.info(f"Target Path: s3://{target_bucket}/{target_file_path}/{s3_name}.csv")

            # 매핑 정보 조회 쿼리 실행
            
            # 컬럼명 가져오기
            
            column_query = f"SELECT * FROM {self.db_name}.{table_name} limit 1"
            df = pd.read_sql(column_query, self.conn)
            columns = df.columns

            select_statement = []
            for c in columns:
                select_statement.append(f"COALESCE({c}, '') AS `{c}`")
            
            query = f"SELECT {','.join(select_statement)} FROM {self.db_name}.{table_name}"

            logger.info(f"Query: {query}")

            df = pd.read_sql(query, self.conn)

            # 모든 문자열 컬럼에 적용
            df = df.astype(str).apply(lambda col: col.map(clean_text_field))
            df = df.fillna('')
            df = df.replace(to_replace=['None'], value=[''])

            logger.info(f"{table_name}")
            # logger.info(f"{', '.join(df.columns)}")
            for index, row in df.iterrows():
                logger.info(f'[{table_name}] ' + '\t'.join(row.astype(str)))

            # df.to_csv(lambda_file_path, index=False, quoting=csv.QUOTE_ALL)
            # if self.db_name == 'addi' and table_name == 'code':
            #     df.to_csv(lambda_file_path, sep="|", index=False)        
            # else :
            df.to_csv(lambda_file_path, sep="\t", index=False)
            s3.upload_file(lambda_file_path, target_bucket, f'{target_file_path}/{s3_name}.csv')

            
        except Exception as e:
            logger.error(f'{table_name} 추출 시 오류 발생: {e}')
            pass


    @retry(tries=10, backoff=5)
    def connect_db(self) -> pymysql.connections.Connection:
        try:
            """커넥션 풀에서 커넥션 가져오기"""
            pool = self.init_connection_pool()
            conn = pool.connection()
            
            logger.info("RDS 커넥션 풀에서 연결 획득!")

            return conn
        except Exception as e:
            logger.error(f'[CONNECT-DB]{e}')
            raise e
#     return conn

    # @retry(tries=10, backoff=5)
    def load_db_config(self) -> dict:
        try:
            if self.db_cluster_name=="database-1" and self.db_name=="ptbwa_propfit":
                secret_name = "propfit_rds_startwith_P_1234"
                region_name = "ap-northeast-2"
            elif self.db_cluster_name=="database-addi" and self.db_name=="addi":
                secret_name = "rds-addi"
                region_name = "ap-northeast-2"
            elif self.db_cluster_name=="database-de" and self.db_name=="prod_data_service":
                secret_name = "database_de"
                region_name = "ap-northeast-2"
            else:
                raise ValueError("DB 연결 정보를 찾을 수 없습니다")
            
            session = boto3.session.Session()
            logger.info(f"Screct Name: {secret_name}")
            client = session.client(service_name='secretsmanager', region_name=region_name)
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
            secret = get_secret_value_response['SecretString']

            logger.info("RDS 연결 정보 불러오기 완료!")

            return json.loads(secret)
        except Exception as e:
            logger.error(f'[LOAD-DB-CONFIG]{e}')
            raise e

    @retry(tries=10, backoff=5)
    def init_connection_pool(self):
        try:
            """커넥션 풀 초기화"""
            # global connection_pool
            
            # if connection_pool is None:        
            db_config = self.load_db_config()
            
            connection_pool = PooledDB(
                creator=pymysql,  # 사용할 DB 모듈
                maxconnections=5,  # 최대 커넥션 수
                mincached=2,       # 초기 시작 시 최소 idle 커넥션 수
                maxcached=5,       # 최대 idle 커넥션 수
                maxshared=0,       # 최대 공유 커넥션 수 (0=무제한)
                blocking=True,     # 커넥션 풀이 가득 찰 경우 대기할지 여부
                maxusage=None,     # 하나의 커넥션 최대 재사용 횟수 (None=무제한)
                setsession=[],     # 커넥션 생성 시 실행할 SQL 명령어 리스트
                ping=1,            # 커넥션 체크 방법 (0=None, 1=default, 2=cursor.execute(), 4=cursor.ping())
                host=db_config['db_host'],
                user=db_config['db_user'],
                password=db_config['db_password'],
                database=db_config['db'],
                charset='utf8',
                autocommit=True
            )
            
            logger.info(f"커넥션 풀 초기화 완료! (최대 커넥션: 5개)")

            return connection_pool
        except Exception as e:
            logger.error(f'[INIT-CONNECTION-POOL]{e}')
            raise e

    @retry(tries=10, backoff=5)
    def disconnect_db(self):
        try:
            """커넥션을 풀에 반환"""
            self.conn.close()  # 실제로는 풀에 반환됨
            logger.info("커넥션을 풀에 반환!")
        except Exception as e:
            logger.error(f'[DISCONNECT-DB]{e}')
            raise e

    # 풀 상태 확인 함수 (옵션)
    @retry(tries=10, backoff=5)
    def get_pool_status(self):
        try:
            """현재 커넥션 풀 상태 확인"""
            if connection_pool:
                return {
                    "connections": connection_pool._connections,
                    "idle_cache": len(connection_pool._idle_cache),
                    "lock": connection_pool._lock
                }
            return None
        except Exception as e:
            logger.error(f'[GET-POOL-STATUS]{e}')
            raise e
