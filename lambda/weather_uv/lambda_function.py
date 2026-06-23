import io
import csv
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone

S3_BUCKET   = "ptbwa-da"
REGIONS_KEY = "prod/weather/regions/regions.csv"
KST = timezone(timedelta(hours=9))


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_regions(s3) -> list[dict]:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(content)))

def classify_uv(h0_int: int) -> str:
    if h0_int >= 11:  return "B001_004_005"
    if h0_int >= 8:   return "B001_004_004"
    if h0_int >= 6:   return "B001_004_003"
    if h0_int >= 3:   return "B001_004_002"
    return "B001_004_001"

def fetch_uv(endpoint: str, api_key: str, adm_code: str, time_str: str) -> tuple[str, int] | None:
    res = requests.get(
        f"{endpoint}/getUVIdxV5",
        params={"serviceKey": api_key, "areaNo": adm_code,
                "time": time_str, "dataType": "JSON"},
        timeout=5,
    )
    if res.status_code != 200:
        return None
    items = res.json().get('response', {}).get('body', {}) \
                      .get('items', {}).get('item', [])
    if not items:
        return None
    h0_value = items[0].get('h0')
    if h0_value is None or h0_value == "":
        return None
    h0_int = int(h0_value)
    return classify_uv(h0_int), h0_int

def save_to_s3(s3, key: str, records: list[dict]):
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body.encode('utf-8'),
                  ContentType='application/json')

def register_partition(glue, dt: str, hr: str, location: str):
    """
    방금 적재한 dt/hr 파티션을 Glue Catalog에 즉시 등록 (MSCK REPAIR 불필요).
    S3 적재는 이미 끝난 뒤라 데이터 자체는 안전하지만, 등록 실패(권한 등)를 조용히 넘기면
    MSCK 백업이 없는 상태에서 해당 파티션이 계속 조회에서 빠진 채로 남을 수 있으므로
    예외를 다시 던져 람다 실행을 실패로 표시한다 (CloudWatch 알람/재시도로 드러나도록).
    """
    try:
        table = glue.get_table(DatabaseName="weather", Name="uv")["Table"]
        sd = dict(table["StorageDescriptor"])
        sd["Location"] = location
        glue.create_partition(
            DatabaseName="weather", TableName="uv",
            PartitionInput={"Values": [dt, hr], "StorageDescriptor": sd},
        )
    except glue.exceptions.AlreadyExistsException:
        pass
    except Exception as e:
        print(f"Partition registration failed (dt={dt}, hr={hr}): {e}")
        raise

def lambda_handler(event, context):
    api_secret = get_secret('weather_API')
    endpoint   = api_secret['UV_API_ENDPOINT']
    api_key    = api_secret['UV_API_KEY']

    now    = datetime.now(KST)
    hour   = (now.hour // 3) * 3
    time_str = now.strftime(f"%Y%m%d{hour:02d}")
    dt_str = now.strftime("%Y%m%d")
    hr_str = f"{hour:02d}"

    s3      = boto3.client('s3')
    glue    = boto3.client('glue')
    regions = load_regions(s3)

    records = []
    errors  = []

    for r in regions:
        region_id = int(r['id'])
        area_name = r['area_name']
        adm_code  = r['adm_code']

        try:
            result = fetch_uv(endpoint, api_key, adm_code, time_str)
            if result is None:
                raise RuntimeError("유효한 UV 값 없음")
            w_code, h0_int = result
            records.append({
                "region_id":    region_id,
                "area_name":    area_name,
                "weather_code": w_code,
                "h0_value":     h0_int,
                "created_at":   now.isoformat(),
            })
        except Exception as e:
            print(f"Error [{area_name}]: {e}")
            errors.append({"region_id": region_id, "area_name": area_name, "error": str(e)})

    if records:
        key = f"prod/weather/uv/dt={dt_str}/hr={hr_str}/data.json"
        save_to_s3(s3, key, records)
        print(f"S3 saved: {key} ({len(records)} records)")
        register_partition(glue, dt_str, hr_str, f"s3://{S3_BUCKET}/prod/weather/uv/dt={dt_str}/hr={hr_str}/")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "uv":    len(records),
            "errors": errors,
        })
    }
