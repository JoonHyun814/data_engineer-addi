import io
import csv
import json
import time
import boto3
import pymysql
from datetime import datetime, timedelta, timezone

S3_BUCKET      = "ptbwa-da"
REGIONS_KEY    = "prod/weather/regions/regions.csv"
ATHENA_OUTPUT  = "s3://ptbwa-da/athena-results/weather_codes_update/"
KST = timezone(timedelta(hours=9))

# 1일 lookback으로 최신 파티션 기준 가져오기, special_alert는 7일
ATHENA_QUERIES = {
    "forecast": """
        SELECT region_id, weather_code, discomfort_code
        FROM (
            SELECT region_id, weather_code, discomfort_code,
                   ROW_NUMBER() OVER (PARTITION BY region_id ORDER BY dt DESC, hr DESC) AS rn
            FROM weather.forecast
            WHERE dt >= date_format(date_add('day', -1, current_date), '%Y%m%d')
        ) t
        WHERE rn = 1
    """,
    "fine_dust": """
        SELECT region_id, weather_code
        FROM (
            SELECT region_id, weather_code,
                   ROW_NUMBER() OVER (PARTITION BY region_id ORDER BY dt DESC, hr DESC) AS rn
            FROM weather.fine_dust
            WHERE dt >= date_format(date_add('day', -1, current_date), '%Y%m%d')
        ) t
        WHERE rn = 1
    """,
    "uv": """
        SELECT region_id, weather_code
        FROM (
            SELECT region_id, weather_code,
                   ROW_NUMBER() OVER (PARTITION BY region_id ORDER BY dt DESC, hr DESC) AS rn
            FROM weather.uv
            WHERE dt >= date_format(date_add('day', -1, current_date), '%Y%m%d')
        ) t
        WHERE rn = 1
    """,
    # 특보: (region_id, keyword) 기준 최신 이벤트가 '발표'인 것만
    "special_alert": """
        SELECT region_id, weather_code
        FROM (
            SELECT region_id, weather_code, status,
                   ROW_NUMBER() OVER (PARTITION BY region_id, keyword ORDER BY tmFc DESC) AS rn
            FROM weather.special_alert
            WHERE dt >= date_format(date_add('day', -7, current_date), '%Y%m%d')
        ) t
        WHERE rn = 1 AND status = '발표'
    """,
}


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_regions_csv(s3) -> dict[int, str]:
    """region_id → adm_code"""
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    return {int(r['id']): r['adm_code'] for r in csv.DictReader(io.StringIO(content))}

def load_region_code_map(conn) -> dict[str, str]:
    """adm_code → region_code (RDS)"""
    with conn.cursor() as cur:
        cur.execute("SELECT region_code, adm_code FROM regions WHERE adm_code IS NOT NULL")
        return {str(row['adm_code']): row['region_code'] for row in cur.fetchall()}

MSCK_TABLES = ["weather.forecast", "weather.uv", "weather.fine_dust", "weather.special_alert"]

def run_msck(athena, table: str):
    resp = athena.start_query_execution(
        QueryString=f"MSCK REPAIR TABLE {table}",
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )
    exec_id = resp["QueryExecutionId"]
    for _ in range(30):
        state = athena.get_query_execution(QueryExecutionId=exec_id)["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            print(f"MSCK {table}: OK")
            return
        if state in ("FAILED", "CANCELLED"):
            print(f"MSCK {table}: {state} (무시하고 계속)")
            return
        time.sleep(2)
    print(f"MSCK {table}: timeout (무시하고 계속)")

def run_athena_query(athena, sql: str) -> list[list[str]]:
    resp = athena.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )
    exec_id = resp["QueryExecutionId"]

    for _ in range(60):
        status = athena.get_query_execution(QueryExecutionId=exec_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena {state}: {reason}")
        time.sleep(3)
    else:
        raise TimeoutError(f"Athena query timed out: {exec_id}")

    rows = []
    paginator = athena.get_paginator("get_query_results")
    first_page = True
    for page in paginator.paginate(QueryExecutionId=exec_id):
        page_rows = page["ResultSet"]["Rows"]
        if first_page:
            page_rows = page_rows[1:]  # 헤더 제외
            first_page = False
        for row in page_rows:
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows


def lambda_handler(event, context):
    db1_secret   = get_secret('database-1')
    addi_secret  = get_secret('database_addi')

    s3     = boto3.client('s3')
    athena = boto3.client('athena')

    print("Running MSCK REPAIR TABLE...")
    for table in MSCK_TABLES:
        run_msck(athena, table)

    region_id_to_adm = load_regions_csv(s3)

    conn1 = pymysql.connect(
        host=db1_secret['host'], user=db1_secret['username'],
        password=db1_secret['password'],
        db=db1_secret.get('dbname', 'ptbwa_propfit'),
        port=int(db1_secret.get('port', 3306)),
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        adm_to_region_code = load_region_code_map(conn1)
    finally:
        conn1.close()

    def region_code(region_id: int) -> str | None:
        adm = region_id_to_adm.get(region_id)
        return adm_to_region_code.get(str(adm)) if adm else None

    weather_data: list[tuple[str, str]] = []

    # B001_001 일반날씨 & B001_002 불쾌지수 — forecast 1회 쿼리로 함께 처리
    print("Querying forecast...")
    for row in run_athena_query(athena, ATHENA_QUERIES["forecast"]):
        region_id, wcode, dcode = int(row[0]), row[1], row[2]
        rc = region_code(region_id)
        if rc is None:
            continue
        if wcode:
            weather_data.append((rc, wcode))
        if dcode:
            weather_data.append((rc, dcode))

    # B001_003 미세먼지
    print("Querying fine_dust...")
    for row in run_athena_query(athena, ATHENA_QUERIES["fine_dust"]):
        rc = region_code(int(row[0]))
        if rc and row[1]:
            weather_data.append((rc, row[1]))

    # B001_004 자외선
    print("Querying uv...")
    for row in run_athena_query(athena, ATHENA_QUERIES["uv"]):
        rc = region_code(int(row[0]))
        if rc and row[1]:
            weather_data.append((rc, row[1]))

    # B001_005 특보 — 현재 발효 중인 건만 (발표 상태)
    print("Querying special_alert...")
    for row in run_athena_query(athena, ATHENA_QUERIES["special_alert"]):
        rc = region_code(int(row[0]))
        if rc and row[1]:
            weather_data.append((rc, row[1]))

    print(f"Total weather_data rows to insert: {len(weather_data)}")

    conn_addi = pymysql.connect(
        host=addi_secret['host'], user=addi_secret['username'],
        password=addi_secret['password'],
        db=addi_secret.get('dbname', 'addi'),
        port=int(addi_secret.get('port', 3306)),
    )
    try:
        with conn_addi.cursor() as cur:
            cur.execute("TRUNCATE TABLE area_weather_codes")
            cur.executemany(
                "INSERT INTO area_weather_codes (region_code, weather_code, moddt) VALUES (%s, %s, NOW())",
                weather_data,
            )
        conn_addi.commit()
    except Exception as e:
        conn_addi.rollback()
        raise e
    finally:
        conn_addi.close()

    return {
        "statusCode": 200,
        "body": json.dumps({"updated_rows": len(weather_data)}),
    }
