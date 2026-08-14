---
name: truncated-diagnostic-shows-only-the-passing-half
description: 자동 소비자(에이전트·봇·CI)에게 실패 원인을 돌려줄 때 결과 객체 전체를 직렬화하고 앞에서 N자를 자르면, 통과 블록이 먼저 직렬화될 경우 "실패했다"면서 통과 목록만 보여준다. 소비자는 우회하지 않고 같은 실패를 무한 반복한다. 트리거 - 실패 피드백/에러 리포트/재시도 프롬프트를 만들 때, `json.dumps(result)[:N]` 같은 blind prefix, 동일 실패가 3회 이상 반복, 라인 번호가 안 움직이는 반복 실패, "어려운 작업인가 결함인가" 판단이 안 될 때.
---

# 잘린 진단은 통과한 절반만 보여준다

## Problem

- **증상**: 에이전트/봇이 같은 실패를 **바이트 단위로 동일하게** 반복한다. 겉보기엔
  "모델이 못 고치는 어려운 작업"으로 읽힌다.
- **근본 원인**: 실패 피드백이 **결과 객체 전체의 blind prefix** 다. 앞자리를 차지한
  블록이 통과한 검사면, 메시지는 누락이 아니라 **정면으로 거짓말**을 한다.
- **흔한 오해**: "정보는 result 안에 다 있다" → 있는 것과 **소비자가 받는 것**은 다르다.

### 실측 (BSVibe #751, run `010bbdd8`)

피드백이 이랬다:

```python
"Verification FAILED. Details:\n"
f"{json.dumps(verdict.result)[:1500]}\n"
"Fix the problem and try again."
```

| | |
|---|---|
| `json.dumps(verdict.result)` 전체 | **13,056자** |
| 앞 1500자의 내용 | 에이전트 **자기** 명령 4개 — 전부 `"passed": true` (verbose `pytest -v` 로그) |
| 진짜 실패(`no-untyped-def`) 위치 | **인덱스 3516** — 잘림 |

에이전트가 매 라운드 받은 것은 문자 그대로:

> **"Verification FAILED. Details: [전부 통과했음] Fix the problem and try again."**

결과: **41분, 16회, 같은 mypy 오류 3건, 같은 라인 번호.** 고칠 수가 없었다.

### 왜 하필 통과 블록이 앞에 왔나 — 이게 급소다

코드는 두 소스의 권위를 **명시적으로 구분**하고 있었다:

- `derived_gate` — 레포가 선언한 게이트. **authoritative**, 판정을 내림
- `command_results` — 에이전트 자기 신고. **advisory**, 아무것도 결정 안 함

그런데 **직렬화 순서는 advisory 가 먼저**였다. 즉 리포트는 *판정을 내린 필드를 자르고
아무것도 결정하지 않는 필드를 보여준다*. 순서는 아무도 의도하지 않았고 아무도 안 봤다.

### 증폭기: `ensure_ascii`

`json.dumps` 기본값 `ensure_ascii=True` 는 한글 1자를 `\uXXXX` **6자**로 부풀린다.
한국어 judge 사유 200자 = 예산 1200자. 비-ASCII 로그가 있으면 예산은 체감보다 6배 빨리 소진된다.

## Solution

**리포트를 자르지 마라. 실패만으로 조립하라.**

1. 실패한 항목만 뽑아 **권위 순서**로 배치 (authoritative → … → advisory 는 맨 뒤)
2. 통과 검사는 **한 줄 요약**으로만 — 어떤 양의 통과 출력도 실패를 밀어낼 수 없다
3. 텍스트를 **텍스트로** 렌더 (JSON 직렬화 금지 → `\uXXXX` 부풀림 제거)
4. 절단은 **양끝** 보존 — mypy 는 앞, pytest 는 뒤에 답을 둔다. head-only 는 도구에 따라 답을 잃는다
5. 모든 절단이 **몇 자 버렸는지 고지**
6. **실패가 하나도 식별 안 되면 그렇게 말하라** — 통과 목록을 대신 보여주는 것이 그 거짓말이다

