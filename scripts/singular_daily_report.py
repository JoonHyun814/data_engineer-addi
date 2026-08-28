#!/usr/bin/env python
# coding: utf-8
"""
Singular Reporting API로 일별 install/reengagement 데이터 추출 (스펙 확인용).

이 API 키는 파트너/에이전시용 키였다 (실행 시 "missing parameter: organization_key" 에러로 확인).
그래서 일반 단일 계정 키와 인증 방식이 다르다:
    - api_key는 헤더가 아니라 query param으로 보낸다.
    - create_async_report는 organization_key가 필수다 (어느 광고주 조직 데이터를 볼지 지정).
    - organization_key는 get_customer_accounts로 먼저 조회해야 한다.
(출처: Singular Help Center "Reporting API for Partners")

흐름:
    1) GET  get_customer_accounts?api_key=...            -> organizations 목록 (display_name, organization_key)
    2) POST create_async_report?api_key=... (body에 organization_key 포함) -> report_id
    3) GET  get_report_status?api_key=...&report_id=...   -> 폴링 (organization_key 불필요)
    4) DONE되면 응답의 download_url에서 CSV 그냥 GET (인증 불필요, presigned URL로 추정)

실행 전: API 키를 환경변수로 넘길 것 (코드에 절대 하드코딩하지 말 것)
    - 레포 루트 .env에 SINGULAR_API_KEY=... 를 써두면 자동으로 읽는다 (.env는 .gitignore 대상).
    - 또는 직접: Windows PowerShell $env:SINGULAR_API_KEY = "...", Git Bash export SINGULAR_API_KEY="..."
    조직이 여러 개면: SINGULAR_ORGANIZATION_KEY도 같은 방식으로 지정 (안 하면 1개일 때만 자동 선택)

cmp 매핑 확인 결과: adn_campaign_id/adn_campaign_name은 이 tracker에서 "N/A"로 비어있고,
tracker_campaign_name이 "CTV_Propfit_<cmp>_<cmp>" 형태로 cmp 값을 그대로 담고 있다.
같은 날짜 tracker_installs/tracker_reengagements 값도 home_sing_v2.csv와 정확히 일치했다
(예: cmp=10174, 08-19 install=6/reengagement=11 등) - 백필 수치의 출처가 이 API(또는 대시보드)였던 것으로 보인다.
"""

import csv
import io
import os
import time

import requests

BASE_URL = "https://api.singular.net/api/v2.0"


