# weather_codes_update

Athena의 weather 데이터(forecast/fine_dust/uv/special_alert)에서 region별 최신 `weather_code`를 계산해 RDS `area_weather_codes` 테이블을 매 실행마다 통째로(`TRUNCATE` 후 재삽입) 갱신한다. 모든 카테고리를 매번 처음부터 다시 계산하며, 이전 DB 상태와 diff하지 않는다.

## forecast / fine_dust / uv

각 테이블에서 `region_id`별로 `dt, hr` 기준 최신 파티션 1건만 가져와(`ROW_NUMBER() ... ORDER BY dt DESC, hr DESC`) 그 시점의 `weather_code`를 그대로 채택한다. 단순 "최신 스냅샷" 방식.

## special_alert(B001_005) 현재 상태 계산

`getPwnCd` 응답의 `stnId`는 지역과 무관하게 전국 어디든 항상 `"108"` 고정값으로 내려온다(실측 확인, 2026-06-23). 그래서 region 매핑은 `stnId`가 아니라 `areaCode`(특보구역코드)로 한다. `areaCode → region_id` 매핑은 기상청 "특보구역코드 안내" 엑셀의 `REG_UP` 계층을 따라 만든 별도 CSV(`weather/match_area_codes.py`로 생성, S3 `prod/weather/regions_area_code/regions_area_code.csv`)를 `load_area_code_to_region_id`가 읽어온다. 해상구역(`S-`) 등 region이 없는 areaCode는 이 매핑에 없으므로 자동으로 스킵된다.

`weather_special_alert` 람다가 적재하는 raw 테이블은 "현재 상태" 테이블이 아니라 중복 제거된 append-only 이벤트 로그다. 그래서 위 세 카테고리처럼 단순히 최신 파티션을 보는 게 아니라, **dt 필터 없이 전체 이력을 스캔**해서 현재 발효 중인 특보를 매번 다시 계산한다(`ATHENA_QUERIES["special_alert"]`). dt로 윈도우를 좁히면 건조/한파처럼 며칠씩 지속되는 특보가 윈도우 밖으로 밀려나 누락될 수 있어서 전체 스캔이 필수다.

쿼리는 3단계로 좁혀간다:

1. **버전 선택** — 같은 이벤트(`areaCode + warnVar + tmFc + tmSeq`)가 raw 로그에 여러 번 적재돼 있을 수 있다(예: `cancel` 0→1 정정). `fetched_at` 기준 가장 최근에 수집된 버전 하나만 채택해 그 이벤트의 최종 상태를 확정한다.
2. **취소 제외** — 채택된 버전이 `cancel = '1'`이면 그 발표 자체가 없었던 것으로 간주하고 버린다.
3. **최신 발표 선택** — 남은 버전들 중 `(areaCode, warnVar)`별로 `tmFc, tmSeq`가 가장 큰(가장 최근 발표/연장/해제) 한 건만 가져온다.

이 결과를 `collect_special_alert_codes`에서 Python으로 가공한다:

- `warnVar`(숫자 코드) → 한글 라벨(`WARN_VAR_LABELS`) → `B001_005_xxx`(`WEATHER_CODE_MAP`)로 매핑. 풍랑/폭풍해일/열대야처럼 아직 코드가 배정되지 않은 종류는 매핑이 없으므로 스킵한다.
- `command`가 해제(`2`)·변경해제(`8`)면 "해제", 그 외(발표/연장/정정/변경발표)면 "활성"으로 분류(`LIFT_COMMANDS`).
- `areaCode`는 `area_code_to_region_id`로 `region_id`가 되고, 그 `region_id`는 RDS `regions` 테이블로 `region_code`까지 변환된다(`build_region_code_resolver`).

같은 region 아래 여러 `areaCode`가 있을 수 있어(예: 경기도 산하 시군구 다수), 한쪽은 발표 중·다른 쪽은 해제 상태인 경우가 생길 수 있다. 결과가 행 처리 순서에 좌우되지 않도록, 모든 행을 먼저 `active`/`lifted` 두 집합에 모아두고 마지막에 한 번에 병합한다:

```python
active -= (lifted - active)
```

즉 "그 region 산하 어느 한 구역이라도 발표 중이면 활성"이 최종 규칙이다.

## 최종 적재

forecast/fine_dust/uv/special_alert 결과를 모두 합친 `(region_code, weather_code)` 목록으로 `area_weather_codes`를 `TRUNCATE` 후 전체 재삽입한다(`save_weather_data`).

## 파티션 디스커버리는 여기서 하지 않음

과거에는 이 람다가 매 실행마다 4개 테이블에 `MSCK REPAIR TABLE`을 돌려 새 파티션을 등록했다. 파티션 수가 쌓일수록 S3 전체를 훑는 이 작업이 점점 느려지는 구조라, 각 적재 람다(`weather_fcst`/`weather_fine_dust`/`weather_uv`/`weather_special_alert`)가 적재 시점에 자기가 쓴 파티션 하나만 Glue Catalog에 직접 등록하는 방식으로 옮겼다(각 람다의 `register_partition` 참고). 그래서 이 람다는 Athena 쿼리만 수행하고 파티션 등록은 더 이상 신경 쓰지 않는다.
