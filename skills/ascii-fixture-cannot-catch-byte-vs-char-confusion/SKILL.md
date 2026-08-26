---
name: ascii-fixture-cannot-catch-byte-vs-char-confusion
description: 두 단위가 우연히 같아지는 픽스처("x"*N, 정수 1.0, UTC 자정)로 만든 테스트는 단위 혼동을 영원히 못 잡는다 — 계약이 단위를 말하면 픽스처는 그 단위가 갈라지는 값을 써야 한다.
category: trap
---

# 단위가 겹치는 픽스처는 단위 혼동의 알리바이가 된다

## Problem

계약이 **단위**를 명시하는데(바이트 · 밀리초 · 센트 · UTC) 구현이 다른 단위로
세고 있다. 테스트는 있고, 통과한다.

- **증상**: 상한/예산/변환에 테스트가 붙어 있는데 실제로는 넘는다. 특정 로케일·
  데이터에서만 드러나 "환경 문제"로 오진된다.
- **근본 원인**: 픽스처가 **두 단위를 같은 숫자로 만드는 값**을 쓴다. ASCII 문자열은
  `len(s) == len(s.encode())` 라서, 바이트 계약을 문자로 센 구현도 영원히 통과한다.
- **흔한 오해**: *"상한 테스트가 있으니 상한은 지켜진다."* 있는 것은 테스트가 아니라
  **알리바이**다.

## 실측 (BSVibe #825, 2026-08-26)

CI 파일을 LLM 프롬프트 근거로 읽는 함수. 예산은 **바이트**로 선언돼 있다
(`_CI_CTX_BYTES = 8*1024`, `_CI_TOTAL_CTX_BYTES = 24*1024`).

```python
# 읽기는 바이트 — 맞다
data = await box.read_file(path, min(_CI_CTX_BYTES, remaining))
# 보관은 문자를 자르고
text = data.decode("utf-8", errors="replace").strip()[:remaining]
# 차감도 문자를 뺀다  ← 여기
remaining -= len(text)
```

기존 테스트:

```python
box = _Box({f".github/workflows/w{i}.yml": "x" * 200_000 for i in range(5)})
ci = await svc._read_ci_declarations(box)
assert sum(len(v) for v in ci.values()) <= _CI_TOTAL_CTX_BYTES   # ASCII → 항상 통과
```

한국어 CI 파일로 바꿔 재니 **청구 13,655 / 실소비 40,965B**, 예산 24,576B 의
**1.67배**. 파일당도 8,193B(상한 8,192) — `errors="replace"` 가 넣는 U+FFFD 가
3바이트라서다. 이 초과는 곧 다른 근거를 프롬프트에서 밀어낸다
(→ `llm-grounding-additions-can-evict-existing-grounding`).

## Solution

1. **픽스처가 두 단위를 갈라놓게 하라.** 계약 단위로 단언하라.

```python
box = _Box({f".github/workflows/w{i}.yml": "가" * 200_000 for i in range(5)})
spent = sum(len(v.encode("utf-8")) for v in ci.values())   # 계약 단위로 센다
assert spent <= _CI_TOTAL_CTX_BYTES
```

2. **한 층만 고치지 마라.** 읽기 상한 · 자르기 · 차감이 **전부** 같은 단위여야 한다.
   층마다 테스트를 따로 두면 음성 대조군이 자동으로 생긴다.
3. **자를 때는 계약 단위로 자르고 경계를 지켜라.**

```python
def _clamp_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")  # 쪼개진 꼬리는 버린다
```

4. **음성 대조군 2층**: ① 클램프를 no-op 으로 → 파일당 테스트만 실패
   ② 차감을 문자로 되돌림 → 총량 테스트만 실패. 서로 안 겹쳐야 각 층이 독립적으로
   고정된 것이다.

## Key Insights

- **테스트의 존재는 계약의 증거가 아니다.** 픽스처가 계약을 구분할 수 있는지를 봐라.
- **`errors="replace"` 는 데이터를 늘린다.** 바이트로 자른 뒤 디코드하면 대체 문자가
  들어가 재인코딩 크기가 상한을 **넘을 수 있다.** 자르기 → 디코드 → 재측정 순서로.
- 같은 함정의 형제들: 초 vs 밀리초(둘 다 1일 때 통과) · 달러 vs 센트(1.00) ·
  로컬 vs UTC(UTC 자정 기준 픽스처) · 0-based vs 1-based(길이 1 리스트) ·
  퍼센트 vs 비율(값 1). **픽스처를 "1" 또는 "ASCII" 로 잡는 순간 의심하라.**
- 다음에 먼저 확인할 것: **상수 이름이 단위를 말하는가**(`*_BYTES`, `*_MS`,
  `*_CENTS`) → 그렇다면 그 단위로 단언하는 테스트가 있는지, 그리고 그 픽스처가
  단위를 갈라놓는지.

## Red Flags

- 상수 이름이 `_BYTES` / `_MS` / `_CENTS` 인데 근처 코드가 `len(str)` 를 쓴다
- 테스트 픽스처가 `"x" * N` · `"a" * N` · `1` · `1.0` · UTC 자정이다
- 예산/상한 로직에서 **읽는 곳과 차감하는 곳의 표현이 다르다**
  (`bytes` 를 읽고 `str` 을 뺀다)
- 버그가 "특정 언어/로케일에서만" 난다고 보고된다
- 자기 레포 데이터로는 재현이 안 된다 — 그런데 그 코드는 **임의의 입력**을 받는다
