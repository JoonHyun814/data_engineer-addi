# weather_special_alert

기상청 기상특보 발표현황 조회 API(`getPwnCd`)를 3시간 주기로 호출해, 응답을 가공 없이 raw 그대로 S3(`prod/weather/special_alert/dt=*/hr=*/`)에 적재한다. 현재 발효 중인 특보 상태 계산은 이 raw 데이터를 읽는 `lambda/weather_codes_update`에서 수행한다.

## 중복 처리

3시간 주기로 실행되지만 조회 구간은 매번 "오늘 - 1일 ~ 오늘"로 겹치게 잡는다(`LOOKBACK_DAYS = 1`). 한 번 실행이 누락돼도 다음 실행에서 재확보되도록 하기 위한 의도된 오버랩이라, 같은 이벤트가 여러 실행에 걸쳐 응답에 반복적으로 나타난다.

- 이벤트를 식별하는 고정 필드 묶음(`stnId, areaCode, warnVar, warnStress, command, cancel, tmFc, tmSeq`)만 모아 SHA-256 해시를 만든다. `fetched_at` 등 매번 달라지는 부가 필드는 해시에서 제외한다(`HASH_FIELDS`, `item_hash`).
- S3 상태 파일(`state/seen.json`)에 "해시 → 최초 수집일"을 들고 다니며, 이미 본 해시면 스킵하고 새 해시만 저장한다.
- 같은 이벤트라도 상태가 바뀌면(예: `cancel` 0→1 정정, `command`가 연장→해제로 변경) 해시가 달라지므로 새 레코드로 추가 적재된다 — 덮어쓰기가 아니라 그 이벤트의 변경 이력이 쌓이는 append-only 로그.
- API가 애초에 6일보다 과거는 조회할 수 없으므로(`fromTmFc` 제약), 그보다 여유 있는 `RETENTION_DAYS = 8`이 지난 해시는 매 실행 끝에 정리해 상태 파일이 무한정 커지지 않도록 한다(`prune_seen`).

## 페이지네이션

`getPwnCd`는 `numOfRows`/`pageNo`로 페이징되며 응답에 `totalCount`가 함께 온다. `fetch_all_alerts`는 `numOfRows=100`으로 `pageNo`를 1부터 증가시키며 호출을 반복해, **누적 아이템 수가 `totalCount` 이상이 되거나 응답이 비어있을 때** 멈춘다. 조회 구간 내 결과가 100건을 넘어도 빠짐없이 전부 가져온다.

## 현재 상태 계산은 여기서 하지 않음

이 람다는 raw 이벤트를 적재만 하고, "지금 어떤 특보가 발효 중인지" 판단은 하지 않는다. 그 계산은 raw 로그 전체를 다시 스캔해 현재 상태를 매번 재계산하는 `lambda/weather_codes_update`의 역할이다(해당 폴더 코드의 `ATHENA_QUERIES["special_alert"]`, `collect_special_alert_codes` 참고).
