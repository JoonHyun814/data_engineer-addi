# 셋톱–모바일 ADID IP 매핑

## 1. 목적

APM-TV 광고 입찰 로그에서 확인한 **셋톱 ID–IP 관계**와 NHN·TG 광고 로그에서 확인한 **모바일 ADID–IP 관계**를 동일 IP 기준으로 연결하여 셋톱–모바일 ADID 후보 매핑을 만든다.

대상 기간은 **2026년 8월과 9월**이다.

```text
APM-TV                       NHN / TG
셋톱 ID ─ 셋톱 IP    동일 IP    모바일 IP ─ 모바일 ADID
                   ────────▶
             셋톱 ID–모바일 ADID 후보 관계
```

IP가 같다는 사실만으로 동일 사용자나 동일 가구임이 확정되지는 않는다. 따라서 결과는 확정 매핑이 아니라 **동일 IP를 사용한 이력이 있는 후보 관계**로 취급한다.

## 2. 전체 단계

| 단계 | 이름 | 역할 |
|---:|---|---|
| 1 | APM STP–IP | APM-TV에서 셋톱 ID와 IP 관계 준비 |
| 2 | NHN IP–ADID | NHN의 IP와 모바일 ADID 정규화 |
| 3 | TG IP–ADID | TG의 IP와 모바일 ADID 정규화 |
| 4 | 모바일 참조 통합 | NHN과 TG를 동일 구조로 통합 |
| 5 | IP 매핑 | 같은 IP를 기준으로 셋톱과 모바일 ADID 연결 |
| 6 | 셋톱별 출처 플래그 | 셋톱별 NHN/TG 매핑 여부 요약 |
| 7 | APM 모집단 | 통신사별 전체 셋톱·IP 수 집계 |
| 8 | IP 분포 | 소스별·통합 IP 매핑 수 집계 |
| 9 | 셋톱 분포 | NHN/TG 단독·중복 셋톱 수 집계 |
| 10 | 모바일 ADID 분포 | 소스별·통합 고유 ADID 수 집계 |
| 11 | 최종 요약 | 통신사별 매핑 수·매핑률·우세 소스 출력 |

단계를 성격별로 묶으면 다음과 같다.

```text
1~4: 원천 데이터 준비 및 정규화
5:   실제 셋톱–모바일 후보 매핑
6:   셋톱별 매핑 출처 요약
7~11: 매핑 결과의 규모, 비율, 분포 분석
```

실제 상세 매핑 목록은 5단계의 `matched`이며, 7~11단계는 매핑 성과를 확인하기 위한 통계 리포트다.

## 3. 단계별 설명

### 3.1 1단계: APM-TV 셋톱 ID–IP 준비

원천 테이블은 `prod-ptbwa-dw.apm_bid_log_flatten`이다. 이 테이블은 일반적인 Application Performance Monitoring 로그가 아니라 APM 계열 TV 매체에서 발생한 **광고 입찰 요청 로그**다.

광고 요청에는 다음과 같은 정보가 들어올 수 있다.

- `req_id`: 광고 요청 식별자
- `ifa`: 셋톱박스 광고 식별자
- `ip`: 광고 요청 당시 IP
- `app_bundle`: 요청을 발생시킨 통신사·TV 앱
- `content_id`, `content_title`, `content_genre`: 요청 당시 콘텐츠 정보
- `imp_*`, `bidfloor`: 광고 지면 및 입찰 조건
- `created_at`: 요청 발생 시각

1단계에서는 이 중 `app_bundle`, `ifa`, `ip`를 사용해 아래 구조를 만든다.

| carrier | stp_id | apm_ip |
|---|---|---|
| SKB | stp-001 | 1.2.3.4 |

현재 쿼리는 채널이나 콘텐츠 정보를 결과에 보존하지 않는다. 따라서 “어떤 TV가 어떤 채널을 시청했는지”가 아니라 **어떤 셋톱에서 광고 요청이 발생했고 당시 어떤 IP를 사용했는지**를 나타낸다.

주요 정제 내용:

- `app_bundle`을 이용해 `SKB`, `U+`, `KT`로 통신사 분류
- 셋톱 ID와 IP의 공백 제거 및 소문자화
- IPv4 호환 IPv6 표기의 `::ffff:` 제거
- 빈 ID, 기본 UUID, 비정상·로컬 IP 제거
- 동일한 통신사–셋톱 ID–IP 조합 중복 제거

