---
name: re-parenting-a-dependency-moves-the-test-override-seam
description: FastAPI 의존성의 부모를 바꾸면 `dependency_overrides` 씸이 같이 이동한다 — 스위트가 오버라이드하던 콜러블에 더는 아무도 의존하지 않아서, 테스트는 조용히 프로덕션 인증을 다시 타고 "missing Authorization header" 로 무너진다. 기능이 틀린 게 아니라 씸이 옮겨간 것이다.
---

# 의존성의 부모를 바꾸면 테스트 오버라이드 씸이 같이 옮겨간다

## Problem

- **증상**: 인증 로직 하나를 손봤는데 **관련 없어 보이는 테스트 수십 개**가
  `401 {"detail":"missing Authorization header"}` 로 깨진다. 새로 쓴 테스트는 전부 초록이다.
- **근본 원인**: `app.dependency_overrides[f] = g` 는 **f 를 루트로 하는 서브트리 전체**를
  치환한다. 하위 의존성(`get_workspace_id` 등)이 **f 를 더 이상 거치지 않게** 리팩터링하면,
  오버라이드는 그 경로를 못 덮는다 ⇒ 실제 인증이 다시 돈다 ⇒ 헤더가 없으니 401.
- **흔한 오해**: "테스트가 낡았으니 다 고치면 된다."
  실은 **내가 씸을 옮겼다**. 스위트 전체가 합의한 계약을 한 커밋으로 깬 것이다.

실제 사례(BSVibe #1017): 게이트를 이중 발급자로 만들며 `get_workspace_id` 를
`CurrentUser` 대신 새 `CurrentPrincipal` 에 의존시켰다. 스위트 여러 곳의
`dependency_overrides[get_current_user] = _user` 가 **한 번에 무의미해져** 29개가 깨졌다.

## Solution

### 원칙: **새 데이터를 아래로 흘리되, 기존 씸의 부모 관계는 건드리지 마라**

새 정보는 요청 스코프에 **발행**하고, 하위 의존성은 그걸 **비침습적으로 읽는다**.
그러면 오버라이드는 원래 의미를 유지하고, 오버라이드된 경우엔 자연히 옛 동작으로 폴백한다.

```python
async def get_current_principal(request: Request, authorization=Header(None), session=...):
    principal = await resolve(...)
    # 모든 하위 의존성에 principal 을 꿰지 않는다 — 그러면 씸이 옮겨간다.
    # 요청에 발행만 한다. get_current_user 를 오버라이드하면 이 함수 자체가
    # 안 돌고, 아래 읽기는 None 이 되어 리팩터링 전 경로로 자연 폴백한다.
    request.state.api_principal = principal
    return principal

async def get_current_user(principal: CurrentPrincipal) -> User:   # 씸은 여기 그대로
    return principal.user

def request_principal(request: Request) -> ApiPrincipal | None:
    p = getattr(request.state, "api_principal", None)
    return p if isinstance(p, ApiPrincipal) else None

async def get_workspace_id(request: Request, user: CurrentUser, session=...):
    principal = request_principal(request)          # 있으면 쓰고
    ws = principal.workspace_id if principal else None
    if ws is None:                                   # 없으면 옛 방식 그대로
        ws = await resolve_workspace_id(session, supabase_user_id=user.id)
    ...
```

### 착수 전 30초 점검

```bash
# 1. 내가 건드리는 의존성을 누가 오버라이드하는가
grep -rn "dependency_overrides\[" tests/ | sort | uniq -c | sort -rn
# 2. 그 씸에 의존하는 하위 의존성 목록 — 이게 리팩터링의 진짜 반경이다
grep -rn "Depends(get_current_user)\|: CurrentUser" backend/ | wc -l
```

## Key Insights

- **`dependency_overrides` 는 함수가 아니라 서브트리를 치환한다.** 그래서 "어떤 dep 이
  어떤 dep 에 의존하는가"는 프로덕션 구조일 뿐 아니라 **테스트 하네스의 공개 API** 다.
- **깨진 테스트 개수는 반경의 센서다.** 29개가 한 모양으로 깨졌으면 개별 수정 대상이
  아니라 **하나의 구조 결정**이 잘못된 것이다. 29개를 고치기 전에 그 결정을 되돌려봐라.
- **오버라이드 경로의 자연 폴백이 설계 목표다.** `request.state` 읽기가 `None` 일 때
  리팩터링 **전** 동작이 나오면, 씸을 오버라이드한 테스트는 *정의상* 원래 의미를 유지한다.
- **역방향 위험도 기억해라**: 오버라이드가 살아 있으면 새 경로는 **테스트되지 않는다.**
  그래서 새 경로는 **오버라이드를 전혀 안 쓰는** 별도 파일에서 진짜 크리덴셜로 재야 한다.

## Red Flags

- 인증/스코핑 dep 을 리팩터링한 뒤 **`missing Authorization header`** 가 대량으로 뜬다
  ← 테스트가 인증을 우회하고 있었는데 이제 진짜로 돌고 있다는 정확한 지문
- 무관해 보이는 스위트(`tests/auth`, `tests/api/test_*_rbac`)가 한꺼번에 빨개진다
- 새로 쓴 테스트는 전부 초록인데 기존 것만 깨진다 ← 기능이 아니라 **씸**이 원인
- dep 시그니처에서 파라미터를 **교체**했다(`user: CurrentUser` → `principal: CurrentPrincipal`)
  ← 추가가 아니라 교체는 항상 씸 이동이다
