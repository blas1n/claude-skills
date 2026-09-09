---
name: a-dead-entity-can-be-the-subject-of-a-live-claim
description: producer 없는 테이블·0행 컬럼·안 불리는 설정을 발견하면 "청소 항목"으로 분류되지만, 그 이름은 대개 **어딘가에서 사용자에게 무언가를 주장하는 문장의 주어**로 살아 있다 — 공시·보존 정책·대시보드·프롬프트·문서. 죽은 것은 무해하지 않고 **거짓 주장을 생산한다.** 지우기 전에 "무엇이 이것에 대해 말하는가"를 따로 세라. 트리거 - "0행이니 죽은 듯", 감사/인수인계의 미확인 잔재 목록, DROP 마이그레이션 착수, "안 쓰이니 지우자", 컴플라이언스·공시·정책 문구를 만질 때.
version: 1.0.0
task_types: [review, refactor, audit]
triggers:
  - pattern: "prod 0행 / 호출자 0 인 테이블·컬럼을 발견해 삭제를 검토할 때"
  - pattern: "인수인계·감사가 '죽은 것으로 보이지만 단정 안 함' 으로 넘긴 항목"
  - pattern: "GDPR/보안/SLA 공시, 보존 정책, 상태 대시보드 문구를 읽거나 쓸 때"
  - pattern: "DROP TABLE / drop_column 마이그레이션 착수 직전"
category: methodology
---

# 죽은 자리가 살아 있는 주장의 주어일 수 있다

## Problem

죽은 것을 찾으면 다음 질문은 자동으로 **"지울까?"** 가 된다. 그 질문은 대상을
*무해한 잉여* 로 전제한다. 실제로는 이름이 남아 있는 한 **누군가 그것에 대해
말하고 있을** 가능성이 크고, 그 문장은 이제 **거짓**이다.

BSVibe 2026-09-09. 인수인계가 이렇게 넘겼다:

> `audit_events` 테이블이 prod 에서 완전히 비어 있다. 코드에서 그 테이블을 쓰는
> 곳을 못 찾았다. **죽은 테이블로 보이지만 단정하지 않았다** — 지우려면 따로 재라.

재보니 죽은 게 맞았다(생성 0 · select 0 · delete 0 · prod 0행). 그런데 **살아 있는
프로덕션 참조가 정확히 하나** 있었고, 그게 사용자에게 나가는 문장이었다:

```python
# GET /api/v1/workspace/processing-record — GDPR Art. 30 처리기록
"retention": {
    ...
    "audit_events": "Retained 1 year for security incident review.",
}
```

**세 겹으로 거짓이었다:**

| 축 | 주장 | 실제 |
|---|---|---|
| 주어 | `audit_events` 가 감사 흔적 | 한 번도 행을 담은 적 없음. 진짜 흔적은 `audit_outbox` (5,494행) |
| 창 | 1년 후 정리 | 보존은 `audit_retention_days`, **NULL = forever 가 기본** · prod 3/3 NULL |
| 강제 | (암묵) | `365` 는 보존 경로 어디에도 없다 — 맨 문자열 |

즉 **정리한다고 말하면서 영구 보관하고 있었다.** 청소 항목이 아니라 컴플라이언스
결함이었다.

### 왜 안 보이나

- **이름으로 grep 하면 노이즈에 묻힌다.** `audit_events` 는 41건이 나오는데
  대부분이 동명의 **현역 파이썬 모듈**(`workflow.application.audit_events`,
  `chat_audit_events`)이었다. 그래서 0행 사실이 **2026-08-16 에 이미 실측되고도**
  3주 뒤 같은 자리에서 재발견됐다.
- **"쓰는 곳"만 센다.** 감사는 read/write 호출자를 센다. **그것에 대해 말하는 곳**은
  CRUD 가 아니라 문자열이라 그 집계에 안 들어온다.
- **주장은 조용하다.** 공시 문구는 테스트가 키 존재만 보고 지나가고, 아무도
  빨개지지 않으며, 틀려도 런타임 에러가 없다.

### 이 모양은 반복된다 — 같은 파일이 이미 두 번 고쳤다

`workspace_compliance.py` 는 **같은 결함을 두 번** 고쳐놓고 세 번째를 40줄 옆에
두고 있었다:

```python
# region — "a column that never steered anything" 을 Art.30 기록에서 뺐다
# canonical_anchors — "producer-less: nothing writes it, so reading it
#   under-reported the founder's knowledge as empty for every workspace
#   (a GDPR Art. 15/20 defect)"
```

**고친 자리는 풍부한 단언을 얻었고, 안 고친 자리는 키 존재 검사만 남았다.**
[[a-lesson-fixed-in-one-failure-path-does-not-travel-to-the-others]]

## Solution

### 1. "쓰는 곳" 과 "말하는 곳" 을 **따로** 세라

```bash
# ① 쓰는 곳 — CRUD (보통 여기서 멈춘다)
grep -rn "AuditEvent\b" --include="*.py" | grep -v test

# ② 말하는 곳 — 문자열/문서/설정 (이쪽이 사용자에게 나간다)
grep -rn "[\"']audit_events[\"']" --include="*.py" --include="*.ts" --include="*.tsx" \
     --include="*.json" --include="*.md" --include="*.yaml"
```

