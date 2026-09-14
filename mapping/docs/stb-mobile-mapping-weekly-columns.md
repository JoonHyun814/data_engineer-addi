# stb_mobile_mapping_weekly 테이블 명세서

대상 테이블: `dev-ptbwa-dw.stb_mobile_mapping_weekly` (Hive/Parquet, `batch_week` 파티션)

관련 SQL:
- 스키마 생성: `mapping/querys/11_create_stb_mobile_mapping_weekly.sql`
- 주간 적재 로직: `mapping/querys/12_insert_stb_mobile_mapping_weekly.sql`
- 이 테이블을 소비하는 병합: `mapping/querys/22_merge_stb_mobile_mapping_current.sql`
- current 테이블 명세서: `mapping/docs/stb-mobile-mapping-current-columns.md`

## 1. 개요

APM(셋톱)과 NHN·TG(모바일)의 **한 주간(월~일) 원본 로그**를 집계해 셋톱–모바일 IP 매핑 후보를 만든 뒤, `batch_week` 파티션으로 쌓아두는 원본 이력 테이블이다. `stb_mobile_mapping_current`는 이 테이블을 주 단위로 하나씩 읽어 병합(MERGE)한 결과물이므로, weekly는 **가공 전 주간 스냅샷**, current는 **누적 최신 상태**라고 보면 된다.

## 2. 행의 성격 및 그레인

`stb_mobile_mapping_current`와 동일하게 두 종류의 행이 섞여 있다.

- `STB_IP`: 해당 주에 관측된 셋톱–IP 조합 1건 (모바일 매칭 여부 무관, 전체 모집단)
- `MAPPING`: 해당 주에 동일 IP로 연결된 셋톱–모바일 ADID 후보 1건

한 배치(`batch_week`) 안에서 그레인은 `record_type, carrier, plattform_id, ip, ad_id, cate`이다.

## 3. 컬럼 명세

| 컬럼명 | 한글 명칭 | 설명(계산식) |
|---|---|---|
| `record_type` | 레코드 유형 | `STB_IP`(APM 전체 모집단) 또는 `MAPPING`(IP 일치 후보 매핑) |
| `plattform_id` | 셋톱 광고식별자 | APM `ifa`를 소문자·공백 제거로 정규화한 값 |
| `ad_id` | 모바일 광고식별자(ADID) | NHN `device_ifa` 또는 TG `uuid` 정규화 값. `STB_IP`는 `NULL` |
| `ip` | IP 주소 | 셋톱/매칭 IP. `::ffff:` 접두사 제거, 소문자·공백 제거 |
| `carrier` | 통신사 | APM `app_bundle`로 판별한 `SKB`/`U+`/`KT` |
| `cate` | 모바일 데이터 출처 | `NHN` 또는 `TG`. `STB_IP`는 `NULL` |
| `stb_first_seen_at` | 셋톱 최초 관측 시각(주간) | 같은 주 안에서 `carrier, plattform_id, ip`별 관측 시각의 `MIN` |
| `stb_last_seen_at` | 셋톱 최종 관측 시각(주간) | 같은 주 안에서 `carrier, plattform_id, ip`별 관측 시각의 `MAX` |
| `mobile_first_seen_at` | 모바일 최초 관측 시각(주간) | NHN: `cate, ip, ad_id`별 관측 시각의 `MIN`. TG: 해당 월 1일 00:00:00(실제 시각 정보 없음) |
| `mobile_last_seen_at` | 모바일 최종 관측 시각(주간) | NHN: `cate, ip, ad_id`별 관측 시각의 `MAX`. TG: 해당 월 말일 23:59:59 |
| `stb_observation_count` | 셋톱 관측 건수(주간) | `carrier, plattform_id, ip`별 그 주 로그 행 수(`COUNT(*)`) |
| `mobile_observation_count` | 모바일 관측 건수(주간) | `cate, ip, ad_id`별 그 주(TG는 해당 월) 로그 행 수(`COUNT(*)`) |
| `ip_adid_cardinality` | IP당 고유 ADID 수(주간) | NHN+TG를 합친 그 주 데이터에서 `ip`별 `COUNT(DISTINCT ad_id)`. `STB_IP` 행은 매칭 없으면 `0` |
| `batch_week` | 배치 주(파티션) | 처리 대상 주의 월요일 날짜(`YYYY-MM-DD`). 파티션 컬럼 |

## 4. 특이사항

- **20개 초과 IP 제외**: `ip_adid_cardinality`가 20을 넘는 IP는 NAT 등 공유 IP로 보고 `MAPPING` 행 생성 대상에서 제외한다. 단 `STB_IP` 행은 그대로 남고 카디널리티 값도 진단용으로 보존된다.
- **carrier 미판별 셋톱 제외**: `app_bundle`로 통신사가 판별되지 않으면 해당 셋톱 로그는 집계에서 제외된다.
- **TG는 월 단위 관측**: TG 원천에 시:분:초 정보가 없어 `mobile_first/last_seen_at`이 실제 발생 시각이 아니라 해당 월의 시작/끝이다. 같은 월을 포함하는 여러 주에서 값이 동일하게 반복될 수 있다.
- **중복 적재 주의**: 같은 `batch_week`를 두 번 `INSERT`하면 행이 중복된다. 배치별로 1회만 실행해야 하며, 재실행 방지는 이 테이블이 아니라 `22_merge...sql`의 `last_batch_week` 비교 조건에서 이루어진다.
- **정적 파티션 프루닝**: 원천 로그 조회 시 `YYYYMMDD` 정수 범위로 대상 주(월~일)를 지정하며, 파티션이 0-padding으로 되어 있다는 전제가 깨지면 결과가 틀어질 수 있다.
