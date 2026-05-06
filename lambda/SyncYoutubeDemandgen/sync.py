import boto3
import json
import pymysql
import pandas as pd
import dateutil
from datetime import datetime
from retry import retry
from botocore.exceptions import ClientError
from dbutils.pooled_db import PooledDB
from utils.aws import s3, glue, ssm
from utils.logger import logger


MYSQL_TO_ATHENA_TYPES = {
    'tinyint': 'TINYINT',
    'smallint': 'SMALLINT',
    'mediumint': 'INT',
    'int': 'INT',
    'integer': 'INT',
    'bigint': 'BIGINT',
    'float': 'FLOAT',
    'double': 'DOUBLE',
    'decimal': 'DOUBLE',
    'numeric': 'DOUBLE',
    'char': 'STRING',
    'varchar': 'STRING',
    'text': 'STRING',
    'mediumtext': 'STRING',
    'longtext': 'STRING',
    'tinytext': 'STRING',
    'enum': 'STRING',
    'set': 'STRING',
    'date': 'DATE',
    'datetime': 'TIMESTAMP',
    'timestamp': 'TIMESTAMP',
    'time': 'STRING',
    'year': 'INT',
    'bool': 'BOOLEAN',
    'boolean': 'BOOLEAN',
    'json': 'STRING',
}

SECRET_MAP = {
    ('database-1', 'ptbwa_propfit'): 'propfit_rds_startwith_P_1234',
    ('database-addi', 'addi'): 'rds-addi',
    ('database-de', 'prod_data_service'): 'database_de',
}


class SyncManager:
    def __init__(self, db_cluster_name: str, db_name: str):
        self.db_cluster_name = db_cluster_name
        self.db_name = db_name
        self.conn = self._connect_db()

    def run(
        self,
        table_name: str,
        watermark_col: str,
        glue_db: str,
        glue_table: str,
        s3_bucket: str,
        s3_prefix: str,
    ):
        watermark_key = f'/addi/sync/{self.db_name}/{table_name}/last_{watermark_col}'
        last_value = self._get_watermark(watermark_key)

        logger.info(f"워터마크 [{watermark_col}]: {last_value or '최초 실행 - 전체 추출'}")

        if last_value is None:
            df = pd.read_sql(
                f"SELECT * FROM {self.db_name}.{table_name} ORDER BY {watermark_col}",
                self.conn
            )
        else:
            df = pd.read_sql(
                f"SELECT * FROM {self.db_name}.{table_name} WHERE {watermark_col} > %s ORDER BY {watermark_col}",
                self.conn,
                params=(last_value,)
            )

        if df.empty:
            logger.info("신규 데이터 없음 → 스킵")
            return

        logger.info(f"{len(df)}건 신규 데이터 감지")

        self._ensure_glue_table(table_name, glue_db, glue_table, s3_bucket, s3_prefix)

        dt = datetime.now(dateutil.tz.gettz('Asia/Seoul')).strftime('%Y-%m-%d')
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        s3_key = f"{s3_prefix}/dt={dt}/{ts}.csv"
        local_path = f"/tmp/{self.db_name}_{table_name}_{ts}.csv"

        df.to_csv(local_path, sep="\t", index=False)
        s3.upload_file(local_path, s3_bucket, s3_key)
        logger.info(f"S3 업로드 완료: s3://{s3_bucket}/{s3_key}")

        self._register_partition(glue_db, glue_table, s3_bucket, s3_prefix, dt)

        new_watermark = str(df[watermark_col].max())
        self._set_watermark(watermark_key, new_watermark)
        logger.info(f"워터마크 업데이트: {new_watermark}")

    def disconnect(self):
        try:
            self.conn.close()
        except Exception as e:
            logger.error(f"[DISCONNECT] {e}")

    # ── Glue ─────────────────────────────────────────────────────────────────

    def _ensure_glue_table(self, rds_table: str, glue_db: str, glue_table: str, s3_bucket: str, s3_prefix: str):
        try:
            glue.get_table(DatabaseName=glue_db, Name=glue_table)
            logger.info(f"Glue 테이블 확인: {glue_db}.{glue_table}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                logger.info(f"Glue 테이블 없음 → 자동 생성: {glue_db}.{glue_table}")
                self._create_glue_table(rds_table, glue_db, glue_table, s3_bucket, s3_prefix)
            else:
                raise

    def _create_glue_table(self, rds_table: str, glue_db: str, glue_table: str, s3_bucket: str, s3_prefix: str):
        col_df = pd.read_sql(
            "SELECT COLUMN_NAME, DATA_TYPE "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            self.conn,
            params=(self.db_name, rds_table)
        )

        columns = [
            {
                'Name': row['COLUMN_NAME'],
                'Type': MYSQL_TO_ATHENA_TYPES.get(row['DATA_TYPE'].lower(), 'STRING'),
            }
            for _, row in col_df.iterrows()
        ]

        glue.create_table(
            DatabaseName=glue_db,
            TableInput={
                'Name': glue_table,
                'TableType': 'EXTERNAL_TABLE',
                'Parameters': {'classification': 'csv'},
                'PartitionKeys': [{'Name': 'dt', 'Type': 'STRING'}],
                'StorageDescriptor': {
                    'Columns': columns,
                    'Location': f's3://{s3_bucket}/{s3_prefix}/',
                    'InputFormat': 'org.apache.hadoop.mapred.TextInputFormat',
                    'OutputFormat': 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat',
                    'Compressed': False,
                    'SerdeInfo': {
                        'SerializationLibrary': 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe',
                        'Parameters': {
                            'field.delim': '\t',
                            'skip.header.line.count': '1',
                        },
                    },
                },
            }
        )
        logger.info(f"Glue 테이블 생성 완료: {glue_db}.{glue_table} ({len(columns)}개 컬럼)")

    def _register_partition(self, glue_db: str, glue_table: str, s3_bucket: str, s3_prefix: str, dt: str):
        try:
            glue.get_partition(DatabaseName=glue_db, TableName=glue_table, PartitionValues=[dt])
            logger.info(f"파티션 이미 존재: dt={dt}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                table_info = glue.get_table(DatabaseName=glue_db, Name=glue_table)['Table']
                sd = {
                    **table_info['StorageDescriptor'],
                    'Location': f's3://{s3_bucket}/{s3_prefix}/dt={dt}',
                }
                glue.create_partition(
                    DatabaseName=glue_db,
                    TableName=glue_table,
                    PartitionInput={'Values': [dt], 'StorageDescriptor': sd},
                )
                logger.info(f"파티션 등록 완료: dt={dt}")
            else:
                raise

    # ── Watermark ─────────────────────────────────────────────────────────────

    def _get_watermark(self, key: str):
        try:
            return ssm.get_parameter(Name=key)['Parameter']['Value']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                return None
            raise

    def _set_watermark(self, key: str, value: str):
        ssm.put_parameter(Name=key, Value=value, Type='String', Overwrite=True)

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
        secret_name = SECRET_MAP.get((self.db_cluster_name, self.db_name))
        if not secret_name:
            raise ValueError(f"DB 연결 정보 없음: cluster={self.db_cluster_name}, db={self.db_name}")

        client = boto3.session.Session().client('secretsmanager', region_name='ap-northeast-2')
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        logger.info(f"Secret 로드: {secret_name}, keys: {list(secret.keys())}")
        return secret
