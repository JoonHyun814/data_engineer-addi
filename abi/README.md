# PTBWA Log ETL Step Functions

Athena / Glue / RDB로 이어지는 PTBWA 광고 로그(ABI, APM, NHN) 집계 파이프라인 정리. 아래 3개의 최상위 Step Functions를 중심으로, 이들이 호출하는 공용 하위 State Machine, Lambda, Athena 쿼리 파일을 정리한다.

- `stepfunctions/ptbwa-postback-log-etl-hourly.json`
- `stepfunctions/ptbwa-bid-log-etl-hourly.json`
- `stepfunctions/ptbwa-log-etl-daily.json`

## 공통 구조

세 파이프라인 모두 아래 순서를 따른다.

1. 매체(ABI/APM/NHN)별 원본 로그가 S3(`propfit-bid-logs`)에 다 쌓였는지 확인
2. 필요 시 Glue Crawler(Workflow)를 실행해 카탈로그를 최신화
3. Athena 쿼리로 집계/평탄화 후 필요하면 RDB(`ptbwa_propfit`)에 적재

공용으로 재사용되는 하위 State Machine 3개:

| State Machine | 역할 | 사용 Lambda / Job |
|---|---|---|
| `athena-insert-data` | S3에 있는 쿼리(`.sql`)를 다운로드해 날짜 플레이스홀더를 치환하고 Athena에서 `INSERT INTO ...` 실행 | `DeleteS3Objects`(기존 출력 삭제, 레포에 소스 없음), `CreateAthenaQuery`(`lambda/CreateAthenaQuery`) |
| `ptbwa-log-agg` | `athena-insert-data` 실행 후 Glue Job으로 Athena 결과를 RDB에 적재 | `athena-insert-data`, Glue Job `insert-athena-data-to-rdb`(`glue/insert-athena-data-to-rdb.py`) |
| `data-consistency` | 정합성 체크 쿼리를 실행해 결과 로우 수를 `match_condition`과 비교, 불일치 시 알림 | `CreateAthenaQuery`, `DataConsistencyAlert`(레포에 소스 없음) |

`CreateAthenaQuery` 람다(`lambda/CreateAthenaQuery/query.py`)는 `query_type`에 맞는 `querys/{query_dirs}/{query_type}.sql`을 S3 버킷 `ptbwa-athena`에서 받아 `{input_year}`, `{input_month}`, `{input_day}`, `{input_hour}`, `{exchange_first_day}`, `{exchange_last_day}` 등의 플레이스홀더를 실제 날짜값으로 치환한다.

---

## 1. `ptbwa-postback-log-etl-hourly` — 포스트백 로그 시간별 집계

**입력**: `{ "date": "YYYY-MM-DD HH:MM:SS" }`

**흐름**:
1. 120초 대기(로그 적재 시간 확보) 후 Parallel로 ABI/APM/NHN 3개 브랜치 동시 진행
   - S3에서 해당 시간대 postback 로그 목록 조회 → ELB(`describeTargetHealth`)로 정상 인스턴스 수 조회 → 로그 개수가 인스턴스 수 대비 부족하면 `PtbwaLogMissingAlert` 람다(`lambda/PtbwaLogMissingAlert`) 호출해 알림
     - ABI: S3 prefix `ab/propfit_log/ab_postback_log/...`, ELB `propfit-authorizedbuyers`
     - APM: S3 prefix `postback_log/...`, ELB `propfit-01-tg`
     - NHN: S3 prefix `nhn/propfit_log/nhn_postback_log/...`, ELB `propfit-v2-bidder-tg` (인스턴스당 로그 3배 기준)
2. Glue Crawler Workflow `ptbwa-postback-hourly` 실행/완료 대기
3. **General Agg** → `ptbwa-log-agg` 호출

**사용 쿼리**: `querys/prod-report_summary_hour.sql`
**사용 테이블**: Athena `prod-ptbwa-da.report_summary_hour` → RDB `ptbwa_propfit.report_summary_hour`

---

## 2. `ptbwa-bid-log-etl-hourly` — 비드 로그 시간별 평탄화(flatten)

**입력**: `{ "date": "YYYY-MM-DD HH:MM:SS" }`

**흐름**: 120초 대기 후 Parallel로 ABI/APM/NHN 3개 브랜치가 각각 독립적으로 진행 (postback 파이프라인과 동일한 S3-vs-ELB 로그 개수 비교 + `PtbwaLogMissingAlert` 알림 구조를 공유).

각 브랜치는 자체 Glue Crawler를 실행/완료 대기한 뒤, `athena-insert-data`를 직접 호출해 원본 bid 로그를 평탄화(flatten)한 테이블에 적재한다. (이 파이프라인은 `ptbwa-log-agg`를 거치지 않으므로 RDB 적재 단계가 없다.)

