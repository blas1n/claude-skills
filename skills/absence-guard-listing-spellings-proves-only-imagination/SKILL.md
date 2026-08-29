---
name: absence-guard-listing-spellings-proves-only-imagination
description: 부재 가드를 "내가 본 적 있는 철자 목록"으로 쓰면 상상 밖의 철자로 살아남은 인스턴스를 통과시킨다 — 가드는 green, 결함은 생존. 패턴 목록 대신 **결과 집합(파일/호출자/심볼)을 핀으로 박아라**: 어떤 이름으로든 새 인스턴스가 생기면 목록에 없어서 실패한다. 핀이 썩는 것도 같이 막아라. 트리거 - 부재/금지를 grep 으로 주장하는 테스트, 삭제 PR 의 가드, "이제 아무도 X 를 안 읽는다" 주장, 감사 후속 정리.
version: 1.0.0
task_types: [testing, refactor, review]
triggers:
  - pattern: "grep 패턴을 여러 개 -e 로 나열해 부재를 주장하는 테스트"
  - pattern: "삭제/이전 PR 에서 '남은 호출자 0' 을 가드로 고정할 때"
  - pattern: "감사가 '이제 한 곳에서만 읽는다' 고 결론냈을 때"
category: trap
---

# 철자를 나열하는 부재 가드는 저자의 상상력만 증명한다

## Problem

부재 가드는 보통 이렇게 쓰인다 — **자기가 본 적 있는 형태를 나열**해서.

```python
hits = subprocess.run([
    "grep", "-rn", "--include=*.py",
    "-e", "await workspace_region(",
    "-e", "WorkspaceRow.region,",
    "-e", "select(WorkspaceRow.region",
    "-e", "row.region",              # ← 내가 본 receiver 이름
    str(repo / "backend"),
], capture_output=True, text=True).stdout.strip()

assert not hits, f"판독기가 살아남았다:\n{hits}"
```

**이 가드는 green 이었고, 살아있는 판독기 둘이 그대로 남아 있었다.**

