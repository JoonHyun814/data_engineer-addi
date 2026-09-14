# stb_mobile_mapping_current 테이블 명세서

대상 테이블: `dev-ptbwa-dw.stb_mobile_mapping_current` (Iceberg, `s3://ptbwa-dw/dev/stb_mobile_mapping_current/`)

관련 SQL:
- 스키마 생성: `mapping/querys/21_create_stb_mobile_mapping_current.sql`
- 주간 병합(갱신) 로직: `mapping/querys/22_merge_stb_mobile_mapping_current.sql`
- weekly 테이블 명세서: `mapping/docs/stb-mobile-mapping-weekly-columns.md`

## 1. 개요

`stb_mobile_mapping_weekly`의 주간 스냅샷을 오래된 순서대로 하나씩 `MERGE`해서 만드는 **현재 시점 기준 누적 최신 상태** 테이블이다. weekly가 "그 주에 무슨 일이 있었는지"라면, current는 "지금까지 누적해서 무슨 상태인지"에 해당한다.

## 2. 행의 성격 및 그레인

weekly와 동일하게 `STB_IP`(셋톱 전체 모집단), `MAPPING`(셋톱–모바일 ADID 후보) 두 종류 행이 있고, 그레인도 동일하다.

```text
record_type, carrier, plattform_id, ip, ad_id, cate
```

다만 weekly는 그레인이 `batch_week`별로 반복되지만, current는 이 조합당 **행이 1개만** 존재한다(주간 값을 계속 병합하며 갱신).

## 3. 컬럼 명세

| 컬럼명 | 한글 명칭 | 설명(계산식) |
|---|---|---|
| `record_type` | 레코드 유형 | weekly와 동일 |
| `plattform_id` | 셋톱 광고식별자 | weekly와 동일 |
| `ad_id` | 모바일 광고식별자(ADID) | weekly와 동일 |
| `ip` | IP 주소 | weekly와 동일 |
| `carrier` | 통신사 | weekly와 동일 |
| `cate` | 모바일 데이터 출처 | weekly와 동일 |
| `stb_first_seen_at` | 셋톱 최초 관측 시각 | weekly 값을 누적: `LEAST(기존 current 값, 신규 배치 weekly 값)` |
| `stb_last_seen_at` | 셋톱 최종 관측 시각 | weekly 값을 누적: `GREATEST(기존 current 값, 신규 배치 weekly 값)` |
| `mobile_first_seen_at` | 모바일 최초 관측 시각 | weekly 값을 누적: 한쪽이 `NULL`이면 나머지 값, 둘 다 있으면 `LEAST(기존, 신규)` |
| `mobile_last_seen_at` | 모바일 최종 관측 시각 | weekly 값을 누적: 한쪽이 `NULL`이면 나머지 값, 둘 다 있으면 `GREATEST(기존, 신규)` |
| `stb_observation_count` | 셋톱 관측 건수(누적) | weekly 값을 누적 합산: `기존값 + 신규 배치값` |
| `mobile_observation_count` | 모바일 관측 건수(누적) | `cate = 'TG'`면 `GREATEST(기존값, 신규 배치값)`, `NHN`이면 `기존값 + 신규 배치값` |
| `ip_adid_cardinality` | IP당 고유 ADID 수 | 누적하지 않고 **최신 배치 weekly 값으로 덮어씀** |
| `first_batch_week` | 최초 반영 배치 주 | 이 키가 처음 INSERT된 `batch_week`. 이후 변경되지 않음 |
| `last_batch_week` | 최종 반영 배치 주 | 가장 최근에 반영된 `batch_week`. 병합할 때마다 갱신 |

## 4. 주의사항

- `stb_observation_count`, `mobile_observation_count`는 고유 방문자 수가 아니라 누적 건수다.
- `mobile_observation_count`는 출처에 따라 누적 방식이 다르다 — TG는 월 데이터가 여러 주에서 반복 참조되므로 합산 대신 최댓값을 유지한다.
- `ip_adid_cardinality`는 스냅샷(최신 배치 기준) 값이며 과거 값과 합산/평균하지 않는다. 20을 초과하면 해당 IP의 `MAPPING` 행은 애초에 생성되지 않지만(weekly 단계 필터), `STB_IP` 행과 값 자체는 진단용으로 보존된다.
- 같은 `batch_week`를 재실행해도 `WHEN MATCHED ... AND source.batch_week > target.last_batch_week` 조건 때문에 중복 반영되지 않는다.
- 활성 여부(최근 6개월 이내 관측)는 컬럼으로 저장되지 않고 조회 시점에 `mobile_last_seen_at` 기준으로 계산한다(`mapping/querys/30_create_stb_mobile_mapping_views.sql` 참고).
