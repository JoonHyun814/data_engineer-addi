# addi

애디(광고 전환/유입) 데이터를 수집·적재·집계하는 AWS 기반 데이터 파이프라인. RDS/외부 API → Lambda/Glue → S3/Athena → RDS 순으로 데이터를 옮기고, Step Function으로 오케스트레이션한다.

- `lambda/` — 개별 Lambda 함수 (수집, 동기화, 코드 계산 등). 폴더명 = 함수명.
- `glue/` — Glue Job 스크립트 (Athena/S3 ↔ RDS 이관).
- `athena_querys/` — Athena에서 실행하는 조회/집계 SQL.
- `rds_query/` — RDS 테이블 생성 등 DDL.
- `stepfunction/` — Step Functions 정의 및 IAM 정책 JSON.
- `datas/` — 로컬 참조용 데이터 파일(gitignore 대상, 커밋하지 않음).
- `stepfunction_resource_map.csv` — 모든 Step Function(addi, abi 포함)이 서로 어떤 상위/하위 Step Function, Lambda, Glue Job/Workflow, IAM 정책 파일과 연결되어 있는지 정리한 표. 리소스 관계를 파악할 땐 이 파일부터 확인한다.

## stepfunction_resource_map.csv 동기화

Step Function을 새로 추가하거나, 기존 Step Function이 호출하는 Lambda/Glue Job/하위 Step Function/IAM 정책이 바뀌는 변경(교체, 추가, 삭제)을 할 때마다 `stepfunction_resource_map.csv`도 같이 업데이트한다. 코드만 바꾸고 이 표를 갱신하지 않으면 표가 실제 배포 상태와 어긋나므로, 관련 변경을 담은 커밋에 표 수정도 함께 포함시킨다.

## 커밋 컨벤션

`<type>: <설명>` 형식, 설명은 한글로 작성.

- `feat`: 새로운 기능/쿼리/람다 추가
- `fix`: 버그 수정
- `chore`: 설정, gitignore 등 잡무성 변경
- `refactor`: 동작 변화 없는 구조 개선
- `docs`: 문서(README 등)만 변경

특정 리소스(람다/글루/쿼리)에 한정된 변경은 `이름: 설명` 형식도 허용한다 (예: `weather_codes_update: 코드 매핑 추가`). 하나의 커밋은 하나의 논리적 변경만 담는다 — 관련 없는 변경은 커밋을 분리한다.

## 코드 컨벤션

- Lambda 진입점 파일명은 `lambda_function.py`, 핸들러는 `lambda_handler`.
- 각 Lambda/Glue 폴더에 필요한 IAM 정책은 `iam_policy.json`으로 같이 둔다.
- 코드 주석과 문서(README)는 한글로, *무엇을* 하는지가 아니라 *왜* 그렇게 했는지(비직관적인 제약, 실측으로 확인한 API 동작 등)를 적는다.
- Athena SQL은 대문자 키워드, 스네이크_케이스 컬럼/별칭을 사용한다.
- 시간대는 KST(UTC+9) 기준으로 다루고, 코드에서 `timezone(timedelta(hours=9))`로 명시한다.
- `datas/`, `.env`, `__pycache__`, `.claude`는 커밋하지 않는다.
