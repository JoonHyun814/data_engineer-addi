import io
import csv
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone

S3_BUCKET    = "ptbwa-da"
REGIONS_KEY  = "prod/weather/regions/regions.csv"
FCST_BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
KST = timezone(timedelta(hours=9))


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_regions(s3) -> list[dict]:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(content)))

def get_base_datetime() -> tuple[str, str]:
    now = datetime.now(KST) - timedelta(minutes=10)
    for t in reversed(FCST_BASE_TIMES):
        if now.hour >= int(t[:2]):
            return now.strftime("%Y%m%d"), t
    yesterday = now - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), "2300"

def fetch_fcst(api_key: str, nx: int, ny: int) -> list[dict]:
    base_date, base_time = get_base_datetime()
    res = requests.get(
        "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
        params={"serviceKey": api_key, "pageNo": 1, "numOfRows": 1000,
                "dataType": "JSON", "base_date": base_date, "base_time": base_time,
                "nx": nx, "ny": ny},
        timeout=10,
    )
    res.raise_for_status()
    data = res.json()
    rc = data["response"]["header"]["resultCode"]
    if rc != "00":
        raise RuntimeError(data["response"]["header"]["resultMsg"])
    return data["response"]["body"]["items"]["item"]

def _safe_float(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def _safe_int(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def classify(items: list[dict]) -> dict:
    slots = sorted(set((i["fcstDate"], i["fcstTime"]) for i in items))
    fd, ft = slots[0]

    # 첫 번째 슬롯 값
    s = {i["category"]: i["fcstValue"]
         for i in items if i["fcstDate"] == fd and i["fcstTime"] == ft}

    # TMN(일최저기온, 0600슬롯), TMX(일최고기온, 1500슬롯) — 같은 날짜에서 탐색
    tmn = next((i["fcstValue"] for i in items
                if i["fcstDate"] == fd and i["category"] == "TMN"), None)
    tmx = next((i["fcstValue"] for i in items
                if i["fcstDate"] == fd and i["category"] == "TMX"), None)

    sky = _safe_int(s.get("SKY")) or 1
    pty = _safe_int(s.get("PTY")) or 0
    wsd = _safe_float(s.get("WSD")) or 0.0
    tmp = _safe_float(s.get("TMP")) or 20.0
    reh = _safe_float(s.get("REH")) or 50.0

    # B001_001 일반날씨
    if pty == 3:           g_code = "B001_001_004"
    elif pty in (1, 2, 4): g_code = "B001_001_003"
    elif wsd >= 14:        g_code = "B001_001_005"
    elif sky in (3, 4):    g_code = "B001_001_002"
    else:                  g_code = "B001_001_001"

    # B001_002 불쾌지수 (Thom, 1959)
    tf = 9 * tmp / 5
    di = tf - 0.55 * (1 - reh / 100) * (tf - 26) + 32
    if di >= 80:    d_code = "B001_002_004"
    elif di >= 75:  d_code = "B001_002_003"
    elif di >= 70:  d_code = "B001_002_002"
    else:           d_code = "B001_002_001"

    return {
        "g_code": g_code,
        "d_code": d_code,
        "pop":  _safe_int(s.get("POP")),
        "pty":  pty,
        "pcp":  s.get("PCP", "강수없음"),
        "reh":  reh,
        "sno":  s.get("SNO", "적설없음"),
        "sky":  sky,
        "tmp":  tmp,
        "tmn":  _safe_float(tmn),
        "tmx":  _safe_float(tmx),
        "uuu":  _safe_float(s.get("UUU")),
        "vvv":  _safe_float(s.get("VVV")),
        "wav":  _safe_float(s.get("WAV")),
        "vec":  _safe_int(s.get("VEC")),
        "wsd":  wsd,
        "di":   round(di, 1),
        "fcst_date": fd,
        "fcst_time": ft,
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
        region_id = int(r['id'])
        area_name = r['area_name']
        nx        = int(r['grid_x'])
        ny        = int(r['grid_y'])

        try:
            items  = fetch_fcst(api_key, nx, ny)
            result = classify(items)

            records.append({
                "region_id":       region_id,
                "area_name":       area_name,
                "weather_code":    result["g_code"],
                "discomfort_code": result["d_code"],
                "pop":             result["pop"],
                "pty":             result["pty"],
                "pcp":             result["pcp"],
                "reh":             result["reh"],
                "sno":             result["sno"],
                "sky":             result["sky"],
                "tmp":             result["tmp"],
                "tmn":             result["tmn"],
                "tmx":             result["tmx"],
                "uuu":             result["uuu"],
                "vvv":             result["vvv"],
                "wav":             result["wav"],
                "vec":             result["vec"],
                "wsd":             result["wsd"],
                "di":              result["di"],
                "fcst_date":       result["fcst_date"],
                "fcst_time":       result["fcst_time"],
                "created_at":      now.isoformat(),
            })
        except Exception as e:
            print(f"Error [{area_name}]: {e}")
            errors.append({"region_id": region_id, "area_name": area_name, "error": str(e)})

    if records:
        key = f"prod/weather/forecast/dt={dt_str}/hr={hr_str}/data.json"
        save_to_s3(s3, key, records)
        print(f"S3 saved: {key} ({len(records)} records)")

    return {
        "statusCode": 200,
        "body": json.dumps({"forecast": len(records), "errors": errors})
    }
