import io
import csv
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone

S3_BUCKET   = "ptbwa-da"
REGIONS_KEY = "prod/weather/regions/regions.csv"
KST = timezone(timedelta(hours=9))

PM10_THRESHOLDS = [
    (0,   30,  "B001_003_001"),
    (31,  80,  "B001_003_002"),
    (81,  150, "B001_003_003"),
    (151, 9999, "B001_003_004"),
]


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_regions(s3) -> list[dict]:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(content)))

def _safe_float(v):
    if v in (None, "", "-"): return None
    try: return float(v)
    except (TypeError, ValueError): return None

def _safe_int(v):
    if v in (None, "", "-"): return None
    try: return int(v)
    except (TypeError, ValueError): return None

GRADE_TO_CODE = {
    1: "B001_003_001",
    2: "B001_003_002",
    3: "B001_003_003",
    4: "B001_003_004",
}

def classify_pm10(pm10: float) -> str:
    for lo, hi, code in PM10_THRESHOLDS:
        if lo <= pm10 <= hi:
            return code
    return "B001_003_004"

def resolve_weather_code(pm10_grade, pm10_grade1h, pm10_value) -> str:
    if pm10_grade in GRADE_TO_CODE:
        return GRADE_TO_CODE[pm10_grade]
    if pm10_grade1h in GRADE_TO_CODE:
        return GRADE_TO_CODE[pm10_grade1h]
    return classify_pm10(pm10_value) if pm10_value is not None else "B001_003_001"

def fetch_dust(api_key: str, sido: str, rep_station: str) -> dict:
    res = requests.get(
        "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty",
        params={"serviceKey": api_key, "returnType": "json",
                "numOfRows": 100, "pageNo": 1, "sidoName": sido, "ver": "1.3"},
        timeout=10,
    )
    res.raise_for_status()
    items = res.json().get("response", {}).get("body", {}).get("items", [])
    if not items:
        raise RuntimeError("items 없음")

    # 대표 측정소 우선, 없으면 첫 번째 유효값
    target = next((i for i in items if i.get("stationName") == rep_station), None)
    if target is None:
        target = next((i for i in items
                       if _safe_float(i.get("pm10Value")) is not None), None)
    if target is None:
        raise RuntimeError("유효한 데이터 없음")

    pm10        = _safe_float(target.get("pm10Value"))
    pm10_grade  = _safe_int(target.get("pm10Grade"))
    pm10_grade1h = _safe_int(target.get("pm10Grade1h"))
    code        = resolve_weather_code(pm10_grade, pm10_grade1h, pm10)

    return {
        "weather_code":  code,
        "pm10Value":     pm10,
        "pm25Value":     _safe_float(target.get("pm25Value")),
        "pm10Grade":     _safe_int(target.get("pm10Grade")),
        "pm25Grade":     _safe_int(target.get("pm25Grade")),
        "pm10Grade1h":   _safe_int(target.get("pm10Grade1h")),
        "pm25Grade1h":   _safe_int(target.get("pm25Grade1h")),
        "khaiValue":     _safe_float(target.get("khaiValue")),
        "khaiGrade":     _safe_int(target.get("khaiGrade")),
        "so2Value":      _safe_float(target.get("so2Value")),
        "coValue":       _safe_float(target.get("coValue")),
        "o3Value":       _safe_float(target.get("o3Value")),
        "no2Value":      _safe_float(target.get("no2Value")),
        "dataTime":      target.get("dataTime"),
        "stationName":   target.get("stationName"),
    }

def save_to_s3(s3, key: str, records: list[dict]):
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body.encode('utf-8'),
                  ContentType='application/json')

def lambda_handler(event, context):
    api_secret = get_secret('weather_API')
    api_key    = api_secret['UV_API_KEY']

    now    = datetime.now(KST)
    dt_str = now.strftime("%Y%m%d")
    hr_str = f"{now.hour:02d}"

    s3      = boto3.client('s3')
    regions = load_regions(s3)

    records = []
    errors  = []

    for r in regions:
        region_id   = int(r['id'])
        area_name   = r['area_name']
        sido        = r['dust_area_name']
        rep_station = r['dust_station_name']

        try:
            result = fetch_dust(api_key, sido, rep_station)
            records.append({
                "region_id":   region_id,
                "area_name":   area_name,
                **result,
                "created_at":  now.isoformat(),
            })
        except Exception as e:
            print(f"Error [{area_name}]: {e}")
            errors.append({"region_id": region_id, "area_name": area_name, "error": str(e)})

    if records:
        key = f"prod/weather/fine_dust/dt={dt_str}/hr={hr_str}/data.json"
        save_to_s3(s3, key, records)
        print(f"S3 saved: {key} ({len(records)} records)")

    return {
        "statusCode": 200,
        "body": json.dumps({"fine_dust": len(records), "errors": errors})
    }
