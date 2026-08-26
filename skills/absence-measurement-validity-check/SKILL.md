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

---

## 사례 — **지표로 고른 테이블 자체에 producer 가 없었다** (BSVibe, 2026-08-20)

가장 비싼 형태다: 부재를 잘못 읽은 게 아니라, **부재를 재려고 고른 계기판이 애초에 안 꽂혀
있었다.**

`IngestCompiler` 가 `retriever=` 를 못 받아 눈멀어 있던 것을 고치고, PR 본문에 검증 방법을
이렇게 적었다 — *"배포 후 `ingest_batches` 의 `notes_updated` 가 0에서 움직이는지 보라."*
실제로 재보니:

| | |
|---|---|
| `ingest_batches` 행 수 | **0** |
| `IngestBatchRecorder` 프로덕션 구현체 | **0** (Protocol 선언만) |
| `batch_recorder=` 를 넘기는 생성 지점 | **0** |

**내가 방금 고친 결함과 똑같은 결함이 같은 생성자의 바로 옆 인자에 있었다.** 그 지표는
원리상 영원히 0이므로, 내 수정이 동작하든 안 하든 "검증 실패"로 읽혔을 것이다.

> **지표를 고르는 것도 측정이다. 계기판에 producer 가 있는지부터 세라.**

**처방** — 검증 지표(테이블/카운터/로그/이벤트)를 정할 때 **쓰기 전에** 확인:

```bash
# 1) 그 지표에 지금 값이 들어 있나 (역대 한 번이라도)
psql -tAc "select count(*) from <metric_table>"

# 2) 없다면 — 프로덕션 producer 가 존재하나
grep -rn "<RecorderClass>(" backend/ | grep -v tests   # 0개면 지표가 아니라 유령이다
```

0이면 **지표를 바꾸거나, 지표를 먼저 배선하라.** 그리고 "배선할지 지울지"는 대개 사람의
결정이다 — producer 없는 테이블은 *"연결이 빠진 것"* 이 아니라 *"만든 적 없는 두 번째 표현"*
일 수 있고, 그러면 답은 삭제다.

### 곁가지 함정 — 배포는 로그 히스토리를 자른다

같은 검증에서 `docker logs <worker> --since 12h | grep ingest_compile` 가 **0** 을 냈다.
결함으로 읽을 뻔했는데, 원인은 **배포가 컨테이너를 재생성**해서 그 이전 로그가 아예 없는
것이었다. 컨테이너 로그로 "일어난 적 없다"를 주장하려면 **컨테이너 시작 시각부터의 창**만
유효하다.

```bash
docker inspect -f '{{.State.StartedAt}}' <container>   # 이 시각 이후만 근거가 된다
```

### 또 하나 — 로그가 없다고 경로가 안 도는 게 아니다

`ingest_compile_batch_complete` 가 안 보여서 "settle 이 컴파일러를 안 탄다"로 결론낼 뻔했다.
코드를 읽으니 settle 은 `compile_batch` 가 아니라 `extract_entity_names` 를 타는데,
**그 메서드도 같은 `_find_related` 를 부른다** — 로그만 안 남길 뿐 경로는 돈다.
**관측 장치의 부재를 동작의 부재로 읽지 마라.**

### 실험 판(arm)이 **전부 똑같이** 0 을 내면 처치가 아니라 하네스를 의심하라

BSVibe 2026-08-26. 프롬프트 버전을 변수로 A/B 를 돌렸다 — arm 4개 × 입력 3건 = 12셀.
**전부 명령 0개**가 나왔다. "옛 프롬프트는 이 검사를 낼 능력이 없다"로 읽힐 수 있는
모양이었고, 실제로 그렇게 적을 뻔했다.

원인은 처치가 아니라 **배선**이었다: 프로브가 resolver 에 redis 를 안 넘겨서 12셀 전부
`ExecutorAdapterUnavailable` 로 죽었다. LLM 이 한 번도 호출되지 않았다.

**감별 규칙 — 처치 효과는 균일할 수 없다.**

| 관측 | 읽는 법 |
|---|---|
| arm 마다 0 의 **정도가 다르다** | 진짜 처치 효과일 수 있다 |
| **모든 arm 이 정확히 같은 0** | 하네스/배선 고장. 처치는 아직 안 재봤다 |
| 통제(control) arm 까지 0 | 확정적으로 하네스 고장 — 통제는 되던 것이어야 한다 |

**How to apply**
- 실험 결과에 **오류 필드를 남기고 집계에 함께 출력하라**. `error=None` 인 셀 수를
  먼저 보고 나서 효과를 봐라. 예외를 삼켜 0 으로 만들면 고장이 발견으로 위장한다.
- **알려진-양성 arm 을 반드시 하나 넣어라.** 지금 잘 되는 조건이 0 을 내면 그 판은
  통째로 버린다.
- n=1 스모크를 먼저 돌려 **배선을 확인**하고 나서 본 실행에 비용을 써라.
- 관련: [[ab-on-a-few-items-cannot-recover-a-population-rate]] — 하네스가 멀쩡해도
  **도구 자체가 질문에 안 맞을** 수 있다(모집단 비율을 몇 개 항목으로 물을 때).
