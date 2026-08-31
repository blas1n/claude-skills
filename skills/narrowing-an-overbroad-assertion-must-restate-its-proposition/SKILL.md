---
name: narrowing-an-overbroad-assertion-must-restate-its-proposition
description: 공유 테스트 헬퍼가 명제보다 **넓은 범위**를 세면(디렉터리 전체 rglob, 테이블 전체 count), `len == 1` 이 사실은 "이 범위에 물건이 딱 하나 존재한다"는 훨씬 센 주장이 된다. 같은 범위에 쓰는 기능이 하나 생기면 무관한 테스트가 우수수 빨개지고, **가드가 깨진 것처럼 보이지만 가드는 멀쩡하다**. 함정은 고치는 쪽에 있다 — 헬퍼를 좁히면 그 명제가 제외된 표면에서 조용히 사라진다. 좁히면 **반드시 그 명제를 새 표면에 다시 걸어라**. 트리거 - 새 기능이 기존 저장소/디렉터리/테이블에 쓰기 시작할 때, 무관한 테스트 다수가 동시에 빨개질 때, `rglob`/`glob`/`count(*)` 로 세는 공유 헬퍼, `assert len(x) == 1` / `assert x == []`.
version: 1.0.0
task_types: [testing, refactor, review]
triggers:
  - pattern: "새 기능이 기존 vault/디렉터리/테이블에 파일이나 행을 추가하기 시작할 때"
  - pattern: "내 변경과 무관해 보이는 테스트가 여러 파일에서 동시에 실패할 때"
  - pattern: "테스트 헬퍼가 rglob('*.md') / list_files(dir) / count(*) 로 범위 전체를 셀 때"
category: trap
---

# 범위를 세는 단언은 자기 명제보다 넓게 주장한다

## Problem

테스트 헬퍼가 이렇게 생겼다면 —

```python
def _notes(vault_root, workspace_id):
    ws_dir = vault_root / REGION / str(workspace_id)
    return list(ws_dir.rglob("*.md"))      # ← 워크스페이스 vault 전체
```

이걸 쓰는 단언은

```python
assert len(_notes(tmp, ws)) == 1     # 의도: "가든 노트가 하나 생겼다"
assert _notes(tmp, ws) == []         # 의도: "형님 글자가 0자면 노트가 없다"
```

**의도한 명제가 아니다.** 실제로 주장하는 것은
*"이 워크스페이스 vault 안에 `.md` 파일이 정확히 하나/하나도 존재하지 않는다"* 다.

그래서 같은 vault 에 쓰는 기능이 **하나만** 생겨도 무관한 테스트가 무너진다.

### 왜 위험한가 — 실패가 거짓말을 한다

빨간 테스트 이름이 `test_one_click_acknowledge_leaves_no_vault_note` 이면
*"내가 §13 가드를 깼다"* 로 읽힌다. 실측(BSVibe 2026-08-31): **가드는 멀쩡했다.**

```
settle_sink_skipped_not_worth_remembering  has_founder_text=False   ← 가드 정상 작동
original_recorded  path=.../seeds/request/6b4f8f66-….md              ← 늘어난 건 이것
```

`seeds/feedback/` 은 안 생겼다 — 즉 "형님이 안 쓴 글자로 노트를 만들지 않는다"는
명제는 지켜졌다. 늘어난 것은 **명제와 무관한 다른 종류의 파일**이었다.

가드가 깨졌다고 오독하면 멀쩡한 기능을 되돌리게 된다.

### 복제된다

이 모양은 **한 파일에 안 머문다.** 같은 세션에서 세 파일이 같은 헬퍼를 복사해
갖고 있었다:

| 파일 | 헬퍼 | 깨진 테스트 |
|---|---|---|
| `tests/glue/test_settle_worker.py` | `_written_notes` | 5 |
| `tests/knowledge/test_settlement_needs_founder_text.py` | `_notes` | 5 |
| `tests/workflow/application/test_guided_action_carries_guidance.py` | `_notes` | 3 |

한 곳을 고치고 초록을 보면 끝난 줄 안다. **전체 스위트를 돌리기 전까지 나머지
둘은 안 보인다** — 하위 집합만 돌리면 라운드가 12 → 5 → 5 로 늘어난다.

## Solution

### 1. 헬퍼를 명제의 범위로 좁힌다

```python
def _notes(vault_root, workspace_id):
    """§13 이 말하는 vault 노트 — 싱크가 만드는 가든 관찰 노트."""
    garden = _ws_dir(vault_root, workspace_id) / "garden"
    return list(garden.rglob("*.md")) if garden.exists() else []
```

### 2. ⭐ 제외한 표면에 그 명제를 **다시** 건다

여기가 진짜 함정이다. 좁히기만 하면 테스트는 초록이 되지만, **그 명제가
제외된 표면에서 사라진다.** §13 의 구멍이 새 원본 레이어에서 조용히 다시 열려도
아무도 모른다.

```python
def _feedback_originals(vault_root, workspace_id):
    """형님이 쓴 글자로 만들어진 원본 — §13 이 0자일 때 없어야 하는 쪽."""
    feedback = _ws_dir(vault_root, workspace_id) / "seeds" / "feedback"
    return list(feedback.rglob("*.md")) if feedback.exists() else []
```

```python
assert _notes(tmp, ws) == []
# 원본 레이어에서도 마찬가지다 — 형님이 쓴 글자가 0자면 피드백 원본도 없다.
assert _feedback_originals(tmp, ws) == []
```

좁히기 **전보다 가드가 넓어졌다.** 이게 올바른 종료 상태다.

### 3. 워크스페이스/테넌트 경계 테스트를 특히 조심하라

격리 테스트가 `len(a_notes) == 1 and len(b_notes) == 1` 로 경계를 증명하고
있었다면, 좁히는 순간 **새 표면의 격리는 아무도 안 지킨다.** 같이 걸어라.

```python
assert len(_written_originals(tmp, ws_a)) == 1
assert len(_written_originals(tmp, ws_b)) == 1
assert "alpha" in _written_originals(tmp, ws_a)[0].read_text()
```

## Checklist

새 기능이 기존 저장소(디렉터리·테이블·버킷)에 쓰기 시작할 때:

- [ ] 그 저장소를 **범위로 세는** 테스트 헬퍼를 전부 찾았나 (`rglob` · `glob` ·
      `list_files` · `count(*)` · `len(...)` )
- [ ] **하위 집합이 아니라 전체 스위트**를 돌렸나 — 복제된 헬퍼는 다른 디렉터리에 산다
- [ ] 실패한 테스트가 정말 내 결함인가, 아니면 헬퍼의 과잉 주장인가 —
      **로그로 명제 자체를 확인**했나 (`has_founder_text=False` 같은 것)
- [ ] 헬퍼를 좁혔다면, 제외한 표면에 그 명제를 **다시 걸었나**
- [ ] 격리/경계 테스트라면 새 표면의 경계도 걸었나

## Why it matters

이건 "테스트 고치기"가 아니라 **가드 이설**이다. 좁히기만 하고 넘어가면
전체가 초록인 채로 명제 하나가 시스템에서 사라진다 — 그리고 그 사실은
그 구멍이 실제로 뚫린 날에야 드러난다.

관련: [[a-control-that-counts-is-blind-to-what-it-guards]] (assert 에 `len` 이
보이면 명제를 그대로 써라) · [[deleting-a-layer-reopens-what-the-layer-was-covering]]
(층을 지우면 그 층이 덮던 게 되살아난다) · [[absence-guard-must-scan-tests-and-strings]]
