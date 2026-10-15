---
name: a-validated-field-beside-a-free-form-dict-is-not-validated
description: 사용자가 입력하는 필드(api_base · url · host · path)를 검증하기로 했을 때, 같은 레코드에 그 호출의 kwargs 로 **나중에 merge 되는 자유형 dict**(extra_params · options · headers · config)가 있으면, 그 dict 가 같은 키나 동의어(base_url)를 실어 검증된 필드를 덮는다. 검증은 필드가 아니라 **최종 호출 인자**에 걸어야 하고, 그 지점은 모든 호출이 지나는 한 곳이어야 한다. 트리거 - SSRF 방어, 사용자 지정 엔드포인트/웹훅 URL 검증, `kwargs.update(extra_params)`, LiteLLM/requests/httpx 에 사용자 설정 dict 전달, "api_base 만 막으면 된다".
---

# 검증된 필드 옆의 자유형 dict 는 그 필드를 무효로 만든다

## Problem

BSVibe(2026-10-15): 테넌트 모델 계정의 `api_base` 를 공개 주소로 제한하려 했다.
호출 지점은 이랬다:

```python
kwargs = {"model": model, "messages": messages}
if api_base:
    kwargs["api_base"] = api_base
if extra_params:
    kwargs.update(extra_params)      # ← 테넌트가 저장한 자유형 dict, 마지막에 merge
raw = await litellm.acompletion(**kwargs)
```

`api_base` 만 검증하면 `extra_params={"base_url": "http://169.254.169.254"}` 또는
`extra_params={"api_base": "http://10.0.0.9"}` 로 **검증된 값이 그대로 덮인다.**
필드 단위 검증(스키마 validator)은 dict 안을 보지 않는다.

## Solution

1. **검증 지점 = 최종 kwargs 가 만들어진 직후, 호출 직전.** merge 가 끝난 dict 를 본다.
2. 그 지점은 **모든 호출이 지나는 한 곳**이어야 한다 — 호출자마다 검증하면 다음 호출자가 빠진다.
   (BSVibe: 어댑터 · chat 프록시 둘 다 `LlmClient.chat` 을 지나서 거기 하나.)
3. 키는 이름 하나가 아니라 **동의어 집합**: `api_base`, `base_url`, `*_endpoint`, `*_base_url`.
4. **값이 없을 때의 기본 목적지**도 본다: `ollama/…` 는 엔드포인트가 없으면 라이브러리 기본값
   `localhost:11434` — 서버 자신의 루프백. "필드가 비었으니 안전"이 아니다.
5. 호스트명은 **해석해서 모든 주소**가 공개인지 본다(하나만 사설이어도 거절). `is_global` 하나로
   RFC1918 · 루프백 · 링크로컬 · CGNAT(100.64/10) · `0.0.0.0` 이 다 걸린다. IPv4-mapped IPv6 는 풀어서.
6. 저장 시점 검증은 **UX 용**으로 같은 함수를 재사용 — 보증은 호출 지점이다.
7. 남는 것: DNS rebinding(검증 해석과 실제 연결 해석이 다름). 애플리케이션 층의 바닥일 뿐, 완전한 답은 egress 방화벽.

## 테스트

- 절단 대상에 **merge 후 검사**를 포함: 검사를 `kwargs.update` 앞으로 옮기거나 `base_url` 키를 빼면
  `extra_params` 우회 테스트가 빨개져야 한다.
- DNS 는 resolver 주입 — 테스트가 실제 네트워크를 타면 안 된다(기존 `api.example.com` 테스트가 여기서 깨졌다).
- 기존 픽스처가 `ollama/…` 를 엔드포인트 없이 쓰고 있으면 **검사를 끄는 seam 을 만들지 말고** 픽스처에
  공개 IP 리터럴 엔드포인트를 준다(`93.184.216.34`; `203.0.113.x` 는 TEST-NET 이라 `is_global=False`).
- 예외 경로(예: 워커에서 도는 실행기 계정)는 **예외가 실제로 필요한 입력**으로 테스트하라 —
  예외 없이도 통과하는 입력(`opus`)이면 예외를 지워도 초록이다.
