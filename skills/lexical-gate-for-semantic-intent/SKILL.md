---
name: lexical-gate-for-semantic-intent
description: 에이전트 시스템에서 "질문인가 작업인가" 같은 의미(semantic) 판단을 키워드/의문사/동사 목록으로 대신하면, 문법만 읽고 의도를 놓쳐 오분류된다. 그리고 오분류의 대가가 크다 — 만들 게 없는 코딩 에이전트는 no-op 하지 않고 아무 코드나 고쳐서 ship 한다. 트리거: intent 라우팅, 질문/작업 분기, path_classification, is_question(), 빌드동사 목록, 다국어 입력.
---

# Lexical Gate for Semantic Intent — 문법을 읽고 의도를 놓친다

## Problem

에이전트 파이프라인에는 거의 항상 "이 요청은 **답변**인가 **작업**인가" 분기가 있다
(BSVibe: `path_classification: knowledge_only | agent_loop`). 이 판단을 결정론적으로
만들고 싶은 유혹이 크다 — LLM 없이도 동작하고, 유닛테스트가 쉬우니까. 그래서 이렇게 된다:

```python
_KO_QUESTION_CUES = ("어때", "어떻게", "무엇", "까요", "습니까", ...)   # 24개
_EN_INTERROGATIVES = {"what", "how", "why", "is", "can", ...}
_KO_BUILD_STEMS = ("만들", "구현", "추가", "수정", ...)

def _looks_like_question(text):
    if "?" in text: return True
    if any(cue in text for cue in _KO_QUESTION_CUES): return True
    return text.split()[0] in _EN_INTERROGATIVES
```

- **증상**: "현 프로젝트 상황 **설명해줘**" → `agent_loop` → 코딩 executor 실행 → 리포에서
  **무관한 파일을 골라 고치고** verify 통과시키고 승인 대기까지 올림. 유저는 "질문했는데 왜
  엉뚱한 작업을 하냐"고 함.
- **근본 원인**: `설명해줘`/`알려줘`/`explain X`/`教えて` 는 **말해달라는 정중한 명령형**이다.
  의도는 질문, 문법은 명령문. `?`도 의문사도 없으니 어떤 cue에도 안 걸린다. 목록은 **문법을
  읽지 의도를 읽지 않는다**. 그리고 한/영 외 언어는 애초에 사정권 밖.
- **흔한 오해 1**: "cue 하나만 더 추가하면 된다." — 그 목록은 *이미* 이전 프로덕션 사고
  ("지금 프로젝트 상황 **어때?**")를 막으려고 만들어진 것이었다. 어미 하나 다른 문장이 다시
  뚫렸다. N+1번째 키워드는 N+2번째 사고를 부른다.
- **흔한 오해 2**: "오분류돼도 에이전트가 할 일 없으면 그냥 멈추겠지." — **아니다.** 아래 참조.

## 오분류의 대가: 만들 게 없는 코딩 에이전트는 일을 지어낸다

이게 이 함정의 진짜 무게다. 질문을 코딩 executor에 넘기면 에이전트는 "작업 없음"으로
끝내지 않는다. 리포를 뒤져 **그럴듯한 개선점을 하나 찾아내 고치고**, 테스트를 돌리고,
"검증됨" 배지를 달아 승인 요청까지 만든다. 관측된 실제 diff:

```python
     bearer = ensure_claude_bearer()
     if bearer:
         env["ANTHROPIC_AUTH_TOKEN"] = bearer
+    else:
+        env.pop("ANTHROPIC_AUTH_TOKEN", None)
     return env
```

아무도 요청하지 않은, 그 자체로는 말이 되는 변경. 즉 **오분류 = 조용한 무단 코드 변경**이다.
분류기의 false-negative를 "약간 불편한 UX"로 견적내면 안 된다.

## Solution

1. **의미 판단은 LLM에게, 어휘 목록은 삭제.** 프레이밍 단계가 이미 LLM 호출을 하고 있다면
   판단할 자리는 거기다. 새 호출을 추가하지 말고 기존 호출의 출력 스키마에 얹어라.

2. **루브릭을 "무엇을 돌려받길 원하는가"로 정의.** 문법·어투·구두점·언어로 판단하지 말라고
   **명시적으로** 금지시켜야 한다. 이 문장이 없으면 모델도 문법에 끌려간다:

```python
ASK_VS_PRODUCE_RUBRIC = (
    "Decide by what the founder wants BACK — never by grammar, mood, punctuation, "
    "or language:\n"
    "- ASK: they want to be TOLD something — status, an explanation, a summary, an "
    "opinion. The reply itself IS the deliverable. This holds when the ask is phrased "
    'as a command ("explain the routing", "상황 설명해줘", "状況を教えて"), and it holds '
    "even when answering requires consulting the knowledge base or recorded state.\n"
    "- PRODUCE: they want something MADE or CHANGED. Some artifact must exist or "
    "differ afterwards.\n"
    'When a request both produces and explains ("build X and tell me how it works"), '
    "producing wins: PRODUCE."
)
```
   마지막 tie-break 규칙("둘 다면 PRODUCE")이 "리드미에 dispatch 레이어 **설명 추가해줘**"
   (설명처럼 생겼지만 산출물이 바뀜) 같은 함정을 잡아준다.

