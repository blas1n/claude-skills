---
name: a-layering-contracts-refusal-names-the-right-home
description: 새 import 가 아키텍처 계약(import-linter 등)을 깨뜨리면, 기본 반응은 ignore_imports 추가다 — 그런데 대개 그 거절은 "공유하려는 그것이 지금 엉뚱한 컨텍스트에 산다"는 말이다. 올바른 층으로 내리면 기존 호출자 여럿이 그걸 채택할 수 있게 되고, 그중 하나는 이미 조용히 드리프트해 있다.
---

# 계층 계약의 거절은 그 로직이 **어디 살아야 하는지**를 말한다

## Problem

- **증상**: 기능은 다 됐는데 `lint-imports` / ArchUnit / dependency-cruiser 가
  **전이적 경로 하나**로 빨개진다. 내가 새로 만든 모듈이 기존 모듈을 부르고, 그게
  또 다른 걸 불러서, 금지된 패키지까지 닿는다.
- **근본 원인**: 내가 재사용하려는 함수가 **그 함수의 진짜 주인이 아닌 컨텍스트**에 살고 있다.
  전이 경로는 그 잘못된 소속이 만든 것이다.
- **흔한 오해**: ① `ignore_imports` 에 한 줄 넣는다 ② 함수 안으로 lazy import 를 옮긴다.
  **②는 안 통한다 — import-linter 는 함수 레벨 import 도 본다**
  (스킬 `import-linter-sees-function-level-imports`).
  ①은 통하지만 계약이 지키려던 걸 조용히 갉아먹는다.

실제 사례(BSVibe #1017):
`api.deps → api.bearer_auth → mcp.auth → mcp.api → plugin.audit.events`.
액세스 토큰 검증기가 **MCP 트랜스포트**에 살고 있었는데, 그건 그 토큰의 **발급자**가 아니다.

## Solution

### 1. 거절이 지목한 **공유 대상**을 찾아라

깨진 경로에서 "내가 실제로 필요한 것"이 무엇인지 한 문장으로 말해라.
*"우리 발급자가 낸 토큰을 서명 + `jti` 행으로 검증하는 것"* — 여기 **MCP 는 없다.**

### 2. 그 문장의 주어가 사는 곳으로 **내려라**

발급하는 층이 검증도 소유한다. MCP 는 결과를 자기 타입으로 **어댑트만** 한다.

```python
# backend/identity/access_tokens.py  ← 발급자의 컨텍스트
async def verify_access_token_with_row(*, token, issuer, session) -> VerifiedAccessToken: ...

# backend/mcp/auth.py  ← 이제 얇은 어댑터
verified = await verify_access_token_with_row(token=token, issuer=issuer, session=session)
return McpPrincipal(user_id=verified.user_id, ...)
```

### 3. **기존 호출자를 전부 세고, 드리프트를 확인해라** — 여기가 보상이다

같은 일을 **직접** 하던 곳을 전부 찾아 새 함수로 돌려라. 그리고 각각을 **대조**해라:

| 호출자 | 서명 | `revoked_at` | 행 `expires_at` |
|---|---|---|---|
| MCP 트랜스포트 | ✅ | ✅ | ✅ |
| PAT 엔드포인트 | ✅ | ✅ | ✅ (MCP 경유) |
| **worker register** | ✅ | ✅ | **❌ 누락** |

⇒ 통합이 **실재하는 보안 드리프트**를 드러냈다: DB 에서 수명이 줄어든 토큰으로
워커 등록이 됐다. 계약이 아니었으면 아무도 안 셌다.

### 4. 통합됐음을 **전선 절단으로** 증명해라

공유 함수의 검사 하나를 끄고, **여러 호출자의 테스트가 같이 빨개지는지** 봐라.
한 곳만 빨개지면 아직 공유가 아니다.

```
=== CUT: 행 만료 검사 ===
FAILED tests/api/test_v1_dual_issuer_auth.py::test_row_expiry_is_enforced...
FAILED tests/mcp/test_auth.py::test_resolve_rejects_db_expired_row
2 failed   ← 두 표면이 같은 것을 부른다는 증거
```

## Key Insights

- **계약의 거절은 잔소리가 아니라 설계 정보다.** 전이 경로가 금지 패키지에 닿았다는 건,
  내가 재사용하려는 것이 **그 경로를 만들 이유가 없는 층**에 있다는 뜻이다.
- **"발급하는 쪽이 검증도 소유한다."** 토큰·서명·세션·캐시 키 — 만든 컨텍스트가 주인이고,
  소비자는 **어댑터**여야 한다. 소비자에 두면 다음 소비자가 복사한다.
- **복사가 곧 드리프트다.** 검증 체인을 N 곳이 각자 들고 있으면 N 개가 같지 않다.
  통합할 때 **표로 대조**해라 — 그게 이번 PR 의 진짜 수확이었다.
- **`ignore_imports` 는 마지막 수단이다.** 넣기 전에 물어라: *이 경로를 만든 import 를
  아예 없앨 수 있나?* 대개 있다.

## Red Flags

- 새 모듈이 만든 **전이** 경로로 계약이 깨진다(내 직접 import 는 무해해 보인다)
- 고치려고 **lazy(함수 레벨) import** 를 떠올렸다 ← import-linter 에는 안 통한다
- 재사용하려는 함수가 **그걸 만들지 않은 컨텍스트**에 산다(트랜스포트·라우터·UI 층의 검증기)
- 같은 검증/파싱/직렬화가 두 곳 이상에 손으로 쓰여 있다 ← 통합 전에 **차이를 표로** 세라
