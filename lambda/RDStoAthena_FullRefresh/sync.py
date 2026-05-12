import boto3
import json
import pymysql
import pandas as pd
from datetime import datetime
from retry import retry
from botocore.exceptions import ClientError
from dbutils.pooled_db import PooledDB
from utils.aws import s3, glue
from utils.logger import logger


PANDAS_TO_ATHENA_TYPES = {
    'int8':            'TINYINT',
    'int16':           'SMALLINT',
    'int32':           'INT',
    'int64':           'BIGINT',
    'float32':         'FLOAT',
    'float64':         'DOUBLE',
    'bool':            'BOOLEAN',
    'object':          'STRING',
    'datetime64[ns]':  'TIMESTAMP',
}

class FullRefreshManager:
    def __init__(self, secret_name: str, db_name: str):
        self.secret_name = secret_name
        self.db_name = db_name
        self.conn = self._connect_db()

    def run(
        self,
        table_name: str,
        glue_db: str,
        glue_table: str,
        s3_bucket: str,
        s3_prefix: str,
    ):
        logger.info(f"Full Refresh 시작: {self.db_name}.{table_name}")

        df = pd.read_sql(f"SELECT * FROM {self.db_name}.{table_name}", self.conn)
        logger.info(f"{len(df)}건 조회 완료")

        self._ensure_glue_table(df, glue_db, glue_table, s3_bucket, s3_prefix)
        self._clear_s3_prefix(s3_bucket, s3_prefix)

        ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        s3_key = f"{s3_prefix}/{ts}.parquet"
        local_path = f"/tmp/{self.db_name}_{table_name}_{ts}.parquet"

        df.to_parquet(local_path, index=False, engine='pyarrow')
        s3.upload_file(local_path, s3_bucket, s3_key)
        logger.info(f"S3 업로드 완료: s3://{s3_bucket}/{s3_key}")

    def disconnect(self):
        try:
            self.conn.close()
        except Exception as e:
            logger.error(f"[DISCONNECT] {e}")

    # ── S3 ────────────────────────────────────────────────────────────────────

    def _clear_s3_prefix(self, bucket: str, prefix: str):
        paginator = s3.get_paginator('list_objects_v2')
        deleted = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix.rstrip('/') + '/'):
            objects = page.get('Contents', [])
            if objects:
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': [{'Key': o['Key']} for o in objects]},
                )
                deleted += len(objects)
        logger.info(f"기존 S3 객체 삭제: {deleted}개")

    # ── Glue ─────────────────────────────────────────────────────────────────

    def _ensure_glue_table(self, df: pd.DataFrame, glue_db: str, glue_table: str, s3_bucket: str, s3_prefix: str):
        try:
            glue.get_table(DatabaseName=glue_db, Name=glue_table)
            logger.info(f"Glue 테이블 확인: {glue_db}.{glue_table}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                logger.info(f"Glue 테이블 없음 → 자동 생성: {glue_db}.{glue_table}")
                self._create_glue_table(df, glue_db, glue_table, s3_bucket, s3_prefix)
            else:
                raise

    def _create_glue_table(self, df: pd.DataFrame, glue_db: str, glue_table: str, s3_bucket: str, s3_prefix: str):
        columns = [
            {
                'Name': col,
                'Type': PANDAS_TO_ATHENA_TYPES.get(str(dtype), 'STRING'),
            }
            for col, dtype in df.dtypes.items()
        ]

        glue.create_table(
            DatabaseName=glue_db,
            TableInput={
                'Name': glue_table,
                'TableType': 'EXTERNAL_TABLE',
                'Parameters': {
                    'classification': 'parquet',
                    'parquet.compress': 'SNAPPY',
                },
                'PartitionKeys': [],
                'StorageDescriptor': {
                    'Columns': columns,
                    'Location': f's3://{s3_bucket}/{s3_prefix}/',
                    'InputFormat': 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
                    'OutputFormat': 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
                    'Compressed': False,
                    'SerdeInfo': {
                        'SerializationLibrary': 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
                        'Parameters': {'serialization.format': '1'},
                    },
                },
            }
        )
        logger.info(f"Glue 테이블 생성 완료: {glue_db}.{glue_table} ({len(columns)}개 컬럼)")

    # ── DB ────────────────────────────────────────────────────────────────────

    @retry(tries=5, backoff=3, exceptions=(pymysql.OperationalError,))
    def _connect_db(self):
        conn = self._init_connection_pool().connection()
        logger.info("RDS 연결 완료")
        return conn

    @retry(tries=5, backoff=3, exceptions=(pymysql.OperationalError,))
    def _init_connection_pool(self):
        db_config = self._load_db_config()
        return PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=1,
            maxcached=5,
            maxshared=0,
            blocking=True,
            ping=1,
            host=db_config['host'],
            port=int(db_config.get('port', 3306)),
            user=db_config['username'],
            password=db_config['password'],
            database=self.db_name,
            charset='utf8',
            autocommit=True,
        )

    def _load_db_config(self) -> dict:
        client = boto3.session.Session().client('secretsmanager', region_name='ap-northeast-2')
        response = client.get_secret_value(SecretId=self.secret_name)
        secret = json.loads(response['SecretString'])
        logger.info(f"Secret 로드: {self.secret_name}")
        return secret
