# weather_codes_update

Athena의 weather 데이터(forecast/fine_dust/uv/special_alert)에서 region별 최신 `weather_code`를 계산해 RDS `area_weather_codes` 테이블을 매 실행마다 통째로(`TRUNCATE` 후 재삽입) 갱신한다. 모든 카테고리를 매번 처음부터 다시 계산하며, 이전 DB 상태와 diff하지 않는다.

## forecast / fine_dust / uv

각 테이블에서 `region_id`별로 `dt, hr` 기준 최신 파티션 1건만 가져와(`ROW_NUMBER() ... ORDER BY dt DESC, hr DESC`) 그 시점의 `weather_code`를 그대로 채택한다. 단순 "최신 스냅샷" 방식.

## special_alert(B001_005) 현재 상태 계산

`weather_special_alert` 람다가 적재하는 raw 테이블은 "현재 상태" 테이블이 아니라 중복 제거된 append-only 이벤트 로그다. 그래서 위 세 카테고리처럼 단순히 최신 파티션을 보는 게 아니라, **dt 필터 없이 전체 이력을 스캔**해서 현재 발효 중인 특보를 매번 다시 계산한다(`ATHENA_QUERIES["special_alert"]`). dt로 윈도우를 좁히면 건조/한파처럼 며칠씩 지속되는 특보가 윈도우 밖으로 밀려나 누락될 수 있어서 전체 스캔이 필수다.

쿼리는 3단계로 좁혀간다:

1. **버전 선택** — 같은 이벤트(`stnId + areaCode + warnVar + tmFc + tmSeq`)가 raw 로그에 여러 번 적재돼 있을 수 있다(예: `cancel` 0→1 정정). `fetched_at` 기준 가장 최근에 수집된 버전 하나만 채택해 그 이벤트의 최종 상태를 확정한다.
2. **취소 제외** — 채택된 버전이 `cancel = '1'`이면 그 발표 자체가 없었던 것으로 간주하고 버린다.
3. **최신 발표 선택** — 남은 버전들 중 `(stnId, areaCode, warnVar)`별로 `tmFc, tmSeq`가 가장 큰(가장 최근 발표/연장/해제) 한 건만 가져온다.

이 결과를 `collect_special_alert_codes`에서 Python으로 가공한다:

- `warnVar`(숫자 코드) → 한글 라벨(`WARN_VAR_LABELS`) → `B001_005_xxx`(`WEATHER_CODE_MAP`)로 매핑. 풍랑/폭풍해일/열대야처럼 아직 코드가 배정되지 않은 종류는 매핑이 없으므로 스킵한다.
- `command`가 해제(`2`)·변경해제(`8`)면 "해제", 그 외(발표/연장/정정/변경발표)면 "활성"으로 분류(`LIFT_COMMANDS`).
- `stnId`는 `regions.csv`(`load_stn_to_region_ids`)를 통해 여러 `region_id`로 펼쳐지고, 각 `region_id`는 RDS `regions` 테이블로 `region_code`까지 변환된다(`build_region_code_resolver`). 특보는 stnId 단위로 발표되지만 한 관측소에 여러 region이 매핑될 수 있어서다.

같은 관측소(`stnId`) 아래 여러 `areaCode`가 있을 수 있어, 한쪽은 발표 중·다른 쪽은 해제 상태인 경우가 생길 수 있다. 결과가 행 처리 순서에 좌우되지 않도록, 모든 행을 먼저 `active`/`lifted` 두 집합에 모아두고 마지막에 한 번에 병합한다:

```python
active -= (lifted - active)
```

즉 "그 관측소 산하 어느 한 구역이라도 발표 중이면 활성"이 최종 규칙이다.

## 최종 적재

forecast/fine_dust/uv/special_alert 결과를 모두 합친 `(region_code, weather_code)` 목록으로 `area_weather_codes`를 `TRUNCATE` 후 전체 재삽입한다(`save_weather_data`).
