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
# special_alert: raw 테이블이 dedup된 append-only 이벤트 로그이므로, 매 실행 시
# 전체 이력에서 (stnId, areaCode, warnVar)별 최신 유효 이벤트를 계산해 B001_005 상태를
# 완전히 재계산한다 (다른 카테고리와 동일하게 매 실행 전체 재계산 — DB와의 diff 불필요)
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
    # 특보: (stnId, areaCode, warnVar) 기준 최신 유효 이벤트 1건 — dt 필터 없이 전체 이력에서 계산.
    # raw 테이블에는 동일 이벤트(stnId/areaCode/warnVar/tmFc/tmSeq)가 재조회로 여러 번
    # 적재될 수 있으므로(예: cancel 0→1 정정) fetched_at 기준으로 최신 버전을 먼저 고른 뒤,
    # 취소(cancel=1)된 버전은 버리고, 남은 버전 중 가장 최근 발표(tmFc/tmSeq)를 채택한다.
    # 전체 이력을 스캔해야 1일 lookback 밖에서 시작된 장기 특보(건조/한파 등)도 놓치지 않는다.
    "special_alert": """
        SELECT stnId, areaCode, warnVar, command
        FROM (
            SELECT stnId, areaCode, warnVar, command, tmFc, tmSeq,
                   ROW_NUMBER() OVER (
                       PARTITION BY stnId, areaCode, warnVar
                       ORDER BY tmFc DESC, tmSeq DESC
                   ) AS event_rn
            FROM (
                SELECT stnId, areaCode, warnVar, command, cancel, tmFc, tmSeq,
                       ROW_NUMBER() OVER (
                           PARTITION BY stnId, areaCode, warnVar, tmFc, tmSeq
                           ORDER BY fetched_at DESC
                       ) AS version_rn
                FROM weather.special_alert
            ) versioned
            WHERE version_rn = 1 AND cancel <> '1'
        ) latest_valid
        WHERE event_rn = 1
    """,
}

MSCK_TABLES = ["weather.forecast", "weather.uv", "weather.fine_dust", "weather.special_alert"]

RegionCodeResolver = Callable[[int], "str | None"]

# getPwnCd warnVar(특보종류) → 한글 라벨
WARN_VAR_LABELS = {
    "1": "강풍", "2": "호우", "3": "한파", "4": "건조",
    "5": "폭풍해일", "6": "풍랑", "7": "태풍", "8": "대설",
    "9": "황사", "12": "폭염", "13": "열대야",
}

# 라벨 → B001_005_xxx (풍랑/폭풍해일/열대야 등은 아직 코드 미부여 — 매핑 없으면 스킵)
WEATHER_CODE_MAP = {
    "강풍": "B001_005_001",
    "한파": "B001_005_002",
    "폭염": "B001_005_003",
    "황사": "B001_005_004",
    "태풍": "B001_005_005",
    "대설": "B001_005_006",
    "호우": "B001_005_007",
    "건조": "B001_005_008",
}

# getPwnCd command(발표코드): 1-발표, 2-해제, 3-연장, 6-정정, 7-변경발표, 8-변경해제
LIFT_COMMANDS = {"2", "8"}


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

def load_stn_to_region_ids(s3) -> dict[str, list[int]]:
    """stn_id → region_id 목록 (특보는 stnId 단위로 발표되고, 한 관측소에 여러 region이 매핑될 수 있음)"""
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    mapping: dict[str, list[int]] = {}
    for r in csv.DictReader(io.StringIO(content)):
        mapping.setdefault(r['stn_id'], []).append(int(r['id']))
    return mapping

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

def collect_special_alert_codes(
    athena,
    region_code: RegionCodeResolver,
    stn_to_region_ids: dict[str, list[int]],
) -> list[WeatherCodeRow]:
    """
    B001_005 특보 — 전체 이력에서 (stnId, areaCode, warnVar)별 최신 유효 상태를 계산해
    현재 발효 중인 (region_code, weather_code) 집합을 완전히 새로 만든다.
    동일 stnId 아래 여러 areaCode가 있으면 하나라도 발표 중이면 활성으로 간주한다
    (행 처리 순서에 결과가 좌우되지 않도록 active/lifted를 모았다가 한 번에 병합).
    """
    active: set[WeatherCodeRow] = set()
    lifted: set[WeatherCodeRow] = set()

    for stn_id, _area_code, warn_var, command in run_athena_query(athena, ATHENA_QUERIES["special_alert"]):
        label = WARN_VAR_LABELS.get(str(warn_var))
        wcode = WEATHER_CODE_MAP.get(label) if label else None
        if not wcode:
            continue   # 풍랑/폭풍해일/열대야 등 B001_005 코드가 아직 없는 특보종류는 스킵

        is_lifted = str(command) in LIFT_COMMANDS
        for region_id in stn_to_region_ids.get(stn_id, []):
            rc = region_code(region_id)
            if not rc:
                continue
            key = (rc, wcode)
            (lifted if is_lifted else active).add(key)

    active -= (lifted - active)
    return list(active)


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

    stn_to_region_ids = load_stn_to_region_ids(s3)

    conn_addi = connect_db(addi_secret, 'addi')
    try:
        print("Querying forecast...")
        weather_data = collect_forecast_codes(athena, region_code)

        print("Querying fine_dust...")
        weather_data += collect_codes(athena, "fine_dust", region_code)

        print("Querying uv...")
        weather_data += collect_codes(athena, "uv", region_code)

        print("Querying special_alert...")
        weather_data += collect_special_alert_codes(athena, region_code, stn_to_region_ids)

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
