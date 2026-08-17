---
name: absence-measurement-validity-check
description: Before concluding "X doesn't happen" in an integrated system, verify the pipeline that would produce X is actually running. Measuring zero is trivially easy when the producer is off.
version: 1.0.0
task_types: [debugging, design, evaluation]
triggers:
  - pattern: "claim that a tool / feature / behavior isn't being used / fires zero times"
  - pattern: "longrun / E2E experiment showing 0 count of some event"
  - pattern: "prompt engineering attempt judged 'failed' because LLM didn't do X"
category: trap
---

# Absence Measurement Validity Check

## The Pattern

You run an experiment and observe `X = 0` (tool never called, artifact never created, path never hit). You conclude "X doesn't work / the prompt failed / the model has a limit".

This conclusion is only valid if the pipeline that would produce X is actually running. Otherwise you measured a system that can't produce X *at all*, not a system that chose not to.

## Real Example (BSNexus Session 10)

Goal: prove or disprove that GLM-4.7-flash can be prompted to call a verification tool (`shell_exec`) via TDD-style instructions.

Measurement loop, three iterations:

| Run | Prompt strategy | `shell_exec_ran` count | Conclusion I drew |
|---|---|---|---|
| v8 | direct "MUST verify" instruction | 0 | "direct instruction doesn't work" |
| v9 | Q1/Q2/Q3 CoT scaffold | 0 | "CoT doesn't work" |
| v10 | E2E reframing + file_read banned | 0 | "prompt-layer ceiling hit" |

Three "failed" prompt strategies in a row. Looks decisive.

What I missed: the user pushed me to run V11 patiently and query the DB directly. Results:

- **Assigned agents**: Designer 8, CTO 4, Marketer 3, Backend_Engineer 1, Frontend_Engineer 1, QA_Lead 1… (routing was **working**)
- **`file_read` calls**: 22 (passive workers were **active**, calling other tools)
- **`create_screen` / `file_write`** also firing normally
- **`shell_exec`**: 0

The passive-worker pipeline was fine. The `shell_exec` absence was a real GLM tool-preference signal, but I could not have known that from v8/v9/v10 — I didn't check whether the pipeline that *could* use `shell_exec` was even dispatching. For all I knew from those three runs, every task was self-assigned to the planning agent and no passive worker was running at all.

## Why This Traps You

- `X == 0` reads like a clean data point. It feels like certainty.
- Positive signals are loud (logs, state transitions, artifacts); absence is invisible. There's nothing to question, only something missing.
- Repeating the same measurement under different prompts **does not** increase confidence in the conclusion. All three runs can be contaminated by the same upstream gap.
- A later negative result that's real confirms the wrong early reasoning, so the lesson never surfaces.

## The Validity Check — Before Claiming Absence

Before writing down "X didn't happen → Y caused it", verify three layers:

1. **Producer liveness**: is the process that would emit X actually dispatched/active in this run? Check logs for "its kind of event happened at all", not just the specific signal.

2. **Sibling signals**: does the same code path emit *anything*? If the producer fires same-category events successfully (other tool calls, other file writes), you're comparing "made a choice not to" vs "never got the chance". Different conclusion, different fix.

3. **Artifact vs state**: state transitions (`status=done`, `phase=completed`) are cheap to fake. File-level / command-level artifacts are what matter. Query the DB / filesystem directly; don't trust API responses that might be showing creator vs assignee, cached vs live, etc.

Only after those three layers check out is `X = 0` evidence of intentional absence rather than blocked pipeline.

## Heuristic

> If your measurement is "how often did the LLM / agent / process do X?", and X is zero across N runs, your first follow-up question must be: **did the thing that produces X even execute?** Query the producer's *sibling* signals. If the siblings are also zero, the pipeline is dead; the experiment was invalid and the prompt / model / feature has not actually been tested.

## When This Skill Applies

- Multi-agent systems where a tool might be offered but never called
- Any E2E test claiming "feature X didn't fire"
- Prompt engineering iterations producing the same null count
- Backend enforcement rules that supposedly triggered no rejections
- Dashboards showing a suspicious zero when activity is expected

## When It Does NOT Apply

- Unit tests with synthetic input (the pipeline is explicit)
- Experiments where the producer is obviously controlled (the call site is in your test code)

## Related Skills

- `systematic-debugging` — broader root-cause investigation; this skill is the "check absence first" corner of it.
- `verification-before-completion` — the inverse problem (premature success claims); this one covers premature failure claims.
- `test-against-source-contracts` — when API field semantics confuse you (e.g., `agent_name` returning creator vs assignee), this ties in.

---

## 사례 — **측정 명령 자체가 실패했을 때** (2026-08-17)

이 스킬은 "0을 만들어내는 *생산자*가 도는가"를 묻는다. 그 한 겹 아래에 더 흔한 것이 있다:
**측정 명령 자체가 돌기는 했는가.**

BSVibe 실측. 레포 루트의 임시 파일 5개를 지우기 전에 참조를 확인하려고:

```bash
grep -rn "_patch_judge\|_patch_parse" --include=*.py backend/ tests/
# → (zsh) no matches found: --include=*.py     ← 명령이 죽었다
```

zsh 가 `--include=*.py` 를 글롭으로 먹어 **명령이 실행되지 않았다.** 출력은 비어 있었고,
나는 그 공백을 **"아무도 참조하지 않는다"** 로 읽고 파일을 지웠다.

> **빈 출력은 "없음"이 아니다. 그 명령이 실행됐다는 증거가 먼저 필요하다.**

제대로 다시 돌리니 13개 파일이 매칭됐다(전부 `monkeypatch_resolver` 같은 무관한 부분
문자열이라 삭제는 결과적으로 안전했지만, **그건 운이었다**). 삭제·머지·배포처럼 **비가역**
동작 앞에서는 이 확인이 필수다.

**처방**

- 부재를 근거로 행동하기 전에 **양성 대조**를 하나 끼워라 — 반드시 매칭될 문자열로 같은 명령을
  돌려 **0이 아닌 결과**가 나오는지 본다. 안 나오면 명령이 죽은 것이다.
- 종료 코드를 봐라. `grep` 의 "매칭 없음"은 1, **오류는 2**다. 셸이 죽였으면 그마저 안 나온다.
- 셸 확장이 개입할 수 있는 인자(`*`, `?`, `[`)는 **따옴표로 감싸라**.

```bash
# 양성 대조를 같이 돌린다
grep -rn "_patch_judge" backend tests; echo "exit=$?"
grep -rn "def test_" tests | head -1        # ← 이게 비면 명령이 죽은 것이다
```

**Detection**: 빈 출력을 근거로 **삭제/정리/롤백**을 하려 한다 · 셸 오류 메시지가 출력에 섞여
있는데 결과부만 읽었다 · `tail`/`head` 로 잘라 보느라 앞의 에러를 못 봤다(같은 세션에서
`ruff` 의 F821 을 `tail` 로 놓쳐 85개 테스트를 깨뜨렸다).
