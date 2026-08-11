---
name: import-linter-sees-function-level-imports
description: import-linter(및 대부분의 정적 아키텍처 게이트)는 AST 를 읽으므로 **함수 안 지연 import 도 계약 위반으로 잡는다**. 순환 import 를 피하려고 import 를 함수 안으로 옮기는 흔한 처방이 아키텍처 계약에는 통하지 않는다. 처방은 계약이 허용하는 레이어에 헬퍼를 두는 것(때로는 의도적 중복). 트리거: `lint-imports` 실패인데 파일 상단엔 그 import 가 없음, "circular import" 를 lazy import 로 고친 직후 계약 깨짐, layered/forbidden contract.
---

# 지연 import 는 순환은 피해도 아키텍처 계약은 못 피한다

## Problem

레이어 A 에서 레이어 B 의 헬퍼가 필요하다. 상단에 import 하면 순환이 난다:

```
ImportError: cannot import name X from partially initialized module ... (circular import)
```

관례적 처방대로 함수 안으로 내린다:

```python
async def _provision(session, run, workspace_dir):
    from backend.workflow.application.runtime.account_resolution import (  # noqa: PLC0415
        product_is_client_attach,
    )
    ...
```

런타임 순환은 사라진다. 그런데 `lint-imports` 가 깨진다:

```
backend.api.webhooks is not allowed to import plugin:
-   backend.api.webhooks -> ... -> connector_dispatch._github (l.96)
    connector_dispatch._github -> runtime.account_resolution (l.82)   ← 함수 안 82행
    runtime.account_resolution -> ... -> plugin.audit.service
```

- **증상**: 파일 **상단에는 그 import 가 없는데** 계약 위반 경로에 그 파일이 나온다. 줄 번호가
  함수 본문을 가리킨다.
- **근본 원인**: import-linter 는 실행하지 않는다. **AST 를 읽는다.** `import` 문이 모듈
  최상단이든 함수 안이든 `if TYPE_CHECKING:` 밖이든, 전부 "이 모듈은 저 모듈에 의존한다"로 센다.
  당연하다 — 함수가 호출되면 그 의존은 **실제로** 일어난다.
- **흔한 오해**: "lazy import 는 의존이 아니다." 런타임 그래프에는 늦게 나타날 뿐, 의존은 의존이다.

## Solution

세 가지 중 하나. 위에서부터 시도한다.

**1. 타입만 필요하면 `TYPE_CHECKING`** — 런타임 의존이 아니므로 대부분의 게이트가 제외한다.

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ._github import GithubDeliveryDeps
```

**2. 헬퍼를 계약이 허용하는 레이어로 옮긴다** — 가장 옳은 답인 경우가 많다. 그 헬퍼가 두
레이어 모두의 관심사라면 애초에 위치가 틀린 것이다.

**3. 의도적으로 중복한다 — 그리고 왜인지 적는다.** 헬퍼가 작고(10줄) 계약이 진짜 지키고 싶은
것을 지키고 있다면, 중복이 계약을 뚫는 것보다 낫다.

```python
async def product_runs_in_place(session, product_id) -> bool:
    """...

    Deliberately duplicated from ``runtime.account_resolution.product_is_client_attach``
    — the R2c contract keeps the inbound layer free of plugin imports, and that
    module reaches ``plugin.audit`` transitively. Importing it from here (even
    LAZILY — import-linter reads function-level imports too) puts the inbound
    layer one hop from a plugin.
    """
```

⚠️ 중복을 택했다면 **두 구현이 드리프트하지 않게 테스트로 묶어라**(같은 입력에 같은 답).

## Key Insights

- **순환 import 와 아키텍처 계약은 다른 문제다.** 전자는 런타임 초기화 순서, 후자는 의존 그래프의
  모양. 같은 처방(lazy import)이 하나만 고친다.
- 계약이 깨졌을 때 **줄 번호를 봐라.** 함수 본문을 가리키면 이 함정이다.
- 계약을 우회할 방법을 찾고 있다면 대개 **설계가 신호를 보내는 중**이다. 왜 이 레이어가 저 레이어를
  알아야 하는지 먼저 물어라 — 답이 "작은 사실 하나" 라면 중복이 정답이다.
- 다음에 먼저 확인할 것: 지연 import 를 추가한 뒤 **`lint-imports` 를 돌려라.** 유닛 테스트는
  통과한다.

## Red Flags

- 순환 import 를 함수 안 import 로 고친 직후 아키텍처 게이트가 깨졌다
- 계약 위반 경로의 줄 번호가 모듈 상단이 아니다
- `# noqa: PLC0415` 를 새로 달았다(= 지연 import 를 추가했다)
- 레이어 경계를 넘는 이유가 "불리언 하나 알아내려고"다