②는 응답 스키마 · 프론트 문구 · 프롬프트 · 대시보드 라벨 · 정책 문서까지 간다.
①이 0 이어도 ②가 0 이 아니면 **삭제가 아니라 정정이 먼저**다.

### 2. 주장을 만나면 **세 축을 각각** 검증하라

주어 · 값/창 · 강제 경로. 하나만 맞아도 문장 전체가 거짓일 수 있다.

- **주어**: 이 이름이 실제로 그 일을 하는 객체인가? (동명이인 주의)
- **값**: 문장이 말하는 숫자가 코드 어디엔가 실제로 있나? `grep 365` 가 0건이면
  그 숫자는 아무도 강제하지 않는다
- **강제**: 그 값을 읽어서 행동을 바꾸는 코드가 있나? 없으면 **문서가 곧 유일한
  구현**이다

### 3. 정정할 때는 **아무것도 안 움직이는 값** 대신 **실제로 움직이는 값**을 읽어라

이게 `region` 결함과 정반대인 지점이다. `region` 은 아무것도 안 움직이는 컬럼을
Art.30 에 echo 해서 틀렸다. `audit_retention_days` 는 **스윕이 실제로 그 컬럼으로
워크스페이스를 고른다** — 그래서 echo 하는 것이 옳다.

> 컬럼을 공시에 넣어도 되는지의 기준은 "있느냐" 가 아니라 **"그 다름이 무언가를
> 바꾸느냐"** 다. [[feedback_simplest_is_best_delete_before_adding]]

```python
def _audit_retention_sentence(retention_days: int | None) -> str:
    if retention_days is None:            # 문서화된 기본값 = forever
        return "audit_retention_days is unset — the default — so audit_outbox rows are retained forever, ..."
    return f"audit_retention_days = {retention_days}: a daily sweep deletes audit_outbox rows older than {retention_days} days."
```

**두 분기를 다 테스트하라.** prod 가 도는 분기(대개 기본값)가 조용히 드리프트하는 쪽이다.

### 4. 삭제하기로 했으면 **지식을 정의 지점에 남겨라**

이번 건이 두 번 재발견된 이유는 "0행" 이라는 사실이 **마이그레이션 독스트링과
테스트 독스트링에만** 있었기 때문이다. 다음 사람이 여는 곳은 모델 정의다.

- 남길 거면 → 모델/정의 파일에 `PRODUCER-LESS` + 실측치 + 왜 안 지웠는지
- 지울 거면 → **드롭 마이그레이션 독스트링이 영구 기록**이 된다. 실측치를 거기 적어라

## Key Insights

- **죽은 것은 무해하지 않다 — 거짓 주장을 생산한다.** "0행이니 위험 없음" 은
  데이터 관점에서만 참이다. 문장 관점에서는 0행이야말로 주장을 **최대로 틀리게**
  만든다.
- **삭제 후보를 만나면 첫 질문은 "지울까"가 아니라 "무엇이 이것에 대해 말하나"** 다.
  말하는 곳이 있으면 그건 청소가 아니라 **결함**이고, 우선순위가 다르다.
- **동명이인이 발견을 지연시킨다.** 한 이름이 여러 층에 있으면(테이블 · 모듈 ·
  라우트) grep 건수가 커져서 죽은 쪽이 노이즈로 읽힌다. 건수가 크면 **축별로 갈라
  세라** — 따옴표 붙은 리터럴 vs import 경로 vs 심볼.
- **공시·정책 문구를 검증하는 테스트는 키 존재만 보는 경향이 있다.** 그 키가
  담은 문장이 참인지는 아무도 안 본다. 조사된 항목만 풍부한 단언을 얻는다.

## Red Flags

- 감사/인수인계가 "0행이라 죽은 듯하지만 단정 안 함" 으로 넘긴 항목
- 같은 이름이 테이블 · 모듈 · 라우트 여러 층에 있어 grep 건수가 비정상적으로 큼
- 컴플라이언스/정책/SLA 문구가 **하드코딩 문자열**이고 그 숫자가 코드에 없음
- 테스트가 `assert "retention" in body` 처럼 **키만** 확인
- 같은 파일에 *"never steered anything"*, *"producer-less"*, *"nothing writes it"*
  같은 주석이 **이미** 있음 — 그 파일은 이 병의 상습지다
- 인수인계가 "지우려면 따로 재라" 라고 적어둠 → 재는 김에 **말하는 곳도** 세라

## Related

- [[production-object-never-constructed-not-just-unwired]] — 생성 지점이 0개인 객체
- [[deletion-pr-needs-an-absence-guard-and-a-control]] — 지우기로 한 뒤의 기계적 절차
- [[config-menu-offers-options-nothing-implements]] — 메뉴에 있는데 구현이 없는 쪽(거울상)
- [[a-lesson-fixed-in-one-failure-path-does-not-travel-to-the-others]] — 같은 파일이 두 번 고치고 세 번째를 남긴 이유
- [[a-check-that-cannot-flip-is-not-measuring-anything]] — 키 존재만 보는 단언이 왜 영원히 초록인지
