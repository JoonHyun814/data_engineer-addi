import json
import hashlib
import boto3
import requests
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone

S3_BUCKET  = "ptbwa-da"
RAW_PREFIX = "prod/weather/special_alert"
STATE_KEY  = f"{RAW_PREFIX}/state/seen.json"
KST = timezone(timedelta(hours=9))

LOOKBACK_DAYS  = 1    # 3시간 주기 대비 충분한 오버랩 — 한 번 누락돼도 다음 실행에서 재확보
RETENTION_DAYS = 8    # API 최대 조회기간(6일)보다 여유있게 seen 상태 보존

# dedup 식별에 쓰는 필드만 — startTime/endTime/allEndTime 등 부가 필드 변동은 무시
HASH_FIELDS = ("stnId", "areaCode", "warnVar", "warnStress", "command", "cancel", "tmFc", "tmSeq")

_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd"


def get_secret(name):
    client = boto3.client('secretsmanager')
    return json.loads(client.get_secret_value(SecretId=name)['SecretString'])

def load_seen(s3) -> dict[str, str]:
    """raw item hash → 최초 수집일(YYYYMMDD). 중복 적재 방지용 상태."""
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=STATE_KEY)
        data = json.loads(obj['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {}
        raise
    if not isinstance(data, dict):
        # 구버전(getWthrWrnList) 상태 파일은 list 형식 — 호환되지 않으므로 폐기하고 새로 시작
        return {}
    return data

def save_seen(s3, seen: dict[str, str]):
    s3.put_object(
        Bucket=S3_BUCKET, Key=STATE_KEY,
        Body=json.dumps(seen, ensure_ascii=False).encode('utf-8'),
        ContentType='application/json',
    )

def prune_seen(seen: dict[str, str], now: datetime) -> dict[str, str]:
    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y%m%d")
    return {h: d for h, d in seen.items() if d >= cutoff}

def item_hash(item: dict) -> str:
    """이벤트 식별 필드만 정규화해 동일 이벤트 재적재를 막는 dedup 키 (cancel 변경 등 실제 상태 변화는 새 레코드로 적재)"""
    subset = {k: item.get(k) for k in HASH_FIELDS}
    canonical = json.dumps(subset, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def fetch_all_alerts(api_key: str, from_tm_fc: str, to_tm_fc: str) -> list[dict]:
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
                "fromTmFc": from_tm_fc,
                "toTmFc": to_tm_fc,
            },
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        rc = data.get("response", {}).get("header", {}).get("resultCode", "??")
        if rc not in ("00", "03"):   # 03 = 데이터 없음 (정상)
            raise RuntimeError(data.get("response", {}).get("header", {}).get("resultMsg", rc))
        body  = data.get("response", {}).get("body") or {}
        total = int(body.get("totalCount", 0) or 0)
        raw   = body.get("items") or {}
        if isinstance(raw, dict):
            raw = raw.get("item", [])
        if isinstance(raw, dict):
            raw = [raw]
        items.extend(raw or [])
        if not raw or len(items) >= total:
            break
        page += 1
    return items

def save_raw(s3, key: str, records: list[dict]):
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body.encode('utf-8'),
                  ContentType='application/json')


def lambda_handler(event, context):
    api_secret = get_secret('weather_API')
    api_key    = api_secret['UV_API_KEY']

    now    = datetime.now(KST)
    dt_str = now.strftime("%Y%m%d")
    hr_str = f"{now.hour:02d}"
    from_tm_fc = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    to_tm_fc   = now.strftime("%Y%m%d")

    s3   = boto3.client('s3')
    seen = load_seen(s3)

    items = fetch_all_alerts(api_key, from_tm_fc, to_tm_fc)
    print(f"fetched {len(items)} items ({from_tm_fc} ~ {to_tm_fc})")

    new_records = []
    for item in items:
        h = item_hash(item)
        if h in seen:
            continue
        record = dict(item)
        record["fetched_at"] = now.isoformat()
        new_records.append(record)
        seen[h] = dt_str

    if new_records:
        key = f"{RAW_PREFIX}/dt={dt_str}/hr={hr_str}/data.json"
        save_raw(s3, key, new_records)
        print(f"S3 saved: {key} ({len(new_records)} new, {len(items) - len(new_records)} duplicate skipped)")
    else:
        print("No new records")

    save_seen(s3, prune_seen(seen, now))

    return {
        "statusCode": 200,
        "body": json.dumps({"fetched": len(items), "new": len(new_records)}),
    }