### 3.2 2단계: NHN IP–모바일 ADID 정규화

원천 테이블은 `prod-ptbwa-dw.nhn_bid_log_flatten`이다.

- `device_ip` → `match_ip`
- `device_ifa` → `mobile_adid`
- `source_name` → `NHN`

공백, 대소문자, `::ffff:` 접두사를 정규화하고 유효하지 않은 값과 동일 IP–ADID 중복을 제거한다. 아직 APM 데이터와 연결하지 않는다.

| source_name | match_ip | mobile_adid |
|---|---|---|
| NHN | 1.2.3.4 | adid-a |

### 3.3 3단계: TG IP–모바일 ADID 정규화

원천 테이블은 `propfit.ptbwa_tg`이다.

- `ip` → `match_ip`
- `uuid` → `mobile_adid`
- `source_name` → `TG`

2단계와 동일한 구조 및 정제 규칙을 적용한다.

| source_name | match_ip | mobile_adid |
|---|---|---|
| TG | 1.2.3.4 | adid-b |

### 3.4 4단계: NHN과 TG 통합

2·3단계에서 동일한 구조로 만든 데이터를 `UNION ALL`로 합친다.

| source_name | match_ip | mobile_adid |
|---|---|---|
| NHN | 1.2.3.4 | adid-a |
| TG | 1.2.3.4 | adid-a |
| TG | 1.2.3.4 | adid-b |

NHN과 TG에 같은 IP–ADID가 있어도 두 행을 유지한다. 이후 양쪽 소스에서 모두 발견된 관계인지 판단하려면 `source_name`이 보존되어야 하기 때문이다.

### 3.5 5단계: 동일 IP 기반 셋톱–모바일 매핑

`apm_pool.apm_ip = mobile_reference.match_ip` 조건으로 연결한다.

입력 예시:

| carrier | stp_id | apm_ip |
|---|---|---|
| SKB | stp-001 | 1.2.3.4 |

| source_name | match_ip | mobile_adid |
|---|---|---|
| NHN | 1.2.3.4 | adid-a |
| TG | 1.2.3.4 | adid-b |
| TG | 5.6.7.8 | adid-c |

결과:

| carrier | stp_id | apm_ip | source_name | mobile_adid |
|---|---|---|---|---|
| SKB | stp-001 | 1.2.3.4 | NHN | adid-a |
| SKB | stp-001 | 1.2.3.4 | TG | adid-b |

`INNER JOIN`이므로 IP가 일치하지 않는 행은 결과에서 제외된다. 한 IP에 여러 ADID가 관측되면 하나의 셋톱에 여러 ADID가 연결될 수 있다.

### 3.6 6단계: 셋톱별 NHN/TG 매핑 플래그

5단계의 상세 결과를 셋톱 한 행으로 압축한다. 해당 소스에서 한 번이라도 매핑됐으면 플래그가 1이다.

| carrier | stp_id | nhn_flag | tg_flag | 의미 |
|---|---|---:|---:|---|
| SKB | stp-001 | 1 | 1 | NHN과 TG 모두 매핑 |
| SKB | stp-002 | 1 | 0 | NHN만 매핑 |
| KT | stp-003 | 0 | 1 | TG만 매핑 |
| U+ | stp-004 | 0 | 0 | 매핑 없음 |

전체 APM 셋톱을 기준으로 `LEFT JOIN`하므로 매핑되지 않은 셋톱도 `0, 0`으로 유지된다.

### 3.7 7단계: 통신사별 APM 모집단

통신사별 고유 셋톱 ID 수와 고유 IP 수를 계산한다.

- `total_apm_ifa`: 전체 고유 셋톱 ID 수
- `total_apm_ip`: 전체 고유 APM IP 수

이 값은 최종 매핑률의 분모다.

```text
셋톱 매핑률 = 매핑 셋톱 수 / 전체 셋톱 수 × 100
IP 매핑률   = 매핑 IP 수 / 전체 IP 수 × 100
```

### 3.8 8단계: IP 기준 매핑 분포

통신사별로 다음을 집계한다.

