import io
import csv
import json
import boto3
import requests
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone

S3_BUCKET   = "ptbwa-da"
REGIONS_KEY = "prod/weather/regions/regions.csv"
STATE_KEY   = "prod/weather/special_alert/state/seen.json"
KST = timezone(timedelta(hours=9))

WARNING_CODE_MAP = {
    "강풍": "B001_005_001",
    "한파": "B001_005_002",
    "폭염": "B001_005_003",
    "황사": "B001_005_004",
    "태풍": "B001_005_005",
    "대설": "B001_005_006",
    "호우": "B001_005_007",
    "건조": "B001_005_008",
}

_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList"


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_regions(s3) -> list[dict]:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=REGIONS_KEY)
    content = obj['Body'].read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(content)))

def load_seen(s3) -> set[str]:
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=STATE_KEY)
        return set(json.loads(obj['Body'].read().decode('utf-8')))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return set()
        raise

def save_seen(s3, seen: set[str]):
    s3.put_object(
        Bucket=S3_BUCKET, Key=STATE_KEY,
        Body=json.dumps(list(seen)).encode('utf-8'),
        ContentType='application/json',
    )

def fetch_alerts_by_stn(api_key: str, stn_id: str) -> list[dict]:
    items = []
    page = 1
    while True:
        res = requests.get(
            _URL,
            params={
                "serviceKey": api_key,
                "pageNo": page,
                "numOfRows": 100,
                "dataType": "JSON",
                "stnId": stn_id,
            },
            timeout=10,
        )
        res.raise_for_status()
        body = res.json().get("response", {}).get("body", {})
        total = int(body.get("totalCount", 0))
        raw = body.get("items") or {}
        if isinstance(raw, dict):
            raw = raw.get("item", [])
        if isinstance(raw, dict):
            raw = [raw]
        items.extend(raw or [])
        if len(items) >= total or not raw:
            break
        page += 1
    return items

def extract_keywords(title: str) -> list[tuple[str, str]]:
    """title에서 매칭되는 모든 (code, keyword) 반환 — 복합 특보 대응"""
    return [(code, kw) for kw, code in WARNING_CODE_MAP.items() if kw in title]

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
    seen    = load_seen(s3)

    stn_to_regions: dict[str, list[dict]] = {}
    for r in regions:
        stn_to_regions.setdefault(r['stn_id'], []).append(r)

    records  = []
    new_seen = set(seen)

    for stn_id, stn_regions in stn_to_regions.items():
        items = fetch_alerts_by_stn(api_key, stn_id)
        print(f"stnId={stn_id}: {len(items)} items")

        for item in items:
            title  = item.get("title", "")
            tm_fc  = str(item.get("tmFc", ""))
            tm_seq = str(item.get("tmSeq", ""))
            status = "해제" if "해제" in title else "발표"

            dedup_key = f"{stn_id}_{tm_seq}"
            if dedup_key in seen:
                continue

            matched_keywords = extract_keywords(title)
            if not matched_keywords:
                print(f"No keyword match: stnId={stn_id}, title={title}")
                new_seen.add(dedup_key)
                continue

            for code, keyword in matched_keywords:
                for r in stn_regions:
                    records.append({
                        "region_id":    int(r['id']),
                        "area_name":    r['area_name'],
                        "stn_id":       stn_id,
                        "weather_code": code,
                        "keyword":      keyword,
                        "status":       status,
                        "title":        title,
                        "tmFc":         tm_fc,
                        "tmSeq":        tm_seq,
                        "created_at":   now.isoformat(),
                    })
            new_seen.add(dedup_key)

    if records:
        key = f"prod/weather/special_alert/dt={dt_str}/hr={hr_str}/data.json"
        save_to_s3(s3, key, records)
        print(f"S3 saved: {key} ({len(records)} records)")

    save_seen(s3, new_seen)

    return {
        "statusCode": 200,
        "body": json.dumps({"special_alert": len(records)}),
    }