BSVibe 2026-08-28 실측(#844). vault 경로를 만드는 `region` 을 단일 정의로 모으면서
위 가드를 붙였다. 통과했다. 그런데 전체 스위트가 낸 실패를 고치려고 파일을 열자:

| 살아남은 곳 | 철자 | 왜 안 걸렸나 |
|---|---|---|
| `product_bootstrap_runtime.py` | `region = ws.region` | receiver 가 `ws` — 내 목록엔 `row` 뿐 |
| `bootstrap_anchor_backfill.py` | `region=ws.region` → `target.region` | `target` 은 생각도 못 한 이름 |

두 번째가 더 나쁘다. 컬럼이 배포 기본값과 다른 워크스페이스를 **아무도 읽지 않는
디렉터리에 retrofit 하고 `anchor_backfill_done` 을 찍는다** — 성공 로그를 남기는 무동작.

> 패턴 목록으로 쓴 부재 가드는 **부재를 증명하지 않는다. 저자가 몇 가지 형태를 떠올렸는지를
> 증명한다.** 그리고 그 수는 항상 실제 형태보다 적다.

### 왜 특별히 잘 속나

- **부재 가드는 green 이 기본 상태다.** 아무것도 못 찾는 것과 찾을 게 없는 것이 같은 출력이다.
  (→ [[absence-measurement-validity-check]])
- 목록이 길수록 **더 꼼꼼해 보인다.** 4개를 나열하면 1개보다 안전해 보이지만,
  놓친 5번째가 있으면 둘 다 똑같이 0점이다.
- 리팩터 **직후**에 쓰기 때문에 목록이 "방금 내가 고친 것들"이 된다.
  고치지 **못한** 것은 정의상 목록에 없다.

## Solution

### 결과 집합을 핀으로 박아라 — 패턴이 아니라

가드가 물어야 할 질문을 바꾼다. *"내가 아는 나쁜 형태가 있나"* 가 아니라
**"이 명제를 건드리는 곳 전부가 내가 승인한 목록과 같나"**.

```python
# 넓게 잡는다 — receiver 이름을 묻지 않는다
hits = subprocess.run([
    "grep", "-rnE", "--include=*.py",
    r"[A-Za-z_][A-Za-z0-9_]*\.region\b",     # 어떤 receiver 든
    str(repo / "backend"),
], capture_output=True, text=True).stdout.strip()

# 산문은 뺀다 — 왜 지웠는지 설명하는 docstring 이 자기 이름을 부른다
files = {
    line.split(":", 1)[0].replace(str(repo) + "/", "")
    for line in hits.splitlines() if "``" not in line
}

allowed = {
    # 각 항목에 **왜 허용되는지**를 적는다. 이유를 못 적으면 허용하면 안 된다.
    "backend/api/v1/workspace_compliance.py",   # 공시: 저장값을 그대로 보고, 경로를 안 만든다
    "backend/mcp/tools/account_tools.py",       # 같음
    "backend/api/v1/workspaces.py",             # 쓰기 측(컬럼이 아직 존재)
    "backend/.../settle_worker.py",             # carrier: 값의 출처가 settings, 타입이 row 가 아님
}

assert not sorted(files - allowed), \
    "새 판독기가 생겼다:\n" + "\n".join(sorted(files - allowed))
```

**어떤 철자든** 새 인스턴스가 생기면 그 파일이 `allowed` 에 없어서 실패한다.
내 상상력이 아니라 **승인 목록**이 기준이 된다.

### 핀이 썩는 것도 같이 막아라

허용 목록은 시간이 지나면 **더 이상 읽지 않는 파일**을 가리키게 된다. 그 항목이 남아 있으면
같은 파일에 생긴 **진짜 새 판독기**를 가려준다.

```python
assert not sorted(allowed - files), \
    f"허용 목록이 더 이상 읽지 않는 파일을 가리킨다: {sorted(allowed - files)}"
```

### 가드가 진짜로 무는지 확인하라 — 비어 있지 않음을 심어서

```bash
cp target.py /tmp/bak
printf '\ndef _probe(ws): return ws.region\n' >> some/unrelated/file.py
uv run pytest tests/.../test_guard.py -q   # ← 반드시 FAIL 해야 한다
cp /tmp/bak target.py
```

일부러 **가드가 모르는 receiver 이름**(`ws`)으로 심어라. 목록형 가드였다면 이 대조군이
통과해버린다 — 그게 곧 진단이다.

### AST 로 옮겨도 끝이 아니다 — **어떤 AST 모양**을 세는지가 명제다 (2026-08-29)

grep 을 AST 로 바꾸면 산문·주석·docstring 이 후보에서 빠진다. 거기서 멈추기 쉽다.
그런데 **무엇을 세느냐가 곧 무슨 명제를 증명하느냐**다.

`source_ref` 삭제 PR 에서 가드 하나와 양성 대조군 하나에 **같은 스캐너**를 썼다:

```python
def _dict_string_keys(tree):        # dict 리터럴 키 · 첨자 · .get() 전부
    ...
```

부재 가드에는 맞았다("이 키를 쓰는 코드가 없다"). 그런데 양성 대조군
*"`write_seed` 가 `data` 에서 읽는 키는 title/tags/content 뿐"* 에 같은 걸 쓰자
함수가 **내보내는 이벤트 페이로드**의 `"path"` 가 잡혀 실패했다.

    AssertionError: write_seed 가 읽는 키가 바뀌었다: ['content', 'path', 'tags', 'title']

`"path"` 는 `data` 에서 읽은 게 아니라 `emit_event(..., {"path": ...})` 로 **쓴** 것이다.
스캐너가 "이 함수에 등장하는 dict 키"를 셌고, 내가 증명하려던 건 "이 함수가
`data` **에서 읽어 가는** 키"였다. **두 명제는 다르다.**

고침은 대상 변수에 묶는 것이었다 — `data[k]` · `k in data` · `data.get(k)` 세 형태만:

```python
case ast.Subscript(value=ast.Name(id=name), slice=ast.Constant(value=str() as key)) if name == variable:
```

**교훈 둘:**
- **하나의 스캐너를 부재 가드와 대조군에 돌려 쓰지 마라.** 부재 가드는 넓게 잡아도
  되고(과잉 수집은 false positive 로 시끄럽게 실패한다), 소비자 계약을 재는 대조군은
  **정확히** 그 방향만 잡아야 한다. 넓은 쪽을 그대로 쓰면 조용히 다른 질문에 답한다.
- **대조군이 나를 잡았다.** 부재 가드만 있었으면 스캐너가 과잉 수집하는 채로 green 이었다
  — 이번엔 우연히 오탐이 없었을 뿐이다. [[a-control-that-counts-is-blind-to-what-it-guards]]

### 삭제 PR 은 **자기가 만든 유령**을 잡는 가드가 필요하다 (2026-08-29)

가장 놓치기 쉬운 인스턴스는 트리에 원래 있던 것이 아니라 **이 PR 이 방금
만든 것**이다. 심볼을 지우면 그것을 가리키던 **상호참조가 그 순간 죽는다.**

`VerifierWorker` + `SafeModeQueue.expire` 삭제 PR 에서 실제로 그랬다. 가드는
발견해 둔 유령 이름 하나(`expire_all_due`)를 텍스트로 박아뒀고 **green 이었다**.
그런데 방금 지운 `SafeModeQueue.expire` 를 `:meth:` 로 가리키는 docstring 이
**다섯 군데** 살아 있었다. 그중 하나는 단순 언급이 아니었다:

    Per-workspace callers should keep using :meth:`expire`
    (single-statement update, no audit emission)

**없는 메서드를 쓰라고 지시한다.** 원래 있던 유령보다 나쁘다 — 이건 내가 만들었고,
독자에게 "이걸 쓰라"고 말한다.

⇒ **삭제하는 이름마다 "이걸 가리키던 것이 무엇이었나"를 세라.** 지운 심볼은
가드의 needle 목록에 **자동으로 들어가야 한다.** 발견 시점에 알고 있던 이름만
넣으면, 가드는 자기 PR 이 만든 유령에 대해 구조적으로 눈이 먼다.

**그리고 무엇을 금지할지 정확히 정하라 — 언급이 아니라 가리킴이다.**

지운 이름을 *왜 지웠는지 서술하는 산문*은 정당하다(가드 파일 자신이 그렇다).
정당하지 않은 것은 **독자를 없는 곳으로 보내는 포인터**다. 그래서 needle 을
이름이 아니라 **역할 + 이름**으로 잡는다:

```python
_DEAD = ("SafeModeQueue.expire", "mark_expired_bulk", "expire_all_due")

# ✅ 가리킴만 막는다
if f":meth:`{dead}`" in text or f":meth:`~{dead}`" in text:
    survivors.append(...)

# ❌ 이름을 통째로 막으면 "왜 지웠는지" 를 못 쓴다 — 가드가 자기 PR 의
#    커밋 메시지·체크리스트·자기 docstring 을 물어서 영원히 빨갛다
```

음성 대조군을 **양방향**으로 돌려라: `:meth:` 부활은 물어야 하고, `:meth:` 없는
단순 언급은 **통과해야** 한다. 후자를 확인하지 않으면 과잉 차단인 줄 모른다.

### 거울상 — **존재**를 주장하는 가드는 산문 때문에 *초록*이 된다 (2026-08-30)

여기까지는 전부 *부재* 가드 얘기였다. 같은 병이 반대 방향으로도 온다.

방화벽 실패-폐쇄 PR 에서 *"실패 경로가 PID 1 을 죽인다"* 를 이렇게 검사했다:

```python
assert "kill" in script.lower()      # ❌
```

음성 대조군에서 `kill 1` → `true` 로 바꿨는데 **통과했다.** 내가 같은 PR 의 헤더
주석에 써 둔 설명 문장이 grep 을 만족시켰기 때문이다:

    #   2. On any failure, KILL PID 1. A daemon that cannot prove its isolation
    #      must not accept work — dying loudly beats serving silently unprotected.

**가드가 자기 산문에 걸렸다.** 그리고 그 산문은 내가 방금 썼다 — 즉 가드를 잘
설명할수록 가드가 더 확실히 초록이 된다. 최악의 인센티브다.

| 주장 | 산문이 하는 일 | 증상 |
|---|---|---|
| **부재** ("X 가 없다") | 후보를 만들어낸다 | 영원히 **빨강** → 백틱 필터 같은 미봉책을 부른다 |
| **존재** ("X 를 한다") | 조건을 만족시킨다 | 영원히 **초록** → **결함이 살아남는다** |

⇒ 어느 쪽이든 규칙은 하나다: **산문은 후보가 아니어야 한다.**

* Python 이면 AST 를 걸어라(§위 항목).
* 셸/설정처럼 AST 가 없으면 최소한 **주석 줄을 걷어내고** 세라:

```python
def _code_only(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))

assert "kill 1" in _code_only(script)          # ✅ true 로 바꾸면 떨어진다
assert _code_only(script).count("verify_firewall") >= 2   # 정의 + 호출
```

* **정의만 세지 마라.** 함수가 있는 것과 불리는 것은 다른 명제다 — 호출까지
  포함해 2회 이상을 요구하면 "정의해 놓고 아무도 안 부르는" 죽은 가드를 잡는다.

**그리고 이건 음성 대조군이 없었으면 절대 못 잡았다.** 테스트는 green 이었고,
스크립트도 옳았다. 틀린 것은 *"이 테스트가 그 사실을 증명하는가"* 뿐이었고,
그건 **고의로 코드를 망가뜨려 봐야만** 드러난다.

## 감별 — 언제 목록이 맞고 언제 집합이 맞나

| 목표 | 도구 |
|---|---|
| 특정 **심볼**이 사라졌나 | `assert not hasattr(mod, "name")` — 정확하고 철자 문제가 없다 |
| 특정 **import 경로**가 안 쓰이나 | `grep "from backend.foo"` — 동명이인을 안 문다 (→ [[deletion-pr-needs-an-absence-guard-and-a-control]] #5) |
| **어떤 형태로든** 이 개념을 만지는 곳이 승인 목록뿐인가 | **집합 핀** (이 스킬) |

앞의 둘은 목록이어도 된다. **세 번째만 목록이 원리적으로 실패한다** — 형태가 열려 있기 때문이다.

## Verification

- [ ] 가드가 receiver/변수 이름을 열거하지 **않는다**
- [ ] 허용 목록의 **모든 항목에 이유가 적혀 있다**
- [ ] 무관한 파일에 가드가 모르는 철자로 심어 **FAIL 을 봤다**
- [ ] 허용 목록의 stale 항목도 실패시킨다
- [ ] 가드가 산문(docstring/주석)을 매칭하지 않는다 — 안 그러면 "이미 다 했다"고 보고한다

## Related

- [[absence-measurement-validity-check]] — 빈 출력이 "없음"이 아닌 더 아래 층
- [[deletion-pr-needs-an-absence-guard-and-a-control]] — 삭제 PR 전반. 이름 대신 import 를 세라(#5)는
  **거짓 양성**을 막고, 이 스킬은 **거짓 음성**을 막는다. 둘 다 필요하다
- [[a-control-that-counts-is-blind-to-what-it-guards]] — assert 에 개수가 보이면 명제를 그대로 써라
