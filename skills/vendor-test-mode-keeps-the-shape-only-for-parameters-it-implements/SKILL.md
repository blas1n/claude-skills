---
name: vendor-test-mode-keeps-the-shape-only-for-parameters-it-implements
description: 벤더의 "테스트 데이터 모드는 실제 응답 형태에 플레이스홀더 값"이라는 약속은 **파라미터별로** 깨진다 — 구현 안 된 파라미터(group_by_map 등)는 조용히 무시되고 다른 형태(flat)가 온다. 문서 형태로 짠 정규화기는 크래시 대신 **틀린 키를 데이터로 해석**한다. 트리거 - sandbox/test-data/example 모드로 개발, 응답 구조를 바꾸는 파라미터(group_by, expand, include), 정규화기가 dict 키를 순회, 첫 E2E 에서 이상한 카테고리 이름이 데이터에 섞여 있을 때.
version: 1.0.0
task_types: [integration, testing]
triggers:
  - pattern: "벤더 테스트 모드·샌드박스로 수집기/클라이언트를 개발"
  - pattern: "응답 형태를 바꾸는 쿼리 파라미터에 의존하는 파서"
  - pattern: "E2E 결과에 'data', 'items', 'result' 같은 키 이름이 값으로 나타남"
category: trap
---

# 테스트 모드는 구현된 파라미터의 형태만 지킨다

## Problem

- 증상: Heroes Profile API 테스트 모드는 "실제 형태 + 플레이스홀더 값, 무과금"을 약속했다. `group_by_map=true` 를 보냈는데 맵별 키 구조가 아닌 **flat** `{average_*, data:[5 rows]}` 가 왔다. 문서 형태(`{map: {data:[...]}}`)로 짠 정규화기는 최상위 키를 순회하다 `"data"` 를 **맵 이름으로** 읽어 `map:"data"` 행 5개 + 파생 `all` 5개를 만들었다. 크래시 없음, exit 0, 파일도 정상 — 값만 틀렸다.
- 근본 원인: 샌드박스는 엔드포인트 단위로 고정 예시를 돌려주고, 구조를 바꾸는 파라미터는 구현되지 않았다. "형태를 지킨다"는 약속은 기본 호출 형태에만 참이다.
- 흔한 오해: 테스트 모드 200 = 계약 검증 완료. 실제로는 **내가 쓰는 파라미터 하나하나**에 대해 형태를 다시 봐야 한다.

## Solution

1. 샌드박스 응답을 **파라미터 조합마다** 저장하고 최상위 키를 눈으로 확인한다(`raw_*.json.gz` 를 남겨라).
2. 정규화기는 **형태를 판별하고 나서** 순회한다: "최상위에 `data` 리스트가 있으면 flat", "맵 이름 집합과 교차하면 per-map". 판별 불가면 `ValueError`, 판별되면 **경고 로그**(`normalize.flat_payload`)를 남겨 라이브에서 눈에 띄게.
3. 파서 유닛 테스트에 flat 케이스와 per-map 케이스를 **둘 다** 둔다. 픽스처는 문서 형태와 샌드박스 실측 형태 두 벌.
4. 라이브 첫 실행은 "성공/실패"가 아니라 **형태 로그**를 본다 — 어느 경로가 처음 실전을 탔는지.

```python
if isinstance(raw, dict) and isinstance(raw.get("data"), list):   # flat: group_by 무시됨
    log.warning("normalize.flat_payload", key=key, rows=len(raw["data"]))
    return rows_as_all(raw["data"])
payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw   # per-map
```

## Key Insights

- 구조를 바꾸는 파라미터는 샌드박스에서 **가장 먼저 무시되는** 종류다(비용이 크니까). 값 파라미터(필터)보다 훨씬 의심해야 한다.
- dict 키를 데이터(맵·카테고리 이름)로 해석하는 파서는 형태가 어긋나도 **절대 죽지 않는다** — 그래서 판별 단계가 없으면 틀린 데이터가 성공으로 배포된다([[unit-test-supplies-what-production-withholds]] 의 반대 방향: 프로덕션이 안 주는 걸 테스트가 준 게 아니라, 샌드박스가 다른 걸 줬는데 파서가 받아들였다).
- 무과금 모드에서 5분짜리 E2E 를 두 번 돌리는 비용이, 라이브에서 틀린 형태를 하루치 커밋하는 비용보다 싸다.

## Red Flags

- E2E 결과의 카테고리/맵/키 열에 `data`, `items`, `results`, `average_*` 같은 **응답 구조어**가 섞여 있다
- 테스트 모드 응답 행 수가 파라미터와 무관하게 항상 같다(5개 고정)
- 문서에 "test data has the correct shape" 라고만 적혀 있고 파라미터별 언급이 없다
- 정규화기에 형태 판별 분기가 없고 바로 `for k, v in raw.items()` 다
