# Athena 테이블 타입: Hive와 Iceberg

## 핵심

`table_type`은 데이터를 어떤 파일 형식으로 저장할지가 아니라, **S3 파일과 테이블 메타데이터를 어떻게 관리할지**를 결정한다.

```sql
table_type = 'ICEBERG'
format = 'PARQUET'
```

위 설정은 다음 의미다.

```text
Iceberg: 테이블 메타데이터·스냅샷·트랜잭션 관리 방식
Parquet: 실제 데이터 파일 형식
```

따라서 Iceberg와 Parquet는 서로 대체하는 개념이 아니다. Iceberg 테이블도 내부 데이터 파일은 Parquet로 저장할 수 있다.

## `table_type`을 생략하면

일반적인 Athena CTAS에서 `table_type`을 생략하면 기본 테이블 타입은 Apache Hive다.

```sql
CREATE TABLE example
WITH (
    format = 'PARQUET',
    external_location = 's3://bucket/path/'
)
AS SELECT ...;
```

위 테이블은 다음 조합이다.

```text
table_type = HIVE
format = PARQUET
```

## Hive 테이블과 Iceberg 테이블 비교

| 구분 | Hive 테이블 | Iceberg 테이블 |
|---|---|---|
| 실제 데이터 | S3 파일 | S3 파일 |
| 메타데이터 | Glue 스키마·파티션 중심 | Iceberg 메타데이터·스냅샷 |
| `INSERT INTO` | 가능 | 가능 |
| `UPDATE`·`DELETE` | 일반적으로 지원하지 않음 | 지원 |
| `MERGE INTO` | 불가능 | 가능 |
| 트랜잭션 | 없음 | ACID 트랜잭션 |
| 과거 버전 조회 | 어려움 | Time travel 가능 |
| 파티션 | 명시적 파티션 관리 | Hidden partitioning 지원 |
| 운영 난이도 | 단순 | 스냅샷·파일 관리 필요 |
| 적합한 용도 | append-only 이력·로그 | 갱신되는 current·요약 테이블 |

## Hive 테이블의 특징

Hive 테이블에서 `INSERT INTO`를 실행하면 기존 파일을 수정하지 않고 새 파일을 추가한다.

```text
기존 파일 + 이번 주 파일 + 다음 주 파일
```

주간 이력처럼 과거 행을 수정하지 않고 계속 추가하는 데이터에 적합하다. 반대로 동일 관계의 `last_seen_at`이나 `observation_count`를 갱신하려면 조회 시 `GROUP BY`를 수행하거나 CTAS로 테이블을 다시 만들어야 한다.

## Iceberg 테이블의 특징

Iceberg는 데이터 파일과 함께 테이블 상태를 스냅샷으로 관리한다. 따라서 기존 행 갱신과 신규 행 추가를 하나의 트랜잭션으로 수행할 수 있다.

```sql
MERGE INTO current_table AS target
USING weekly_delta AS source
ON target.mapping_key = source.mapping_key
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...;
```

Athena의 `MERGE INTO`는 Athena Engine 3의 Iceberg 테이블에서만 지원된다.

Iceberg 테이블은 이전 스냅샷을 기준으로 조회할 수도 있다.

```sql
SELECT *
FROM current_table
FOR TIMESTAMP AS OF
    (CURRENT_TIMESTAMP - INTERVAL '1' DAY);
```

## Iceberg의 운영 주의점

`MERGE`, `UPDATE`, `DELETE`가 반복되면 delete 파일과 작은 파일이 늘어날 수 있다. 데이터가 누적되면 주기적으로 다음 작업을 검토한다.

```sql
OPTIMIZE "dev-ptbwa-dw"."stb_mobile_mapping_current"
REWRITE DATA USING BIN_PACK;

VACUUM "dev-ptbwa-dw"."stb_mobile_mapping_current";
```

`VACUUM`은 오래된 스냅샷과 고아 파일을 정리하므로 S3 삭제 권한과 보존 기간 정책을 확인해야 한다.

## 현재 매핑 설계에 적용

현재 매핑 파이프라인에서는 테이블의 역할에 따라 다음 구성이 적합하다.

| 테이블 | 권장 타입 | 이유 |
|---|---|---|
| `stb_mobile_mapping_weekly` | Hive + Parquet | 주간 데이터를 계속 추가하는 이력 테이블 |
| `stb_mobile_mapping_current` | Iceberg + Parquet | 기존 관계의 최종 관측 시각·횟수를 `MERGE`로 갱신 |
| `stb_summary` | View 또는 별도 집계 테이블 | current를 기준으로 조회·집계 |

```text
weekly history: INSERT INTO
current:        MERGE INTO
summary:        current 조회
```

`stb_mobile_mapping_current`를 기본 Hive 테이블로 만들면 `MERGE INTO`가 실행되지 않는다. 그 경우 매번 전체 이력을 집계해 current를 다시 생성해야 하므로, 현재처럼 주간 증분으로 최신 상태를 관리하려면 Iceberg를 사용하는 편이 효율적이다.

## 참고

- [AWS Athena CTAS](https://docs.aws.amazon.com/athena/latest/ug/create-table-as.html)
- [AWS Athena Iceberg 테이블 생성](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html)
- [AWS Athena MERGE INTO](https://docs.aws.amazon.com/athena/latest/ug/merge-into-statement.html)
- [AWS Athena Iceberg 최적화](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-data-optimization.html)