```python
def _clip(text: str, limit: int) -> str:
    """양끝 보존 + 버린 양 고지."""
    if len(text) <= limit:
        return text
    template = "\n… {n} characters omitted …\n"
    room = limit - len(template.format(n=len(text)))
    if room <= 0:
        return text[:limit]
    head, tail = room * 2 // 3, room - room * 2 // 3
    return text[:head] + template.format(n=len(text) - head - tail) + text[-tail:]


def render_failure(result) -> str:
    sections = [block(c) for c in failed(result["derived_gate"]["commands"])]   # authoritative 먼저
    sections += [block(c) for c in failed(result["command_results"])]           # advisory 나중
    if not sections:
        return "실패했지만 어떤 검사도 실패를 보고하지 않았다 — 하네스 문제로 보인다."
    note = f"({passed_count}개 통과, 출력 생략.)"
    return _clip("\n\n".join(sections) + "\n\n" + note, BUDGET)
```

### 테스트는 렌더러 유닛으로 부족하다

렌더러만 단언하면 **루프가 그걸 실제로 쓰는지**는 여전히 미검증이다(같은 세션에서 이
구멍으로 결함 2개가 프로덕션에 나갔다). 실제 루프를 돌려 **LLM 스텁이 받은 메시지**를 읽어라:

```python
async def test_the_agent_receives_the_failure_on_its_next_turn():
    # 실패를 통과 출력 3000자 뒤에 일부러 배치 — 옛 blind prefix 라면 잘린다
    ...
    replan = llm.calls[-1]["messages"][-1]
    assert "MARKER_THE_AGENT_MUST_SEE" in replan["content"]
    assert "P" * 500 not in replan["content"]
```

그리고 **옛 표현으로 되돌렸을 때 그 테스트가 실제로 실패하는지 확인하라.** 확인 안 하면
그 테스트가 무엇을 잡는지 아무도 모른다.

## Key Insights

- **사람과 에이전트의 실패 모드가 다르다.** 사람은 안 보이면 딴 데를 뒤지거나 사람을 부른다.
  에이전트는 **주어진 것만 본다** — 우회하지 않고 예산이 끝날 때까지 같은 실패를 반복한다.
  그래서 "볼 수 없게 만드는 결함"은 인프라에서 **치명적**이다.
- **권위와 직렬화 순서는 별개다.** 어느 필드가 판정을 내리는지 코드가 명시해도, `dict` 삽입
  순서는 그것과 무관하게 정해진다. 자르는 순간 이 둘의 불일치가 결함이 된다.
- **조용한 캡은 누락이 아니라 거짓 주장이다.** "FAILED" 헤드라인 아래 통과 목록을 놓으면
  그 메시지는 사실과 반대되는 것을 단언한다.
- 예산 숫자를 키우는 건 처방이 아니다. **순서가 처방**이고, 예산은 이미 올바른 리포트의
  꼬리를 얼마나 남길지만 정한다.

## Red Flags

- **같은 실패가 3회 이상 반복되는데 오류 메시지·라인 번호가 한 글자도 안 바뀐다.**
  → "어려운 작업"이 아니라 **피드백이 안 닿는 것**을 먼저 의심하라. 라인 번호 고정이 스모킹건이다.
- 소비자가 실패 원인을 **자기 입으로 못 지목**한다("왜 실패했는지 모르겠다", "내 검사는 다 통과한다").
- 코드에 `json.dumps(...)[:N]` / `str(payload)[:N]` / `truncate(report, N)` 이 진단 경로에 있다.
- 리포트에 **권위가 다른 소스가 섞여** 있는데(authoritative gate vs self-reported), 렌더링이
  그 구분을 반영하지 않는다.
- 비-ASCII(한글·일본어·이모지) 로그가 들어가는 경로에 `json.dumps` 기본값을 쓴다.
- 소비자에게 가는 최종 문자열을 **아무도 출력해 본 적이 없다.**

## 확인 절차 (30초)

프로덕션 실제 payload 하나를 꺼내 **소비자가 받는 문자열을 그대로 찍어봐라.**

```python
body = render(actual_production_result)
print(body); print(len(body))
```

이 한 번이 이 결함을 즉시 드러낸다. 유닛 테스트 6000개가 못 잡은 것을 실물 출력 한 번이 잡는다.

## 관련

- `seam-must-assert-what-the-consumer-sees` — 생산자 쪽 추론만으로 소비자 계약을 정하는 실수
- `unit-test-supplies-what-production-withholds` — 조각을 단언하고 조립된 결과를 안 보는 실수
- `absence-measurement-validity-check` — 없음을 관측하기 전에 그것을 만드는 경로를 확인
