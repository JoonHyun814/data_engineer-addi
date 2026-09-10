# 셋톱–모바일 IP 매핑 리포트 컬럼 설명

대상 쿼리: `mapping/querys/02_stp_mobile_ip_mapping_report.sql`

| 컬럼명 | 설명 |
|---|---|
| `carrier` | 셋톱 통신사 (`SKB`, `U+`, `KT`) |
| `total_apm_stp_count` | APM에서 관측된 전체 고유 셋톱 수 |
| `matched_stp_count` | NHN 또는 TG에서 한 번 이상 매핑된 셋톱 수 |
| `unmatched_stp_count` | NHN과 TG 어디에서도 매핑되지 않은 셋톱 수 |
| `stp_mapping_rate_pct` | 전체 셋톱 대비 통합 매핑 셋톱 비율 |
| `total_apm_ip_count` | APM에서 관측된 전체 고유 IP 수 |
| `matched_ip_count` | NHN 또는 TG에서 매핑된 고유 IP 수 |
| `unmatched_ip_count` | NHN과 TG 어디에서도 매핑되지 않은 고유 IP 수 |
| `ip_mapping_rate_pct` | 전체 APM IP 대비 통합 매핑 IP 비율 |
| `nhn_matched_stp_count` | NHN을 통해 매핑된 셋톱 수 |
| `nhn_stp_mapping_rate_pct` | 전체 셋톱 대비 NHN 매핑 셋톱 비율 |
| `nhn_matched_ip_count` | NHN에서 매핑된 APM IP 수 |
| `nhn_ip_mapping_rate_pct` | 전체 APM IP 대비 NHN 매핑 IP 비율 |
| `nhn_mobile_adid_count` | NHN을 통해 확보한 고유 모바일 ADID 수 |
| `tg_matched_stp_count` | TG를 통해 매핑된 셋톱 수 |
| `tg_stp_mapping_rate_pct` | 전체 셋톱 대비 TG 매핑 셋톱 비율 |
| `tg_matched_ip_count` | TG에서 매핑된 APM IP 수 |
| `tg_ip_mapping_rate_pct` | 전체 APM IP 대비 TG 매핑 IP 비율 |
| `tg_mobile_adid_count` | TG를 통해 확보한 고유 모바일 ADID 수 |
| `both_matched_stp_count` | NHN과 TG 양쪽에서 모두 매핑된 셋톱 수 |
| `nhn_only_stp_count` | NHN에서만 매핑된 셋톱 수 |
| `tg_only_stp_count` | TG에서만 매핑된 셋톱 수 |
| `final_mobile_adid_count` | NHN과 TG를 합쳐 중복 제거한 모바일 ADID 수 |
| `matched_mapping_row_count` | `ad_id`가 존재하는 상세 매핑 관계 행 수 |
| `total_table_row_count` | 매핑 성공·실패를 모두 포함한 테이블 전체 행 수 |
| `dominant_mobile_source` | 더 많은 고유 ADID를 제공한 소스 (`NHN`, `TG`, `SIMILAR`, `NO_MATCH`) |

## 주요 계산 관계

```text
total_apm_stp_count
= matched_stp_count + unmatched_stp_count

stp_mapping_rate_pct
= matched_stp_count / total_apm_stp_count × 100

total_apm_ip_count
= matched_ip_count + unmatched_ip_count

ip_mapping_rate_pct
= matched_ip_count / total_apm_ip_count × 100

matched_stp_count
= nhn_only_stp_count
  + tg_only_stp_count
  + both_matched_stp_count
```

## 해석 시 주의사항

- 셋톱에 여러 IP가 있더라도 하나의 IP에서 ADID가 발견되면 해당 셋톱은 매핑 성공으로 계산한다.
- `nhn_matched_stp_count`와 `tg_matched_stp_count`에는 양쪽 소스에서 모두 매핑된 셋톱이 각각 포함된다.
- `final_mobile_adid_count`는 NHN과 TG 사이의 중복 ADID를 제거한 값이다.
- `matched_mapping_row_count`와 `total_table_row_count`는 셋톱 수가 아니다.
- 하나의 셋톱–IP에 여러 ADID가 연결되면 상세 매핑 행이 여러 개 생성될 수 있다.
