---
name: agentic-cli-as-llm-transport
description: 코딩 CLI(claude/codex/opencode)를 "LLM 호출 transport"로 감싸 쓸 때, chat 턴까지 agentic 모드로 띄우면 에이전트가 자기 빈 샌드박스를 뒤져서 그걸 답변한다. 주입한 grounding은 자기 툴이 "본" 것에 밀린다. 툴을 끄는 게 유일한 해결. 트리거: ExecutorAdapter/LLM proxy/chat() 추상화, "왜 답변이 빈 디렉터리 얘기를 하지", chat 호출 타임아웃.
---

# Agentic CLI as an LLM transport — chat 턴은 툴을 꺼야 한다

## Problem

구독형 코딩 CLI(claude code, codex, opencode)를 API 키 대신 **LLM 호출 transport**로 쓰는
아키텍처는 흔하다. 추상화는 보통 이렇게 잡는다:

```
ModelAccountAdapter.chat(system, messages, tools) -> ChatResponse
  ├─ LiteLLMAdapter   → provider API 직접 호출
  └─ ExecutorAdapter  → worker 로 CLI subprocess 디스패치
```

**설계 의도**: 두 어댑터는 동일하게 동작한다(parity).
**실제**: worker 가 CLI 를 띄울 때 `--permission-mode acceptEdits` 같은 **agentic 모드**를
그대로 쓰면, chat 턴(질문 답변·프레이밍·요약)도 **에이전트 런**이 된다.

- **증상 1 — 답변이 자기 샌드박스 얘기를 함.** "현 프로젝트 상황 설명해줘" →
  *"현재 작업 디렉토리(`/private/var/.../task-xo_or5hs`)는 완전히 비어 있는 임시
  디렉토리입니다. 파일 없음, git 저장소 없음"*. 실제 프로젝트는 repo 도 있고 노트 330개도
  있는데. per-task 작업 디렉터리가 비어 있으니 **사실 그대로** 답한 것.
- **증상 2 — chat 호출이 타임아웃.** 단순 질문 하나에 CLI 세션 부팅 + 툴 루프 → 300s 초과.
- **근본 원인**: 코딩 에이전트는 **자기 툴이 관측한 것 > 시스템 프롬프트**로 신뢰한다.
  grounding 을 아무리 정성껏 주입하고 "working directory 를 들여다보지 마라"라고 써도,
  툴이 있으면 `ls` 를 하고 그 결과를 믿는다.
- **흔한 오해**: "프롬프트로 타이르면 된다." → 안 된다. 실측으로 확인됨.
- **더 위험한 오해**: "CLI 가 agentic 하니 chat-shaped caller 는 다른 백엔드(직접 API)로
  라우팅하자." → 이건 **증상 회피**다. parity 가 제1원칙이면 라우팅을 쪼개는 순간 원칙이
  무너지고, executor 만 있는 워크스페이스는 영원히 깨진 채로 남는다.

## Solution

**`tools` 인자가 이미 정답 신호다.** LiteLLM 은 `tools=None` 이면 아무것도 못 하고 프롬프트로만
답한다. executor 도 똑같이 만들면 parity 가 성립한다.

1. 어댑터에서 `agentic = bool(tools)` 를 산출해 태스크에 실어 보낸다
   (adapter → task row(+migration) → dispatch payload → worker context).
2. worker 의 CLI 빌더가 이를 이행한다:

```python
cmd = [claude, "--print", "--output-format", "stream-json"]
if agentic:                      # 에이전트 런: 샌드박스 툴 유지
    cmd += ["--permission-mode", "acceptEdits", "--settings", CONFINED]
else:                            # chat 턴: 툴 전면 차단 = 순수 completion
    cmd += ["--disallowedTools", "Bash Read Write Edit Glob Grep Task WebFetch ..."]
```

3. **기본값은 agentic=True.** 구버전 백엔드가 보낸(플래그 없는) 태스크는 에이전트 런으로
   —  코딩 루프가 조용히 툴을 잃으면 빈 diff 를 ship 한다.

## 코드 짜기 전에 실제 CLI 로 A/B 하라

이 판단은 CLI 벤더 문서가 아니라 **실측**으로만 확정된다. 빈 임시 디렉터리 + 동일 grounding 으로:

