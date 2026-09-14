# stb_mobile_mapping_weekly 테이블 명세서

대상 테이블: `dev-ptbwa-dw.stb_mobile_mapping_weekly` (Hive/Parquet, `batch_week` 파티션)

관련 SQL:
- 스키마 생성: `mapping/querys/11_create_stb_mobile_mapping_weekly.sql`
- 주간 적재 로직: `mapping/querys/12_insert_stb_mobile_mapping_weekly.sql`
- 이 테이블을 소비하는 병합: `mapping/querys/22_merge_stb_mobile_mapping_current.sql`
- current 테이블 명세서: `mapping/docs/stb-mobile-mapping-current-columns.md`

## 1. 개요

셋톱 3개 소스(APM, ADDI 자체 입찰 로그, ADDI 포스트백 로그)와 NHN·TG(모바일)의 **한 주간(월~일) 원본 로그**를 집계해 셋톱–모바일 IP 매핑 후보를 만든 뒤, `batch_week` 파티션으로 쌓아두는 원본 이력 테이블이다. `stb_mobile_mapping_current`는 이 테이블을 주 단위로 하나씩 읽어 병합(MERGE)한 결과물이므로, weekly는 **가공 전 주간 스냅샷**, current는 **누적 최신 상태**라고 보면 된다.

셋톱 원천 3종:

| 소스 | 테이블 | 셋톱 ID | IP | 통신사 | 비고 |
|---|---|---|---|---|---|
| APM | `apm_bid_log_flatten` | `ifa` | `ip` | `app_bundle` | |
| ADDI 자체 입찰 로그 | `addi_bid_log_flatten` | `device_ifa` | `device_ip` | `app_bundle` | `media_id = 'B8BKL2YDDVZQ'`만 포함 |
| ADDI 포스트백 로그 | `addi_postback_log` | `ifa` | `request_ip` | `ctv_media` | conversion 여부(`log_type`)와 무관하게 전체 포함 |

세 소스는 `(carrier, plattform_id, ip)` 기준으로 합쳐진 뒤 하나의 셋톱 모집단으로 취급되며, 그 주에 실제로 관측된 출처 목록은 `stb_sources` 컬럼에 남는다.

## 2. 행의 성격 및 그레인

`stb_mobile_mapping_current`와 동일하게 두 종류의 행이 섞여 있다.

- `STB_IP`: 해당 주에 관측된 셋톱–IP 조합 1건 (모바일 매칭 여부 무관, 전체 모집단)
- `MAPPING`: 해당 주에 동일 IP로 연결된 셋톱–모바일 ADID 후보 1건

한 배치(`batch_week`) 안에서 그레인은 `record_type, carrier, plattform_id, ip, ad_id, cate`이다.

## 3. 컬럼 명세