3. **루브릭은 단일 상수로 공유.** 같은 판단을 하는 표면이 둘 이상이면(예: 인라인 `/ask`
   게이트 + 프레임 단계) 반드시 drift 난다. 상수 하나를 두 프롬프트가 import 하고,
   "이 상수가 프롬프트에 실제로 전달됐는지"를 테스트로 고정하라.

4. **판단 불가 = 명시적 에러. 기본값 금지.** 두 방향 기본값이 **모두** 파괴적이다:
   `agent_loop` 추측 → 질문이 코드가 됨. `knowledge_only` 추측 → 작업이 조용히 안 됨.
   - 모델이 이상한 출력 → 명시적 FAILED(사유 표시)
   - 모델 자체가 라우팅 안 됨 → 기존 "모델 선택 Decision"으로 **일시정지**(FAILED 아님).
     이미 있는 no-account UX에 합류시켜라 — 새 실패 모드를 만들지 말고.

5. **직교 신호는 coherence guard로 남긴다(단방향만).** "산출물 타입 = code/page/pr" 이면
   `knowledge_only` 판정을 뒤집는다(만들 게 있으면 작업이다). 단 **역방향은 금지**:
   `direct_output`은 "답변"과 "산문 산출물(블로그 글/리포트)"이 **둘 다** 쓰는 타입이라
   반대 방향으로 못 민다. 판단은 루브릭 몫.

## 프롬프트 수정은 실제 모델에 A/B 로 검증한다

프롬프트가 곧 로직이 되면 유닛테스트는 배선(verdict가 존중되는지, 없으면 raise 하는지)만
검증할 수 있고 **판단 품질은 못 본다**. 실제 프레임 모델에 old/new 프롬프트를 같은 케이스
세트로 걸어 비교하라. 배포 없이 컨테이너 안에서 어댑터만 직접 호출하면 된다:

```python
resolved = await _resolve_via_caller(session, caller_id=CALLER_FRAME,
                                     workspace_id=WS, settings=settings,
                                     redis=get_dispatch_redis_client(settings))  # executor 라우팅이면 redis 필수
for label, prompt in (("OLD", OLD_PROMPT), ("NEW", NEW_PROMPT)):
    for text, expected in CASES:   # 3개 언어 × (질문/작업/함정)
        turn = await resolved.adapter.chat(system=prompt, messages=[...], tools=None)
        ...
```

실측: **OLD 11/13 → NEW 13/13**, 그리고 OLD가 틀린 2개가 **정확히 프로덕션에서 터진 그 문장들**
이었다. 이 A/B 없이는 "프롬프트 고쳤음"은 그냥 주장이다.

## Key Insights

- 키워드 목록은 **의미 판단의 대역(proxy)이 아니라 문법 판단**이다. 정중한 명령형, 생략,
  다국어에서 반드시 깨진다. "결정론적이라 안전하다"는 정확히 거꾸로다 — 결정론적으로 틀린다.
- **오분류된 코딩 에이전트는 멈추지 않고 일을 지어낸다.** 분기 하나의 false-negative가
  무단 코드 변경 + 검증 배지 + 승인 요청으로 증폭된다.
- 목록에 항목을 추가하려는 손이 움직일 때, 그 목록이 **왜 처음 만들어졌는지** 보라. 이전
  프로덕션 사고를 막으려 만든 목록이라면, 지금 추가하려는 항목도 다음 사고를 못 막는다.
- 라우팅 재설계가 "어떤 **모델**을 쓸지"를 통합했다고 해서 "어떤 **종류**의 run인지"가
  통합된 건 아니다. 두 축은 다르다 — kind 결정이 아직 어느 구석의 word list에 남아있는지 확인하라.

## Red Flags

- `is_question()`, `_looks_like_question()`, `_BUILD_VERBS`, `_QUESTION_CUES` 같은 이름의
  함수/상수가 **실행 경로 분기**에 쓰이고 있다.
- 그 목록의 주석에 "prod dogfood가 이 문장에서 죽어서 추가함"이 적혀 있다 (= 이미 한 번 뚫렸다).
- 같은 heuristic이 2~3개 표면(API 게이트, LLM 구제 가드, no-LLM 폴백)에서 import 된다 (단일 실패점).
- 프레임/분류 LLM이 "산출물 없음"(`artifact_type_hint: null|direct_output`)이라고 말했는데
  실행 경로는 코딩 루프다 — 비일관. 로그/DB에서 이 조합을 grep 하면 오분류가 바로 나온다.
- 한국어/일본어 등 비영어 입력이 들어오는 제품인데 분류 로직에 언어별 substring 목록이 있다.