```bash
cd $(mktemp -d)
claude --print --model sonnet --append-system-prompt "$GROUNDING" "현 프로젝트 상황 설명해줘"
#  → "완전히 비어 있는 임시 디렉토리입니다"   (툴이 cwd 를 봄)

claude --print --model sonnet --disallowedTools "Bash Read Glob Grep Edit Write WebFetch Task" \
       --append-system-prompt "$GROUNDING" "현 프로젝트 상황 설명해줘"
#  → grounding 그대로 요약한 정확한 답변      (툴 없음 = 프롬프트만)
```

플래그 이름은 반드시 `--help` 로 확인할 것(추측 금지 — [[external-cli-wrapper-contract-drift]]).

## Key Insights

- **에이전트는 자기 툴이 본 것을 프롬프트보다 신뢰한다.** "빈 작업 디렉터리"는 거짓말이 아니라
  그 에이전트가 아는 유일한 사실이었다. 답변이 이상하면 "모델이 멍청한가" 이전에 **"모델이 무엇을
  볼 수 있었나"** 를 물어라.
- **추상화가 이미 답을 갖고 있는 경우가 많다.** `tools=None` 은 "행동하지 말고 답하라"는 뜻인데,
  transport 가 그 의미를 아래로 전달하지 않아 parity 가 깨졌다. 새 플래그를 발명하기 전에
  **기존 인자의 의미가 끝까지 전달되는지** 확인하라.
- **parity 원칙이 있으면 라우팅 분리는 우회일 뿐이다.** "이 백엔드는 chat 에 안 맞으니 다른 데로
  보내자"는 처방은 원칙을 무너뜨린다. 깨진 건 백엔드가 아니라 그 백엔드의 chat 구현이다.
- 답변 품질 문제는 대개 **모델이 아니라 grounding 파이프라인**이다. 이번엔 (1) 툴이 grounding 을
  이기고 (2) retriever 가 노트 **경로만** 주고("Related note — path", 검증 경로용 포인터)
  (3) 인라인 경로는 semantic 검색을 아예 안 붙임 — 3중 결함이 한 증상으로 보였다.

## 배포 검증 함정 — "컨테이너 배포했는데 왜 그대로지?"

이 아키텍처는 코드가 **두 군데**서 돈다. 고친 코드가 어느 프로세스에 속하는지 먼저 확인하라.

| 코드 | 실행 위치 | 반영 방법 |
|---|---|---|
| 어댑터/디스패치/API | backend·worker **컨테이너** | 이미지 재빌드 + recreate |
| **executor CLI 래퍼**(claude_code.py 등) | **호스트 launchd 워커** | **launchd 워커 재시작** (`launchctl kickstart -k`) |

컨테이너만 재배포하고 "왜 아직 옛 동작이지?" 하며 코드를 다시 의심하기 쉽다. 호스트 워커는
보통 repo 를 editable install 로 물고 있어서 **재시작해야** 새 코드를 빌드한다.

## 라이브 로그가 유닛 테스트보다 정직하다

grounding 파이프라인을 고친 뒤 라이브에서 확인했더니 `answer_grounding_note_unreadable`
경고가 hit 마다 찍혔다 — **vault 는 절대경로를 요구하는데 retriever 가 상대경로 ref 를 그대로
넘긴 것**. 유닛 테스트는 vault 를 dict 스텁으로 흉내내 **내가 넘긴 그 키를 그대로 받아줬기
때문에** 초록이었다. 저장소/vault 처럼 **경로 경계 검증이 있는 컴포넌트는 진짜 객체로 테스트**하라
([[test-against-source-contracts]], [[mock-fixtures-hide-wiring-bugs]]).

그리고 `factory.vault_path()` — 프로퍼티를 메서드로 호출 — 는 **`mypy --strict` 가 잡았다**.
CI 가 돌리는 게이트(ruff/format/lint-imports/mypy/pytest)를 **푸시 전에 그대로 로컬에서** 돌려라.

## Red Flags

- chat 호출인데 응답이 **파일/디렉터리/git 상태**를 언급한다.
- 단순 질문 하나가 수십 초~수 분 걸리거나 executor timeout 으로 죽는다.
- 어댑터 docstring 엔 "a chat turn is not a code-running task" 라고 써 있는데 **worker 쪽엔
  그 구분을 받는 코드가 없다** (설계 의도와 실행 경로의 괴리 — grep 해서 확인하라).
- chat 태스크의 per-task workspace 가 `mkdtemp()` 빈 디렉터리다 (= 에이전트가 볼 게 없다).
- "chat-shaped caller 는 다른 모델로 라우팅해서 회피" 같은 과거 결정이 메모/문서에 남아 있다.
