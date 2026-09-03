---
name: a-never-walked-checklist-item-may-be-unbuildable
description: 한 번도 안 걸어본 E2E 체크리스트의 `- [ ]` 는 "아직 확인 안 함"이 아니라 "제품이 만들 수 없는 상태를 적어둔 문장"일 수 있다 — 그리고 유닛 스위트가 자식 컴포넌트를 직접 렌더하며 부모가 절대 안 주는 조합을 넣고 있으면, 코드도 문서도 초록인 채로 그 거짓이 산다. 트리거 - 미체크 항목이 오래 남은 체크리스트, "유닛은 다 통과인데 라이브는 안 걸어봄", 자식 컴포넌트를 직접 렌더하는 테스트, 문서가 약속한 UI 상태를 못 찾을 때, 감사/인수인계가 넘긴 미검증 목록.
---

# 미체크는 "안 재봤다"가 아니라 "못 만든다"일 수 있다

## Problem

BSVibe 2026-09-03. `docs/e2e/pwa-onboarding-checklist.md` 는 이렇게 생겼다:

```markdown
## Behavior (unit-verified — Vitest/RTL)
- [x] ... (6개 전부 체크)

## Live E2E (staging/prod PWA, a fresh workspace)
- [ ] 0 제품·0 워커 → 온보딩 체크리스트가 뜬다
- [ ] "Set up a worker" 링크가 Settings → Models → Executor workers 로 딥링크
- [ ] 제품을 만들면 "첫 제품 만들기" 단계가 ✓ 로 바뀐다
- [ ] ...
```

나는 이 `- [ ]` 들을 **"검증 부채"** 로 읽었다. 걸어보니 그중 **둘은 프로덕션이
만들 수 없는 상태**를 적고 있었다 — 부채가 아니라 **거짓**이었다.

## 실측

**① "제품을 만들면 단계가 ✓ 로 바뀐다"**

```tsx
// BriefContent.tsx — 부모
const firstRun = !view.placeholder && !view.hasProducts && ...   // ← !hasProducts
{firstRun && <OnboardingChecklist hasProducts={view.hasProducts} ... />}
```

`firstRun` 이 `!hasProducts` 를 요구한다 ⇒ 제품이 생기는 순간 **블록이 통째로
사라진다** ⇒ 1단계의 ✓ 는 **도달 불가능한 상태**다. 그리고 더 나쁘게, 워커가
아직 없는 사용자가 제품을 만들면 **남은 단계의 안내까지 함께 사라진다** — 그
화면이 닫으려고 존재하는 블로커가 그 화면 안에서 살아 있었다.

**② "링크가 Models → Executor workers 로 딥링크"** — 링크는 `href="/settings"`
였고, 그건 General 탭으로 서버 리다이렉트된다. 워커 표면은 `/settings/models`.

## 유닛은 왜 전부 초록이었나

```tsx
// 기존 테스트 — 자식을 직접 렌더한다
it("checklist marks the worker step done when a live worker is connected", () => {
  render(<OnboardingChecklist hasProducts={false} hasLiveWorker={true} />);
  ...
});
```

자식을 직접 렌더하면 **부모가 절대 만들지 않는 prop 조합**을 자유롭게 넣을 수
있다. 그래서 컴포넌트는 `hasProducts=true` 를 완벽히 처리하는데, **부모는 그 값을
줄 때 컴포넌트를 아예 렌더하지 않는다.**

⇒ `unit-test-supplies-what-production-withholds` 의 UI 판본이다. 새로운 부분은
**문서가 그 거짓을 받아 적었다**는 것 — 체크리스트가 컴포넌트의 능력을 보고
사용자 시나리오처럼 써 놨다.

## 판정 근거는 코드 자신에 있었다

취향 논쟁이 될 뻔한 것을 **컴포넌트의 docstring 이 끊었다**:

> *"the whole block hides once the workspace **can actually produce** (handled by
> the parent)"*

생산하려면 워커가 있어야 한다. 즉 **부모가 컴포넌트의 계약과 다른 것을 구현**하고
있었다. 계약 위반이므로 고친다: `!(hasProducts && hasLiveWorker)`.

⇒ **UI 결함이 "디자인 취향"인지 "결함"인지 헷갈릴 때, 컴포넌트/모듈 자신이
적어둔 계약을 먼저 찾아라.** 거기 답이 있으면 논쟁이 아니라 수정이다.

## 규칙

1. **미체크 항목을 사양으로 읽지 마라.** 걸어보기 전엔 그것이
   (a) 참인데 미확인 · (b) **산출 불가능한 문장** · (c) 결함의 서술
   중 무엇인지 알 수 없다. 셋은 문서에서 **똑같이 생겼다.**
2. **UI 명제는 부모를 통과시켜라.** 자식 직접 렌더는 컴포넌트를 테스트하지
   *시나리오*를 테스트하지 않는다. 새 회귀 테스트는 **사용자가 실제로 도달하는
   진입점**에서 시작해야 한다.
3. **문서와 코드가 어긋나면 셋 중 하나로 끝내라** — 코드를 고치거나, 문서를
   고치거나, **왜 그 조합이 도달 불가인지**를 문서에 적거나. `- [ ]` 로 두면
   다음 사람이 다시 부채로 읽는다.
4. **걸으면서 내 단언이 틀리면 그것도 신호다.** 이 세션에서 내 E2E 단언 둘이
   틀렸는데, **그 하나를 고치는 과정에서 결함 ②가 드러났다**
   (`playwright-e2e-patterns` 의 "리다이렉트를 레이스하는 단언" 참고).

## 관련

* `unit-test-supplies-what-production-withholds` (메모리) — 같은 실명의 데이터 판본
* `seam-must-assert-what-the-consumer-sees`
* `verify-handoff-claims-against-code-before-building`
* `the-branch-behind-a-human-gate-was-never-run` — 같은 세션에서 나온 자매 결함:
  안 걸어본 것은 문서만이 아니었다
