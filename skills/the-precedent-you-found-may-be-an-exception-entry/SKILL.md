---
name: the-precedent-you-found-may-be-an-exception-entry
description: 기존 코드가 X 를 하고 있다고 해서 X 가 허용된 패턴인 건 아니다 — 그 줄이 **예외 목록에 등록된 위반**일 수 있다. 호출 지점에서는 선례와 예외가 **똑같이 생겼다**: 둘 다 그냥 도는 코드다. 차이는 아키텍처 게이트의 설정 파일에만 있다. 설계를 선례 위에 세우기 전에, 그 선례가 `ignore_imports` · `noqa` · allowlist · `# type: ignore` 에 이름이 올라가 있는지 **먼저 확인하라.** 트리거 - "이미 이렇게 하는 데가 있으니 따라 하면 된다", 레이어 경계를 넘는 임포트, 새 모듈이 다른 컨텍스트를 참조, 계약 게이트(import-linter·ruff·mypy)가 있는 저장소.
version: 1.0.0
task_types: [design, implementation, investigation]
triggers:
  - pattern: "기존 코드에서 '선례'를 찾아 그 위에 설계를 세우려 할 때"
  - pattern: "레이어/컨텍스트 경계를 넘는 임포트를 추가하기 직전"
  - pattern: "'A 도 B 를 임포트하니까 나도 해도 된다'는 추론"
  - pattern: "import-linter / ruff noqa / mypy ignore 가 있는 저장소에서 새 배선"
category: trap
---

# 선례처럼 보이는 것이 예외 등록일 수 있다

## Problem

MCP 툴과 REST 라우트가 같은 규칙을 공유해야 했다. 규칙을 어디에 둘지 정하려고
저장소를 뒤졌더니 이런 게 나왔다:

```python
# backend/mcp/tools/run_routing_rules_tools.py
from backend.api.v1.run_routing import (
    ApplyError, apply_proposals, compile_for_workspace, ...
)
```

읽은 대로 결론을 냈다 — *"`backend.mcp` 가 `backend.api` 에서 공유 규칙을
가져오는 건 이 저장소의 sanctioned 패턴이다."* 그 위에 서비스 두 개를 추출하고,
라우트 두 개를 얇은 어댑터로 다시 쓰고, MCP 툴 네 개를 배선했다. 테스트는 전부
green 이었다.

`lint-imports` 를 돌리자:

```
MCP context depends only on Identity + Workflow + Knowledge + common  BROKEN
backend.mcp is not allowed to import backend.api
```

계약 주석은 **왜** 금지인지까지 적어두고 있었다 — *"그러면 MCP 툴이 REST 표면은
넘지 않는 경계를 넘게 된다."* 내가 선례로 읽은 그 줄은 `ignore_imports` 에
이름이 올라간 **등록된 위반**이었다.

## 왜 놓치기 쉬운가

**호출 지점에서 선례와 예외는 구분이 안 된다.** 둘 다 그냥 도는 코드고, 둘 다
테스트를 통과하고, 둘 다 프로덕션에 있다. 차이는 오직 **다른 파일**(게이트의
설정)에만 존재한다:

| 기제 | 예외가 등록되는 곳 |
|---|---|
| import-linter | `pyproject.toml` 의 `ignore_imports` |
| ruff | 그 줄의 `# noqa: RULE` |
| mypy | `# type: ignore` · `[[tool.mypy.overrides]]` |
| 커스텀 가드 테스트 | `_KNOWN_GAPS` · `_ALLOWED` · `EXEMPT` 같은 집합 |

`grep` 로 찾은 코드는 예외 표시를 **같이 보여주지 않는다.** 특히 `ignore_imports`
처럼 예외가 **다른 파일**에 있으면 그 줄만 봐서는 영영 알 수 없다.

그리고 이 오독의 비용은 뒤로 갈수록 커진다 — 잘못된 선례 위에 세운 설계는
게이트가 돌 때까지 살아 있고, 그때는 이미 여러 파일을 고쳐놓은 뒤다.

## 처방

### 1. 선례를 채택하기 전에 예외 목록을 먼저 grep 하라

```bash
# import-linter
grep -n "ignore_imports" -A60 pyproject.toml | grep "<모듈 경로>"

# 그 줄 자체의 억제 표시
sed -n '<line>p' <file> | grep -E "noqa|type: ignore"
```

한 줄이면 끝난다. 설계를 세우기 **전에** 하는 게 요점이다.

### 2. 계약을 읽어라 — 예외가 아니라 **규칙**을

허용 목록이 있는 게이트는 대개 **왜**를 주석으로 적어둔다. 그 문장이 설계를
직접 정해준다. 위 사례에서 계약은 `backend.mcp` 가 무엇을 임포트해도 되는지
(Identity · Workflow · Knowledge · common) 를 그대로 알려줬고, 그게 규칙의
올바른 집이었다.

### 3. 게이트를 설계 직후·구현 직전에 한 번 돌려라

계약 게이트는 보통 CI 후반이나 전체 스위트에서 돈다. 배선을 시작하기 전에
**가짜 임포트 한 줄**로 게이트를 먼저 때려보면, 다섯 파일을 고친 뒤가 아니라
30초 만에 답이 나온다.

```bash
# 이 임포트가 허용되나? 를 30초에 묻는 법
echo "import backend.api.v1.deliverables" >> backend/mcp/tools/_probe.py
lint-imports; rm backend/mcp/tools/_probe.py
```

### 4. 예외가 진짜 필요하면, **왜**를 적고 좁게 잡아라

기존 예외들은 전부 이유를 달고 있었다 — *"암호화 로직의 두 번째 복사본을
만들지 않기 위해"*. 새 예외를 추가할 땐 같은 기준을 넘겨라: **복제가 더 나쁜가?**
아니면 규칙을 허용된 층으로 옮기는 게 답이다.

## 신호

- "이미 이렇게 하는 데가 있다" 로 시작하는 설계 근거
- 컨텍스트/레이어 이름이 다른 두 패키지 사이의 임포트
- 그 임포트를 하는 파일이 **한두 개뿐**일 때 (진짜 패턴이면 더 많다)
- 함수 안에 숨은 lazy import (`# noqa: PLC0415`) — import-linter 는 **이것도 본다**

## 관련

- `mirrored-surface-drifts-in-the-direction-of-least-testing` — 두 표면의 규칙을
  공유해야 하는 이유. 이 스킬은 *어디에* 공유하느냐를 정한다.
- `import-linter-sees-function-level-imports` — lazy import 로는 못 피한다.
- `absence-guard-listing-spellings-proves-only-imagination` — 예외 목록을
  fail-closed 로 유지하는 법.