def _load_dotenv():
    """
    레포 루트의 .env(KEY=VALUE)를 읽어 os.environ에 채워준다.
    이미 셸에서 export/$env:로 설정된 값은 덮어쓰지 않는다.
    별도 패키지(python-dotenv) 없이 이 스크립트에서만 쓰는 최소 구현.
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _api_key():
    api_key = os.environ.get("SINGULAR_API_KEY")
    if not api_key:
        raise SystemExit("환경변수 SINGULAR_API_KEY 가 설정되어 있지 않습니다.")
    return api_key


def get_customer_accounts():
    resp = requests.get(f"{BASE_URL}/get_customer_accounts", params={"api_key": _api_key()})
    if not resp.ok:
        print(f"[ERROR] {resp.status_code} {resp.text}")
    resp.raise_for_status()
    body = resp.json()
    print(f"[DEBUG] get_customer_accounts raw response: {body}")
    # 응답 envelope 구조가 확실치 않아 value로 한 번 더 감싼 경우까지 방어적으로 처리한다.
    if "organizations" in body:
        return body["organizations"]
    return body["value"]["organizations"]


def resolve_organization_key():
    org_key = os.environ.get("SINGULAR_ORGANIZATION_KEY")
    if org_key:
        return org_key

    organizations = get_customer_accounts()
    print("조회된 organization 목록:")
    for org in organizations:
        print(f"  - {org['display_name']}: {org['organization_key']}")

    if len(organizations) == 1:
        return organizations[0]["organization_key"]

    raise SystemExit(
        "organization이 여러 개입니다. 위 목록에서 organization_key를 골라 "
        "환경변수 SINGULAR_ORGANIZATION_KEY로 지정한 뒤 다시 실행하세요."
    )


def get_cohort_metrics(organization_key):
    """
    이 계정에 정의된 커스텀 이벤트(Purchase, Add To Cart, Membership 등) 목록과 cohort_periods를 조회한다.
    주의: 이 엔드포인트는 client 소스상 base가 v2.0이 아니라 https://api.singular.net/api/ 라서
    BASE_URL(.../v2.0)을 안 쓰고 따로 URL을 만든다.
    반환된 metrics[].name(opaque id)을 create_async_report의 cohort_metrics로,
    periods 중 "actual"을 cohort_periods로 넘기면 코호트가 아니라 그 날짜 실측값이 나온다.
    """
    resp = requests.get(
        "https://api.singular.net/api/cohort_metrics",
        params={"api_key": _api_key(), "organization_key": organization_key},
    )
    if not resp.ok:
        print(f"[ERROR] {resp.status_code} {resp.text}")
    resp.raise_for_status()
    return resp.json()


def create_async_report(organization_key, start_date, end_date, dimensions, metrics,
                         cohort_metrics=None, cohort_periods=None, time_breakdown="day", fmt="csv"):
    payload = {
        "organization_key": organization_key,
        "start_date": start_date,
        "end_date": end_date,
        "format": fmt,
        "dimensions": ",".join(dimensions),
        "metrics": ",".join(metrics),
        "discrepancy_metrics": "",
        "display_alignment": True,
        "time_breakdown": time_breakdown,
        "country_code_format": "iso",
    }
    # Purchase/Add To Cart 같은 커스텀 이벤트는 metrics가 아니라 cohort_metrics+cohort_periods로 받는다.
    # cohort_periods="actual"은 설치일 기준 코호트가 아니라 "그 날짜에 실제 발생한 값" (Singular 문서 확인).
    if cohort_metrics:
        payload["cohort_metrics"] = ",".join(cohort_metrics)
        payload["cohort_periods"] = ",".join(cohort_periods) if cohort_periods else "actual"
    resp = requests.post(
        f"{BASE_URL}/create_async_report",
        params={"api_key": _api_key()},
        data=payload,
    )
    if not resp.ok:
        print(f"[ERROR] {resp.status_code} {resp.text}")
    resp.raise_for_status()
    return resp.json()["value"]["report_id"]


def wait_for_report(report_id, poll_interval=5, timeout=600):
    elapsed = 0
    while elapsed < timeout:
        resp = requests.get(
            f"{BASE_URL}/get_report_status",
            params={"api_key": _api_key(), "report_id": report_id},
        )
        if not resp.ok:
            print(f"[ERROR] {resp.status_code} {resp.text}")
        resp.raise_for_status()
        value = resp.json()["value"]
        status = value["status"]  # QUEUED / STARTED / DONE / FAILED

        if status == "DONE":
            return value["download_url"]
        if status == "FAILED":
            raise RuntimeError(f"Singular report failed: {value.get('error_message')}")

        print(f"[{elapsed}s] status={status} ...")
        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError("Singular report polling timed out")


def download_report(download_url):
    resp = requests.get(download_url)
    resp.raise_for_status()
    # download_url(S3)이 Content-Type에 charset을 안 줘서 requests가 인코딩을 잘못 추측하면
    # resp.text 단계에서 이미 한글이 깨진다. UTF-8로 직접 디코딩해서 그 문제를 우회한다.
    return resp.content.decode("utf-8")


def main():
    start_date = "2026-08-14"
    end_date = "2026-08-27"

    # cmp 매핑 확인을 위해 캠페인 관련 dimension을 여러 개 같이 요청한다.
    dimensions = ["app", "source", "adn_campaign_id", "adn_campaign_name", "tracker_campaign_name"]
    metrics = ["tracker_installs", "tracker_reengagements"]

    organization_key = resolve_organization_key()
    print(f"organization_key={organization_key}")

    print("\n[cohort_metrics 조회 - Purchase/AddToCart 등 커스텀 이벤트 목록 확인]")
    cohort_info = get_cohort_metrics(organization_key)
    cohort_metric_list = cohort_info["value"]["metrics"]
    id_to_name = {m["name"]: m["display_name"] for m in cohort_metric_list}
    cohort_metric_ids = list(id_to_name.keys())
    print(f"커스텀 이벤트 {len(cohort_metric_ids)}개: {list(id_to_name.values())}")
    # periods=["actual"] -> 설치일 기준 코호트(1d/7d/14d/30d)가 아니라
    # "그 날짜에 실제 발생한 값" (Singular 문서로 확인) - report_addi_conv_app이 원하는 것과 동일한 개념.

    print(f"\nreport 생성 요청: {start_date} ~ {end_date}")
    report_id = create_async_report(
        organization_key, start_date, end_date, dimensions, metrics,
        cohort_metrics=cohort_metric_ids, cohort_periods=["actual"],
    )
    print(f"report_id={report_id}")

    download_url = wait_for_report(report_id)
    print(f"download_url={download_url}")

    csv_text = download_report(download_url)

    raw_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "singular_daily_report_result.csv")
    with open(raw_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_text)
    print(f"원본 CSV 저장: {raw_path}")

    reader = csv.DictReader(io.StringIO(csv_text))
    print("\n원본 컬럼:", reader.fieldnames)
    rows = list(reader)
    for row in rows[:10]:
        print(row)
    if len(rows) > 10:
        print(f"... (앞 10행만 출력, 전체 {len(rows)}행은 CSV 파일 참고)")

    # 커스텀 이벤트 컬럼명이 opaque id(예: 50020f41ae064e9aa48568b8b44bb34f)라서
    # display_name(Purchase 등)으로 바꾼 사람이 읽을 수 있는 버전을 별도로 저장한다.
    def friendly(col):
        for metric_id, display_name in id_to_name.items():
            if metric_id in col:
                return col.replace(metric_id, display_name)
        return col

    friendly_fieldnames = [friendly(c) for c in reader.fieldnames]
    named_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "singular_daily_report_result_named.csv"
    )
    with open(named_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(friendly_fieldnames)
        for row in rows:
            writer.writerow([row[c] for c in reader.fieldnames])
    print(f"컬럼명 변환 CSV 저장: {named_path}")


if __name__ == "__main__":
    main()
