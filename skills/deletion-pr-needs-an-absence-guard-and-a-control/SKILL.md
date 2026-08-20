---
name: deletion-pr-needs-an-absence-guard-and-a-control
description: 죽은 코드/테이블을 지울 때 삭제만 하고 스위트가 green 이면 "지웠다"가 거짓일 수 있다 — 빈 디렉터리가 namespace package 로 살아남고, downgrade 는 안 돌려봐서 죽어 있고, 알리바이 테스트가 죽은 표면을 명세로 박아둔다. 부재를 주장하는 가드(RED→GREEN)와 살아남아야 할 것의 양성 대조군을 먼저 써라. 트리거 - 서브시스템/패키지/테이블 삭제, 구조 감사 후속, "호출자 0이니 지우자", 드롭 마이그레이션, 죽은 코드 정리 PR.
version: 1.0.0
task_types: [refactor, testing, review]
triggers:
  - pattern: "패키지/모듈/서브시스템을 통째로 삭제하는 PR"
  - pattern: "DB 테이블 드롭 마이그레이션"
  - pattern: "구조 감사가 '프로덕션 호출자 0' 이라고 지목한 코드 정리"
  - pattern: "죽은 코드 삭제 후 테스트가 green 인데 정말 지워졌는지 확신이 안 설 때"
category: methodology
---

# 삭제 PR 에는 부재 가드와 양성 대조군이 필요하다

## Problem

삭제는 "지우고 테스트 돌려서 green 이면 끝"으로 취급되기 쉽다. **그 green 이 거짓일 수 있다.**