| 컬럼명 | 한글 명칭 | 설명(계산식) |
|---|---|---|
| `record_type` | 레코드 유형 | `STB_IP`(셋톱 전체 모집단) 또는 `MAPPING`(IP 일치 후보 매핑) |
| `plattform_id` | 셋톱 광고식별자 | APM `ifa` / ADDI 입찰 로그 `device_ifa` / ADDI 포스트백 `ifa`를 소문자·공백 제거로 정규화한 값 |
| `ad_id` | 모바일 광고식별자(ADID) | NHN `device_ifa` 또는 TG `uuid` 정규화 값. `STB_IP`는 `NULL` |
| `ip` | IP 주소 | 셋톱/매칭 IP. `::ffff:` 접두사 제거, 소문자·공백 제거 |
| `carrier` | 통신사 | APM/ADDI 입찰 로그는 `app_bundle`, ADDI 포스트백은 `ctv_media` 패턴으로 판별한 `SKB`/`U+`/`KT` |
| `cate` | 모바일 데이터 출처 | `NHN` 또는 `TG`. `STB_IP`는 `NULL` |
| `stb_first_seen_at` | 셋톱 최초 관측 시각(주간) | 3개 소스를 합친 뒤 같은 주 안에서 `carrier, plattform_id, ip`별 관측 시각의 `MIN` |
| `stb_last_seen_at` | 셋톱 최종 관측 시각(주간) | 3개 소스를 합친 뒤 같은 주 안에서 `carrier, plattform_id, ip`별 관측 시각의 `MAX` |
| `mobile_first_seen_at` | 모바일 최초 관측 시각(주간) | NHN: `cate, ip, ad_id`별 관측 시각의 `MIN`. TG: 해당 월 1일 00:00:00(실제 시각 정보 없음) |
| `mobile_last_seen_at` | 모바일 최종 관측 시각(주간) | NHN: `cate, ip, ad_id`별 관측 시각의 `MAX`. TG: 해당 월 말일 23:59:59 |
| `stb_observation_count` | 셋톱 관측 건수(주간) | 3개 소스를 합친 뒤 `carrier, plattform_id, ip`별 그 주 로그 행 수(`COUNT(*)`). 소스별로 나뉘지 않는다 |
| `mobile_observation_count` | 모바일 관측 건수(주간) | `cate, ip, ad_id`별 그 주(TG는 해당 월) 로그 행 수(`COUNT(*)`) |
| `ip_adid_cardinality` | IP당 고유 ADID 수(주간) | NHN+TG를 합친 그 주 데이터에서 `ip`별 `COUNT(DISTINCT ad_id)`. `STB_IP` 행은 매칭 없으면 `0` |
| `stb_sources` | 셋톱 관측 출처 목록(주간) | 그 주에 해당 `carrier, plattform_id, ip`를 관측한 로그 출처 배열. `'APM'`/`'ADDI_BID'`/`'ADDI_POSTBACK'` 중 실제 관측된 값만, 중복 제거해서 담는다 |
| `batch_week` | 배치 주(파티션) | 처리 대상 주의 월요일 날짜(`YYYY-MM-DD`). 파티션 컬럼 |

## 4. 특이사항

- **20개 초과 IP 제외**: `ip_adid_cardinality`가 20을 넘는 IP는 NAT 등 공유 IP로 보고 `MAPPING` 행 생성 대상에서 제외한다. 단 `STB_IP` 행은 그대로 남고 카디널리티 값도 진단용으로 보존된다.
- **carrier 미판별 셋톱 제외**: `app_bundle`/`ctv_media`로 통신사가 판별되지 않으면 해당 셋톱 로그는 집계에서 제외된다.
- **셋톱 소스 3종 통합**: APM/ADDI 입찰/ADDI 포스트백 로그를 `(carrier, plattform_id, ip)` 기준으로 합쳐 하나의 셋톱 모집단으로 만든다. 한 셋톱–IP 조합이 여러 소스에서 동시에 관측되면 `stb_observation_count`에는 합산되고, `stb_sources`에는 관측된 소스가 모두 남는다(개별 소스별 관측 건수는 구분되지 않는다).
- **ADDI 자체 입찰 로그는 media_id 필터 적용**: `addi_bid_log_flatten`은 `media_id = 'B8BKL2YDDVZQ'`인 행만 사용한다.
- **ADDI 포스트백은 이벤트 유형 무관**: `addi_postback_log`는 다른 리포트 쿼리와 달리 `log_type = 'v_complete'` 같은 conversion 필터를 적용하지 않고, 유효한 `ifa`/`request_ip`가 있는 모든 행을 셋톱 모집단에 포함한다.
- **TG는 월 단위 관측**: TG 원천에 시:분:초 정보가 없어 `mobile_first/last_seen_at`이 실제 발생 시각이 아니라 해당 월의 시작/끝이다. 같은 월을 포함하는 여러 주에서 값이 동일하게 반복될 수 있다.
- **중복 적재 주의**: 같은 `batch_week`를 두 번 `INSERT`하면 행이 중복된다. 배치별로 1회만 실행해야 하며, 재실행 방지는 이 테이블이 아니라 `22_merge...sql`의 `last_batch_week` 비교 조건에서 이루어진다.
- **파티션 프루닝 방식이 소스마다 다름**: APM/NHN은 0-padding이 확인되어 `YYYYMMDD` 정수 범위로 정적 프루닝하지만, ADDI 입찰/포스트백 로그는 0-padding 여부가 확인되지 않아 `DATE_PARSE` 기반 범위 비교를 사용한다. 후자는 매주 `params.week_start`만 바꾸면 되고 별도 리터럴 수정이 필요 없다.
