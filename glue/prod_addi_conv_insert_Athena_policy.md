# prod_addi_conv_insert_Athena - IAM Policy 문서

## 개요

| 항목 | 내용 |
|---|---|
| Glue Job | `prod_addi_conv_insert_Athena` |
| Policy 파일 | `prod_addi_conv_insert_Athena_policy.json` |
| Region | `ap-northeast-2` |
| Account ID | `170217667865` |
| Worker | G.1X / 2 workers |

---

## 동작 흐름

```
S3에서 SQL 파일 읽기 (ptbwa-da)
    ↓
Glue Catalog에서 테이블 S3 위치 조회
    ↓
S3 파티션 파일 삭제 (ptbwa-da / ptbwa-athena)
    ↓
Athena DROP PARTITION 실행
    ↓
Athena INSERT INTO 실행
    - 소스 테이블 읽기: ptbwa-da, propfit-bid-logs, cookie-match
    - 결과 저장: ptbwa-da/prod/athena-query-results/
```

---

## Statement별 권한 정리

### S3GlueScript
Glue Job 스크립트 파일 읽기

| 버킷 | 경로 | 권한 |
|---|---|---|
| `aws-glue-assets-170217667865-ap-northeast-2` | `scripts/*` | GetObject |

### S3GlueAssets
Glue 임시 파일 (스파크 shuffle, 로그 등)

| 버킷 | 경로 | 권한 |
|---|---|---|
| `aws-glue-assets-170217667865-ap-northeast-2` | `*` | GetObject, PutObject, DeleteObject, ListBucket |

### S3DataBucketDa
주요 데이터 버킷 (SQL 쿼리 파일, 적재 대상 테이블, Athena 쿼리 결과, 소스 테이블 일부)

| 버킷 | 경로 | 권한 |
|---|---|---|
| `ptbwa-da` | `prod/*` | GetObject, PutObject, DeleteObject, ListBucket, GetBucketLocation |

`prod/*` 하위 주요 경로:

| 경로 | 용도 |
|---|---|
| `prod/prod_addi_conv/query/` | SQL 파일 |
| `prod/prod_addi_conv/report_addi_conv_*/` | 적재 대상 테이블 (gtm, app) |
| `prod/addi_conv_info/` | 소스 테이블 |
| `prod/addi_conv_metric_youtube/` | 소스 테이블 |
| `prod/addi_conv_gclid_youtube/` | 소스 테이블 |
| `prod/athena-query-results/` | Athena 쿼리 결과 |

### S3SourceBucketPropfit
`prod-ptbwa-dw` DB 소스 테이블 데이터 (읽기 전용)

| 버킷 | 용도 | 권한 |
|---|---|---|
| `propfit-bid-logs` | `postback_thirdparty_log` 등 소스 데이터 | GetObject, ListBucket, GetBucketLocation |
| `cookie-match` | `gtm_logs` 등 소스 데이터 | GetObject, ListBucket, GetBucketLocation |

> `prod-ptbwa-dw` 테이블이 추가 버킷을 사용하는 경우 동일 Statement에 버킷 ARN 추가 필요

### S3DataBucketAthena
`report_addi_conv_metric_youtube` 테이블 데이터

| 버킷 | 경로 | 권한 |
|---|---|---|
| `ptbwa-athena` | `*` | GetObject, PutObject, DeleteObject, ListBucket, GetBucketLocation |

### AthenaQuery
Athena 쿼리 실행 (DROP PARTITION, INSERT INTO)

| 리소스 | 권한 |
|---|---|
| `workgroup/primary` | StartQueryExecution, GetQueryExecution, GetQueryResults, StopQueryExecution, GetWorkGroup |

### GlueCatalog
테이블 위치 조회 및 파티션 CRUD

| 대상 DB | 용도 | 권한 |
|---|---|---|
| `prod_addi_conv` | 적재 대상 테이블 메타데이터 | 읽기 + 파티션 CRUD |
| `prod-ptbwa-dw` | 소스 테이블 메타데이터 | 읽기 |

### EC2VpcAccess
Glue Job 네트워크 설정 (VPC 내 실행 시 필요)

### CloudWatchLogs
Glue Job 로그 기록 (`/aws-glue/*`)

---

## Job Parameters

| Key | 필수 | 기본값 | 예시 |
|---|---|---|---|
| `--s3_query_path` | ✓ | - | `s3://ptbwa-da/prod/prod_addi_conv/query/report_addi_conv_app.sql` |
| `--athena_table` | ✓ | - | `report_addi_conv_app` |
| `--date` | | 어제 날짜 | `2026-05-09` |
| `--athena_db` | | `prod_addi_conv` | `prod_addi_conv` |
| `--s3_output_location` | | `s3://ptbwa-da/prod/athena-query-results/` | - |

---

## 지원 테이블

| athena_table | SQL 파일 | 소스 DB |
|---|---|---|
| `report_addi_conv_metric_youtube` | `report_addi_conv_metric_youtube.sql` | `prod_addi_conv` |
| `report_addi_conv_gtm_youtube` | `report_addi_conv_gtm_youtube.sql` | `prod_addi_conv`, `prod-ptbwa-dw` |
| `report_addi_conv_app` | `report_addi_conv_app.sql` | `prod_addi_conv`, `prod-ptbwa-dw` |

---

## 에러 이력 및 조치

| 에러 | 원인 | 조치 |
|---|---|---|
| Unable to verify/create output bucket ptbwa-athena | Athena output bucket 권한 누락 | `s3:GetBucketLocation` 추가, output 경로를 `ptbwa-da`로 변경 |
| s3:GetObject on prod/addi_conv_info/ | `ptbwa-da/prod/*` 범위 미포함 | `prod/prod_addi_conv/*` → `prod/*` 로 확장 |
| glue:GetDatabase on prod-ptbwa-dw | Glue Catalog 소스 DB 권한 누락 | `prod-ptbwa-dw` DB/Table ARN 추가 |
| s3:ListBucket on propfit-bid-logs | 소스 테이블 버킷 권한 누락 | `S3SourceBucketPropfit` statement 추가 |
| s3:ListBucket on cookie-match | 소스 테이블 버킷 권한 누락 | `cookie-match` ARN 추가 |