BSVibe 2026-08-20, 죽은 서브시스템 5건(#786~#790, −5,334 LOC)을 순차 삭제하면서
**부재 가드가 없었으면 전부 통과했을 결함 5종**을 잡았다:

| # | 무엇이 | 왜 안 잡히나 |
|---|---|---|
| 1 | **빈 디렉터리가 계속 import 된다** (3회) | `git rm -r` 은 파일만 지운다. 디렉터리가 남으면 **PEP 420 namespace package** 로 `import` 가 성공한다. CI 는 fresh checkout 이라 안 겪어서 "로컬만 이상하다"로 오진하게 된다 |
| 2 | **`downgrade` 가 죽은 채로 머지될 뻔** | 드롭 마이그레이션은 보통 `upgrade` 만 돌려본다. `downgrade` 의 import 누락은 그때 안 터진다 |
| 3 | **알리바이 테스트** | 죽은 표면을 *명세로 박아둔* 테스트(`test_llm_provider_routing_surface_preserved`, `test_router_budget_models_importable`)가 존재해서, 그것만 보면 "쓰이는 코드"처럼 보인다 |
| 4 | **이름 충돌로 오삭제** | `ValidationError` 를 grep 하면 9건이 걸리는데 **전부 pydantic 것**이었다. 이름만 보고 지웠으면 빌드가 깨진다 |
| 5 | **stale ignore 규칙** | `pyproject.toml` 의 import-linter ignore 가 삭제된 모듈을 가리켜 남는다 |

## Solution

### 1. 부재를 주장하는 가드를 **먼저** 써라 (RED → GREEN 은 삭제에도 적용된다)

```python
_DEAD_MODULES = ("backend.foo.db", "backend.foo.repositories")

@pytest.mark.parametrize("module", _DEAD_MODULES)
def test_the_dead_module_is_gone(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)

def test_the_package_re_exports_none_of_it() -> None:
    pkg = importlib.import_module("backend.foo")
    still = [n for n in _DEAD_NAMES if hasattr(pkg, n)]
    assert not still, f"아직 내보낸다: {still}"
```

⚠️ 문자열을 쪼개 써라 (`"backend.foo" + ".db"`) — 안 그러면 정적 분석기/린터가 삭제된
모듈을 참조로 보고 경고한다.

### 2. **양성 대조군**을 함께 써라 — 살아남아야 할 것

삭제 대상 옆에 사는 것이 함께 죽는 게 가장 비싼 실패다. 삭제 **전에도** green 이어야 한다
(그래야 대조군으로 성립한다).

| 지운 것 | 옆에 살던 것 | 대조군이 막은 것 |
|---|---|---|
| BSGateway 라우팅 잔재 | `run_routing_rules` (현역) | 같은 패키지라 통째로 지울 뻔 |
| 예산 **강제** | 비용 **보고**(`actual_cost_cents`) | 같은 파일, 다른 축 |
| 캐노니컬라이제이션 미러 | `note_embeddings` (1,714행, 시맨틱 검색) | 같은 `db.py` |
| `HttpClientBase` | `redact_url_password` | 사라지면 DB 비밀번호가 로그로 샌다 |

### 3. 드롭 마이그레이션은 **왕복**을 돌려라

```bash
alembic upgrade head        # 대상 부재 확인
alembic downgrade -1        # 복원 확인  ← 여기서 import 누락이 터진다
alembic upgrade head        # 다시 부재 확인
```

그리고 **downgrade 를 손으로 적지 마라.** 원본 마이그레이션의 반대편을 그대로 미러해라 —
손으로 다시 적으면 드리프트가 난다.

```python
src = pathlib.Path("versions/20260524_bundle_k.py").read_text()
my_upgrade   = src[src.index("def downgrade"):]           # 원본의 downgrade == 내 upgrade
my_downgrade = src[src.index("def upgrade"):src.index("def downgrade")]
```

ENUM 을 쓰는 테이블은 **타입도 지워라**(안 지우면 고아로 남는다). 지우기 전에 카탈로그로
다른 사용처 0 을 확인:

```sql
select c.relname, a.attname, t.typname from pg_attribute a
  join pg_class c on c.oid=a.attrelid join pg_type t on t.oid=a.atttypid
 where t.typname = '<enum>' and c.relkind='r';
```

### 4. 삭제·리베이스 후 정리는 **두 줄 다** 필요하다

```bash
find backend tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find backend tests -type d -empty -delete 2>/dev/null   # ← 이게 진짜 고침
```

진단: `ls -A <dir> | wc -l` 이 0 이고 `git ls-files <dir>` 도 비면 순수 로컬 찌꺼기다.

### 5. grep 은 **이름이 아니라 import 를** 세라

```bash
# 나쁨 — 동명이인이 걸린다
grep -rn "\bValidationError\b" backend/
# 좋음 — 그 모듈에서 온 것만
grep -rn "from backend.shared.core" backend/ plugin/ bsvibe_sdk/
```

그리고 grep 범위를 `backend/` 로만 잡지 마라. `tests/*/conftest.py` 의 side-effect import
(`import backend.foo.db  # noqa: F401`)가 자주 남는다.

### 6. 알리바이 테스트는 **삭제 대상이지 근거가 아니다**

죽은 표면을 pin 하는 테스트를 만나면 그게 "쓰인다"는 증거가 아니다. 특히 그 테스트의
docstring 이 존재 이유를 자백하는 경우가 많다 — *"the contract **the 4 product migrations**
rely on"* 인데 그 4개 제품이 사라진 것이 삭제의 이유였다.

### 7. 여러 드롭 PR 은 **순차**로만 간다

각 드롭이 alembic head 를 올리므로 병렬로 부모를 잡으면 head 가 쪼개진다 — **CI 는 green
인데 배포가 죽는다.** 앞 PR 머지 후 `alembic heads` 로 확정하고 `down_revision` 을 붙여라.
head 는 보통 **두 테스트 파일**에 문자열로 고정돼 있다.
→ `stale-migration-pr-splits-alembic-head`, `alembic-revision-id-32-chars-and-pinned-head`

## Verification

삭제 PR 이 끝났다고 말할 조건:

- [ ] 부재 가드가 RED 였다가 GREEN 이 됐다 (처음부터 green 이면 아무것도 안 검사한 것)
- [ ] 양성 대조군이 삭제 **전에도 후에도** green
- [ ] 마이그레이션 왕복 3단계 통과 + 대조군 테이블이 전 과정 생존
- [ ] `lint-imports` / 린터가 stale ignore 규칙을 더 안 부른다
- [ ] 테스트 **수집 델타를 파일 단위로 설명**할 수 있다 (설명 안 되는 차이 = 조사 대상)
- [ ] prod 에서 대상이 실제로 사라졌고 살아야 할 것이 살아있다

## Related

- `stale-migration-pr-splits-alembic-head` — 순차 머지 강제의 이유
- `deleting-inert-config-row-disables-hidden-feature` — 삭제 **전에** 존재를 읽는 코드를 세라
- `large-codebase-deprecation-removal` — 삭제로 깨진 테스트를 다루는 3단계 전략
- `boundary-test-must-not-supply-the-answer` — 대조군이 답을 건네주면 안 된다