- `nhn_matched_apm_ip`: NHN에서 ADID가 발견된 APM IP 수
- `tg_matched_apm_ip`: TG에서 ADID가 발견된 APM IP 수
- `union_matched_apm_ip`: NHN 또는 TG 한 곳 이상에서 발견된 APM IP 수

| APM IP | NHN | TG | 통합 포함 여부 |
|---|---:|---:|---:|
| 1.1.1.1 | O | O | O |
| 2.2.2.2 | O | X | O |
| 3.3.3.3 | X | O | O |
| 4.4.4.4 | X | X | X |

위 예시의 NHN IP 수는 2, TG IP 수는 2, 통합 IP 수는 3이다. 양쪽에 등장한 IP도 통합 수에서는 한 번만 센다.

### 3.9 9단계: 셋톱 기준 매핑 분포

6단계 플래그를 사용해 통신사별 셋톱 수를 집계한다.

- NHN 전체 매핑 셋톱
- TG 전체 매핑 셋톱
- NHN과 TG 모두 매핑된 셋톱
- NHN만 매핑된 셋톱
- TG만 매핑된 셋톱
- NHN 또는 TG 한 곳 이상에서 매핑된 셋톱

```text
NHN 매핑 = NHN 단독 + 양쪽 중복
TG 매핑  = TG 단독 + 양쪽 중복
통합 매핑 = NHN 단독 + TG 단독 + 양쪽 중복
```

### 3.10 10단계: 고유 모바일 ADID 분포

5단계에서 셋톱과 연결된 고유 모바일 ADID를 통신사별로 센다.

- `nhn_mobile_adid_count`: NHN에서 확보한 고유 ADID 수
- `tg_mobile_adid_count`: TG에서 확보한 고유 ADID 수
- `final_mobile_adid_count`: 두 소스를 합친 고유 ADID 수

하나의 ADID가 여러 셋톱과 연결되어도 고유 ADID 수에서는 한 번만 계산된다. 따라서 이 값은 셋톱–ADID 관계 수가 아니다.

### 3.11 11단계: 최종 요약

7~10단계 결과를 `carrier` 기준으로 결합하여 다음을 출력한다.

- APM 전체 셋톱·IP 모집단
- NHN 및 TG의 IP·셋톱 매핑 수와 매핑률
- NHN/TG 단독·중복 셋톱 수
- 통합 매핑 수와 매핑률
- 확보한 고유 모바일 ADID 수
- ADID를 더 많이 제공한 소스

`dominant_mobile_source`의 의미:

| 값 | 의미 |
|---|---|
| `NHN` | NHN 고유 ADID 수가 더 많음 |
| `TG` | TG 고유 ADID 수가 더 많음 |
| `NO_MATCH` | 두 소스 모두 매핑 결과 없음 |
| `SIMILAR` | 두 소스의 고유 ADID 수가 같음 |

## 4. 해석 시 주의사항

1. 동일 IP는 동일 사용자나 동일 가구를 보장하지 않는다.
2. 공용 Wi-Fi, 통신사 NAT, 유동 IP 때문에 관계없는 기기가 연결될 수 있다.
3. 현재 쿼리는 8·9월 기간 내 IP가 한 번이라도 같으면 연결하므로 관측 시점 차이를 고려하지 않는다.
4. 하나의 IP에 여러 셋톱 또는 여러 모바일 ADID가 있으면 다대다 관계가 만들어질 수 있다.
5. APM 로그는 시청 로그 자체가 아니라 광고 입찰 요청 로그이므로 광고 요청이 없었던 시청은 모집단에 들어오지 않을 수 있다.
6. 운영 매핑으로 사용하려면 일자·시간 근접도, 반복 관측 횟수, IP별 연결 기기 수 등을 이용한 신뢰도 규칙을 추가하는 것이 안전하다.

## 5. 관련 SQL

- 매핑 테이블 생성: `mapping/querys/01_create_stp_mobile_ip_mapping_2026_08_09.sql`
- 매핑 테이블 기반 리포트: `mapping/querys/02_stp_mobile_ip_mapping_report.sql`
- 전체 1~11단계 참고용 SQL: `mapping/querys/stp_mobile_ip_mapping_2026_08_09.sql`
