# weather_special_alert

기상청 기상특보 발표현황 조회 API(`getPwnCd`)를 3시간 주기로 호출해, 응답을 가공 없이 raw 그대로 S3(`prod/weather/special_alert/dt=*/hr=*/`)에 적재한다. 현재 발효 중인 특보 상태 계산은 이 raw 데이터를 읽는 `lambda/weather_codes_update`에서 수행한다.

## stnId로 지역을 필터링하지 않는 이유

`getPwnCd` 요청에 `stnId`를 region별로 넣어 호출 범위를 좁히는 시도를 했었으나, 실측 결과(2026-06-23) **응답의 `stnId`는 전국 어디든 항상 `"108"` 고정값**이라는 게 확인됐다 — 포천시(육상 호우)부터 제주(강풍)까지 지역과 무관하게 전부 `108`. `regions.csv`의 `stn_id`(105/109/131…)는 이 값과 전혀 매칭되지 않아, 그 값으로 필터링하면 항상 0건만 나온다.

실제 지역 구분은 응답의 `areaCode`(특보구역코드, 예: `L1011300`=포천시)로만 가능하다. 그래서 이 람다는 지역 필터링/조인을 하지 않고 `fetch_all_alerts`로 **전국 단위 응답을 그대로 raw 적재**한다(원래 의도였던 "raw 데이터 모두 적재"와 일치). areaCode 기준 region 연결은 `weather_codes_update`가 별도 매핑 CSV(`weather/match_area_codes.py`로 생성, S3 `prod/weather/regions_area_code/regions_area_code.csv`)를 읽어서 처리한다.

## 조회기간

3시간 주기 자동 실행(스텝펑션, event 없음)에서는 매번 "오늘 - 1일 ~ 오늘"로 겹치게 조회한다(`LOOKBACK_DAYS = 1`, `resolve_date_range`). 한 번 실행이 누락돼도 다음 실행에서 재확보되도록 하기 위한 의도된 오버랩이며, 이 기본 동작은 그대로 유지된다.

수동 실행(예: 누락분 백필) 시에는 Lambda 테스트 이벤트로 기간을 직접 지정할 수 있다:
- `{"lookbackDays": 3}` — "오늘 - N일 ~ 오늘"로 기간 길이만 조정
- `{"fromTmFc": "20260601", "toTmFc": "20260610"}` — 기간을 완전히 직접 지정 (API 제약상 오늘로부터 최대 6일 전까지만 조회 가능)

## 중복 처리

조회 구간을 매번 겹치게 잡거나 수동으로 같은 기간을 다시 조회해도, 같은 이벤트가 여러 번 응답에 나타날 수 있다.

- 이벤트를 식별하는 고정 필드 묶음(`stnId, areaCode, warnVar, warnStress, command, cancel, tmFc, tmSeq`)만 모아 SHA-256 해시를 만든다. `fetched_at` 등 매번 달라지는 부가 필드는 해시에서 제외한다(`HASH_FIELDS`, `item_hash`).
- S3 상태 파일(`state/seen.json`)에 "해시 → 최초 수집일"을 들고 다니며, 이미 본 해시면 스킵하고 새 해시만 저장한다.
- 같은 이벤트라도 상태가 바뀌면(예: `cancel` 0→1 정정, `command`가 연장→해제로 변경) 해시가 달라지므로 새 레코드로 추가 적재된다 — 덮어쓰기가 아니라 그 이벤트의 변경 이력이 쌓이는 append-only 로그.
- API가 애초에 6일보다 과거는 조회할 수 없으므로(`fromTmFc` 제약), 그보다 여유 있는 `RETENTION_DAYS = 8`이 지난 해시는 매 실행 끝에 정리해 상태 파일이 무한정 커지지 않도록 한다(`prune_seen`).

## 페이지네이션

`getPwnCd`는 `numOfRows`/`pageNo`로 페이징되며 응답에 `totalCount`가 함께 온다. `fetch_all_alerts`는 `numOfRows=100`으로 `pageNo`를 1부터 증가시키며 호출을 반복해, **누적 아이템 수가 `totalCount` 이상이 되거나 응답이 비어있을 때** 멈춘다. 조회 구간 내 결과가 100건을 넘어도 빠짐없이 전부 가져온다.

## 현재 상태 계산은 여기서 하지 않음

이 람다는 raw 이벤트를 적재만 하고, "지금 어떤 특보가 발효 중인지" 판단은 하지 않는다. 그 계산은 raw 로그를 areaCode 기준으로 읽어 region에 연결하는 `lambda/weather_codes_update`의 역할이다(해당 폴더 `README.md` 참고).

## 파티션 등록

새 데이터를 S3에 쓴 직후 `register_partition`이 Glue Catalog에 그 `dt/hr` 파티션 하나만 직접 등록한다(`glue.get_table`로 테이블의 StorageDescriptor를 그대로 가져와 Location만 바꿔 `create_partition` 호출). `MSCK REPAIR TABLE`처럼 전체 S3 트리를 매번 훑지 않아도 되고, 등록 비용이 파티션 총량과 무관하게 항상 O(1)이다.

이제 MSCK 백업이 없으므로, 등록이 실패하면(권한 문제 등) 예외를 다시 던져 람다 실행 자체를 실패로 표시한다. S3 적재는 이미 끝난 뒤라 데이터는 안전하지만, 실패를 조용히 삼키면 그 파티션이 조회에서 계속 빠진 채로 남아 `area_weather_codes`가 모르게 stale해질 수 있어서다 — CloudWatch에서 람다 실패로 바로 드러나야 한다.
