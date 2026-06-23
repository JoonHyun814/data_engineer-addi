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

def resolve_date_range(event: dict, now: datetime) -> tuple[str, str]:
    """
    조회기간 결정. 평소(스텝펑션 자동 실행)에는 event 없이 호출돼 기본값(LOOKBACK_DAYS=1일)을 쓴다.
    수동 백필 등 특정 기간을 다시 조회해야 할 때는 event로 직접 지정할 수 있다:
      {"fromTmFc": "20260601", "toTmFc": "20260610"}  -- 기간 직접 지정 (API 제약상 오늘로부터 최대 6일 전까지)
      {"lookbackDays": 3}                              -- "오늘-N일 ~ 오늘"로 지정
    """
    from_tm_fc = event.get("fromTmFc")
    to_tm_fc = event.get("toTmFc")
    if from_tm_fc and to_tm_fc:
        return from_tm_fc, to_tm_fc
    lookback_days = int(event.get("lookbackDays", LOOKBACK_DAYS))
    return (now - timedelta(days=lookback_days)).strftime("%Y%m%d"), now.strftime("%Y%m%d")

def item_hash(item: dict) -> str:
    """이벤트 식별 필드만 정규화해 동일 이벤트 재적재를 막는 dedup 키 (cancel 변경 등 실제 상태 변화는 새 레코드로 적재)"""
    subset = {k: item.get(k) for k in HASH_FIELDS}
    canonical = json.dumps(subset, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def fetch_all_alerts(api_key: str, from_tm_fc: str, to_tm_fc: str) -> list[dict]:
    """
    stnId 파라미터로 필터링하지 않는다 — getPwnCd 응답의 stnId는 지역 관측소 코드가 아니라
    전국 어디든 항상 "108" 고정값으로 내려온다(실측 확인, 2026-06-23). 실제 지역 구분은
    areaCode(특보구역코드)로만 가능하며, regions.csv에는 이 코드가 없어 region 매핑이 아직 없다.
    그래서 지역 필터링/조인 없이 전국 단위 응답을 raw 그대로 적재한다.
    """
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

def register_partition(glue, dt: str, hr: str, location: str):
    """
    방금 적재한 dt/hr 파티션을 Glue Catalog에 즉시 등록 (MSCK REPAIR 불필요).
    S3 적재는 이미 끝난 뒤라 데이터 자체는 안전하지만, 등록 실패(권한 등)를 조용히 넘기면
    MSCK 백업이 없는 상태에서 해당 파티션이 계속 조회에서 빠진 채로 남을 수 있으므로
    예외를 다시 던져 람다 실행을 실패로 표시한다 (CloudWatch 알람/재시도로 드러나도록).
    """
    try:
        table = glue.get_table(DatabaseName="weather", Name="special_alert")["Table"]
        sd = dict(table["StorageDescriptor"])
        sd["Location"] = location
        glue.create_partition(
            DatabaseName="weather", TableName="special_alert",
            PartitionInput={"Values": [dt, hr], "StorageDescriptor": sd},
        )
    except glue.exceptions.AlreadyExistsException:
        pass
    except Exception as e:
        print(f"Partition registration failed (dt={dt}, hr={hr}): {e}")
        raise


def lambda_handler(event, context):
    api_secret = get_secret('weather_API')
    api_key    = api_secret['UV_API_KEY']

    now    = datetime.now(KST)
    dt_str = now.strftime("%Y%m%d")
    hr_str = f"{now.hour:02d}"
    from_tm_fc, to_tm_fc = resolve_date_range(event or {}, now)

    s3   = boto3.client('s3')
    glue = boto3.client('glue')
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
        register_partition(glue, dt_str, hr_str, f"s3://{S3_BUCKET}/{RAW_PREFIX}/dt={dt_str}/hr={hr_str}/")
    else:
        print("No new records")

    save_seen(s3, prune_seen(seen, now))

    return {
        "statusCode": 200,
        "body": json.dumps({"fetched": len(items), "new": len(new_records)}),
    }
