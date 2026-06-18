import io
import csv
import json
import time
import boto3
import pymysql
from typing import Callable
from datetime import datetime, timedelta, timezone

S3_BUCKET      = "ptbwa-da"
REGIONS_KEY    = "prod/weather/regions/regions.csv"
ATHENA_OUTPUT  = "s3://ptbwa-da/athena-results/weather_codes_update/"
KST = timezone(timedelta(hours=9))

# 1일 lookback으로 최신 파티션 기준 가져오기
# special_alert: 상태는 area_weather_codes에 누적 저장되므로, 매 실행 시
# 직전 ~1일 내 신규 발표/해제 이벤트만 가져와 기존 상태에 diff로 적용한다
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
    # 특보: (region_id, keyword) 기준 최신 이벤트 1건 (발표/해제 모두 반환, 적용은 Python에서 diff로 처리)
    "special_alert": """
        SELECT region_id, weather_code, status
        FROM (
            SELECT region_id, weather_code, status,
                   ROW_NUMBER() OVER (PARTITION BY region_id, keyword ORDER BY tmFc DESC) AS rn
            FROM weather.special_alert
            WHERE dt >= date_format(date_add('day', -1, current_date), '%Y%m%d')
        ) t
        WHERE rn = 1
    """,
}

MSCK_TABLES = ["weather.forecast", "weather.uv", "weather.fine_dust", "weather.special_alert"]

RegionCodeResolver = Callable[[int], "str | None"]


# ---- AWS / DB 연결 ----------------------------------------------------

def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def connect_db(secret: dict, default_dbname: str, **kwargs):
    return pymysql.connect(
        host=secret['host'], user=secret['username'], password=secret['password'],
        db=secret.get('dbname', default_dbname),
        port=int(secret.get('port', 3306)),
        **kwargs,
    )


# ---- region_id → region_code 매핑 --------------------------------------

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

def build_region_code_resolver(s3, conn1) -> RegionCodeResolver:
    region_id_to_adm = load_regions_csv(s3)
    adm_to_region_code = load_region_code_map(conn1)

    def region_code(region_id: int) -> "str | None":
        adm = region_id_to_adm.get(region_id)
        return adm_to_region_code.get(str(adm)) if adm else None

    return region_code


# ---- Athena ------------------------------------------------------------

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


# ---- 카테고리별 weather_code 수집 ----------------------------------------

WeatherCodeRow = tuple[str, str]  # (region_code, weather_code)

def collect_codes(athena, query_key: str, region_code: RegionCodeResolver) -> list[WeatherCodeRow]:
    """단일 weather_code 컬럼을 갖는 쿼리(fine_dust, uv)를 (region_code, weather_code) 리스트로 변환"""
    rows = []
    for region_id, wcode in run_athena_query(athena, ATHENA_QUERIES[query_key]):
        rc = region_code(int(region_id))
        if rc and wcode:
            rows.append((rc, wcode))
    return rows

def collect_forecast_codes(athena, region_code: RegionCodeResolver) -> list[WeatherCodeRow]:
    """B001_001 일반날씨 & B001_002 불쾌지수 — forecast 1회 쿼리로 함께 처리"""
    rows = []
    for region_id, wcode, dcode in run_athena_query(athena, ATHENA_QUERIES["forecast"]):
        rc = region_code(int(region_id))
        if rc is None:
            continue
        if wcode:
            rows.append((rc, wcode))
        if dcode:
            rows.append((rc, dcode))
    return rows

def load_active_alerts(conn_addi) -> set[WeatherCodeRow]:
    """B001_005 특보의 현재 상태 = area_weather_codes에 이미 저장된 값"""
    with conn_addi.cursor() as cur:
        cur.execute(
            "SELECT region_code, weather_code FROM area_weather_codes WHERE LEFT(weather_code, 9) = 'B001_005_'"
        )
        return {(row[0], row[1]) for row in cur.fetchall()}

def apply_special_alert_diff(athena, region_code: RegionCodeResolver, active_alerts: set[WeatherCodeRow]) -> None:
    """신규 발표/해제 이벤트를 기존 상태(active_alerts)에 in-place로 적용"""
    for region_id, wcode, status in run_athena_query(athena, ATHENA_QUERIES["special_alert"]):
        rc = region_code(int(region_id))
        if not rc or not wcode:
            continue
        key = (rc, wcode)
        if status == '발표':
            active_alerts.add(key)
        elif status == '해제':
            active_alerts.discard(key)


# ---- RDS 적재 ------------------------------------------------------------

def save_weather_data(conn_addi, weather_data: list[WeatherCodeRow]) -> None:
    with conn_addi.cursor() as cur:
        cur.execute("TRUNCATE TABLE area_weather_codes")
        cur.executemany(
            "INSERT INTO area_weather_codes (region_code, weather_code, moddt) VALUES (%s, %s, NOW())",
            weather_data,
        )


# ---- 엔트리포인트 ---------------------------------------------------------

def lambda_handler(event, context):
    db1_secret  = get_secret('database-1')
    addi_secret = get_secret('database_addi')

    s3     = boto3.client('s3')
    athena = boto3.client('athena')

    print("Running MSCK REPAIR TABLE...")
    for table in MSCK_TABLES:
        run_msck(athena, table)

    conn1 = connect_db(db1_secret, 'ptbwa_propfit', cursorclass=pymysql.cursors.DictCursor)
    try:
        region_code = build_region_code_resolver(s3, conn1)
    finally:
        conn1.close()

    conn_addi = connect_db(addi_secret, 'addi')
    try:
        active_alerts = load_active_alerts(conn_addi)

        print("Querying forecast...")
        weather_data = collect_forecast_codes(athena, region_code)

        print("Querying fine_dust...")
        weather_data += collect_codes(athena, "fine_dust", region_code)

        print("Querying uv...")
        weather_data += collect_codes(athena, "uv", region_code)

        print("Querying special_alert...")
        apply_special_alert_diff(athena, region_code, active_alerts)
        weather_data += list(active_alerts)

        print(f"Total weather_data rows to insert: {len(weather_data)}")
        save_weather_data(conn_addi, weather_data)
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
