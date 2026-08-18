---
name: agent-degraded-output-suspect-execution-environment
description: When a capable agent first declares a STRONG plan/contract/approach then a retry or continuation produces a WEAKER one, suspect the execution environment couldn't run the strong version — not model laziness or a prompting gap.
---

# Agent declares strong, then degrades → suspect the execution environment

## Problem

An LLM agent with a declare→execute split (declares a verification
contract / a plan / a tool sequence, then carries it out) produces a
**weak** final artifact. The obvious first hypothesis — "the model is
lazy / the prompt is too soft / it doesn't follow instructions" — is
often **wrong**.

- 증상: the agent declares something strong (`pytest`, a real test
  command, a thorough plan), the run fails or hits a round cap, and a
  retry / continuation re-declares a **weaker** version (`py_compile`,
  an `import`-only check, a trivial plan) that *does* pass.
- 근본 원인: the strong version was **un-runnable in the agent's
  execution environment** — a missing toolchain, a read-only path, a
  permission wall, a placeholder that didn't resolve. The agent ran
  the strong command, saw it fail, and *rationally* degraded to
  something the broken environment could satisfy.
- 흔한 오해: blaming prompt strength → you strengthen the prompt, the
  agent declares strong AGAIN, it still can't run it, and it degrades
  AGAIN. Prompt engineering cannot fix an environmental wall.

Real case (BSNexus, 2026-05): the work LLM's `shell_exec` ran in a
backend container with no `pytest`/`ruff`. qwen3 declared a strong
`pytest` contract (A1 prompt work succeeded), spent 36 rounds unable
to run it (`pip install` blocked — read-only site-packages), hit the
loop cap; the Tier-1 continuation then re-declared an `import`-only
contract that matched the broken environment. The deliverable reached
`verified` with its tests never run. The fix was environmental (give
the work phase the toolchain — a sandbox), not prompting.

## Solution

When you see declare-strong-then-degrade, **diagnose the environment
before touching the prompt**:

1. Take the STRONG thing the agent declared on the first attempt and
   run it *yourself*, by hand, in the exact environment the agent
   runs in (same container, same user, same cwd, same PATH).
2. If it fails — missing binary (exit 127), `Permission denied`,
   read-only FS, an unresolved `<placeholder>` token — that is the
   root cause. The agent isn't lazy; it's adapting to a broken env.
3. Fix the environment (install the toolchain, fix ownership, resolve
   the placeholder, mount the volume) — not the prompt.
4. Re-verify: the agent should now declare strong AND the strong
   version should run.

Inspect the agent's tool-call trace (e.g. `tool_events`): a run that
shows the agent *trying* the strong command, getting errors, then
`pip install` attempts, then falling back — is the signature.

## Key Insights

- A capable agent degrading its own output is usually **rational
  adaptation to a broken environment**, not a compliance failure. The
  agent saw the strong path fail and routed around it.
- The declare→execute split makes this sneaky: the *declaration* looks
  fine (prompt worked), so you don't suspect the prompt is innocent.
  The break is between declare and execute.
- Prompt engineering has a hard ceiling here — re-nudging a model to
  declare strong does nothing when the environment can't run strong.
  Same family as `local-llm-runtime-nudge-ceiling`.
- First diagnostic move: **run the agent's own first-attempt strong
  command by hand in its environment.** One command tells you env-vs-
  prompt.

## Red Flags

- A retry / continuation / fallback attempt produces a *simpler* or
  *weaker* artifact than the first attempt.
- The agent's trace shows it tried tool/command X, got an error, then
  switched to a weaker Y.
- `pip install` / `npm install` / `apt` attempts mid-run (the agent
  is trying to repair a missing toolchain itself).
- "The model just won't do X" after you've already strengthened the
  prompt once.
- A verification / gate passes via a check that doesn't actually
  exercise the deliverable (compile-only, import-only, `--help`).

---

## 사촌 증상 — "게으른 에이전트"가 사실은 **안 돈 하류 단계**일 때

앞의 내용은 *한 런 안에서* strong→weak 로 떨어지는 경우다. 다단계 파이프라인
(design→impl, plan→build, extract→transform)에는 **같은 오진의 다른 모양**이 있다:

- **증상**: 코드를 요청했는데 **명세 문서 하나**가 나오고 런은 `verified` / 완료로 끝난다.
  "에이전트가 일을 회피했다 / 지시를 안 따랐다" 로 읽힌다.
- **실제**: 상류 단계(design)는 **제 일을 정확히 했다.** 명세를 쓰는 게 그 단계의 산출물이다.
  깨진 것은 **하류 단계(impl)가 아예 스폰되지 않은 것**이다.

### 왜 오진하기 쉬운가

파이프라인이 살아 있을 때와 죽었을 때의 **상류 산출물이 완전히 동일**하다.
차이는 "그 다음에 무엇이 생겼나" 뿐인데, 사람은 눈앞의 산출물만 본다.
게다가 상류 런은 정상 종료라 **에러도 로그도 없다.**

### 먼저 확인할 것 (에이전트를 의심하기 전에)

```sql
-- 1) 이 런은 다단계로 분류됐나?
select payload->'frame'->>'pipeline', payload->>'stage' from execution_runs where id = '<run>';

-- 2) 하류 런이 실제로 생겼나?
select count(*) from execution_runs where payload->>'design_run_id' = '<run>';

-- 3) 같은 축으로 시계열 — 언제부터 안 생겼나?
select created_at::date, count(*) from execution_runs
where payload ? 'design_run_id' group by 1 order by 1;
```

3번이 결정적이다. **어제까지 되던 게 오늘 0이면 에이전트 문제가 아니다.**

### 실제 사례 (BSVibe, 2026-08-18)

`worker_runtime.py` 리팩터링을 요청했고 (*"순수 리팩터링, 동작 변경 금지, 기존 테스트
전부 통과가 수락 조건"*) `spec_..._split.md` 하나가 나왔다. 처음엔 **에이전트의 회피**로
진단하고 "산문 산출물" 검사를 조이는 수정에 착수했다 — **틀렸다.**

시계열을 세니 체이닝된 impl 런이 **전날 1건 → 당일 0건**. 전날 삭제된 라우팅 룰이
체이닝 게이트의 암묵적 피처 플래그였다.
→ `deleting-inert-config-row-disables-hidden-feature`

**착수했던 "회피 방지" 수정은 폐기했다.** 그 수정을 넣었으면 정상적인 design 단계
산출물까지 전부 사람을 호출하는 **과잉 파킹**이 됐을 것이다(역대 파킹 8건 중 4건이
바로 그 정당한 design 단계였다).

> **교훈: 에이전트를 고치는 수정에 착수하기 전에, 그 산출물이 "어느 단계의 정상 산출물"
> 인지부터 확인하라.** 단계를 모른 채 산출물만 보면 정상을 결함으로 읽는다.