| 매체 | S3 prefix | ELB Target Group | Glue Crawler Workflow | 쿼리 (`query_type`) | Athena 적재 위치 |
|---|---|---|---|---|---|
| ABI | `ab/propfit_log/ab_bid_log/...` | `propfit-authorizedbuyers` | `ptbwa-abi-bid-hourly` | `prod-abi_bid_log_flatten` → `querys/prod-abi_bid_log_flatten.sql` | `prod/abi_bid_log_flatten` (bucket `ptbwa-dw`) |
| APM | `bid_log/...` | `propfit-01-tg` | `ptbwa-apm-bid-hourly` | `prod-apm_bid_log_flatten` → `querys/prod-apm_bid_log_flatten.sql` | `prod/apm_bid_log_flatten` (bucket `ptbwa-dw`) |
| NHN | `nhn/propfit_log/nhn_bid_log/...` | `propfit-v2-bidder-tg` | `ptbwa-nhn-bid` | `prod-nhn_bid_log_flatten` → `querys/prod-nhn_bid_log_flatten.sql` | `prod/nhn_bid_log_flatten` (bucket `ptbwa-dw`) |

---

## 3. `ptbwa-log-etl-daily` — 일별 집계 및 데이터 정합성 검증

**입력**: `{ "date": "YYYY-MM-DD" }`

**흐름**:
1. **Is Exist Log** (Parallel): ABI/NHN은 일 단위, APM은 해당 일자의 시간 prefix로 S3 로그 존재 여부 확인
2. 로그가 하나라도 있으면 Glue Crawler Workflow `ptbwa-log-daily` 실행/완료 대기
3. **Agg** (Parallel, 4개 브랜치) — 모두 `ptbwa-log-agg` 호출:

   | 브랜치 | 쿼리 (`query_type`) | Athena 적재 위치 | RDB 테이블 |
   |---|---|---|---|
   | General Agg | `prod-report_summary_daily` → `querys/prod-report_summary_daily.sql` | `prod/report_summary_daily` | `report_summary_daily` |
   | Reach Agg | `prod-report_summary_reach_daily` (쿼리 파일이 이 레포의 `querys/`에는 없음 — S3 `ptbwa-athena` 버킷에만 존재) | `prod/report_summary_reach_daily` | `report_summary_reach_daily` |
   | Reach CMP Agg | `prod-report_summary_cmp_reach_daily` (쿼리 파일이 이 레포의 `querys/`에는 없음) | `prod/report_summary_cmp_reach_daily` | `report_summary_cmp_reach_daily` |
   | Channel Agg | `prod-report_summary_channel_daily` → `querys/prod-report_summary_channel_daily.sql` | `prod/report_summary_channel_daily` | `report_summary_channel_daily` |

   각 브랜치는 `Catch`로 실패를 흡수해 다른 브랜치에 영향을 주지 않는다.

4. **데이터 정합성** (Parallel, 3개 브랜치) — 모두 `data-consistency` 호출, `match_condition: 0`(불일치 로우가 0건이어야 정상):

   | 브랜치 | 쿼리 (`query_type`) | 검증 내용 |
   |---|---|---|
   | Compare report_summary_daily and report_summary_hour | `prod-data_consistency_report_summary_hour_and_daily` → `querys/prod-data_consistency_report_summary_hour_and_daily.sql` | `report_summary_hour` vs `report_summary_daily` 값 불일치 여부 |
   | Compare report_summary_channel_daily and report_summary_hour | `prod-data_consistency_report_summary_daily_and_channel` → `querys/prod-data_consistency_report_summary_daily_and_channel.sql` | `report_summary_daily` vs `report_summary_channel_daily` 값 불일치 여부 |
   | report_summary_reach_daily 음수 여부 | `prod-data_consistency_report_summary_reach_daily` → `querys/prod-data_consistency_report_summary_reach_daily.sql` | `report_summary_reach_daily`의 음수값 존재 여부 |

   불일치(`RowCount != match_condition`) 시 `DataConsistencyAlert` 람다로 `error_message`와 함께 알림.

---

## 참고: 레포에 포함된 Lambda / Glue Job

| 이름 | 경로 | 사용처 |
|---|---|---|
| `CreateAthenaQuery` | `lambda/CreateAthenaQuery` | `athena-insert-data`, `data-consistency` — 쿼리 다운로드 및 날짜 치환 |
| `PtbwaLogMissingAlert` | `lambda/PtbwaLogMissingAlert` | `ptbwa-postback-log-etl-hourly`, `ptbwa-bid-log-etl-hourly` — S3 로그 수 vs ELB 인스턴스 수 불일치 알림 |
| `PtbwaPostbackLogDetect` | `lambda/PtbwaPostbackLogDetect` | 위 3개 Step Functions에서는 직접 호출되지 않음 (다른 트리거/용도로 추정) |
| `insert-athena-data-to-rdb` | `glue/insert-athena-data-to-rdb.py` | `ptbwa-log-agg` — Athena 집계 결과를 RDB로 적재 |
| `DeleteS3Objects` | 레포에 소스 없음 (ARN만 참조) | `athena-insert-data` — 쿼리 실행 전 기존 출력 삭제 |
| `DataConsistencyAlert` | 레포에 소스 없음 (ARN만 참조) | `data-consistency` — 정합성 불일치 알림 |
