---
name: test-fixture-clearing-global-cache-poisons-the-suite
description: 테스트 픽스처가 env 를 바꾸고 lru_cache 의 cache_clear() 를 호출하면, 그 모듈이 아니라 **다른 모듈의 테스트가 실행마다 다르게 깨진다**(격리하면 통과). 캐시는 전역이라 비우는 순간 이후 모든 독자가 지금 환경으로 다시 만든다. 게다가 monkeypatch 를 요청한 픽스처는 monkeypatch 보다 **먼저** 정리되어, 되돌리기 전에 내 값이 다시 캐시된다. 처방은 env 를 안 건드리고 값을 만드는 함수를 패치하는 것. 트리거: 전체 스위트에서만 실패, 실패 목록이 매번 바뀜, get_settings.cache_clear(), monkeypatch.setenv + 캐시 무효화.
---

# 픽스처가 전역 캐시를 비우면 남의 테스트가 깨진다

## Problem

설정이 `lru_cache` 로 감싸여 있고(`@lru_cache def get_settings()`), 테스트에서 특정 키가 필요하다.
관례적으로 이렇게 쓴다:

```python
@pytest.fixture
def kms_key(monkeypatch):
    monkeypatch.setenv("APP_KMS_KEY", base64.b64encode(KEY).decode())
    get_settings.cache_clear()          # 새 env 를 읽게
    yield
    get_settings.cache_clear()          # 원상복구
```

- **증상**: 이 모듈은 통과한다. 대신 **전혀 무관한 모듈**(다른 glue 테스트, 마이그레이션 테스트)이
  전체 스위트에서 실패한다. **격리 실행하면 통과한다.** 그리고 **실패 목록이 실행마다 바뀐다.**
- **근본 원인 둘, 둘 다 조용하다**:
  1. **캐시는 전역이다.** 비우는 순간부터, 이후 아무 모듈이나 `get_settings()` 를 부르면 **그 시점의
     환경**으로 다시 만들어 캐시한다. 자기 env 를 앞서 세팅해두고 캐시된 설정에 기대던 모듈은 그
     값을 잃는다.
  2. **정리 순서가 반대다.** `monkeypatch` 를 **요청한** 픽스처는 pytest 가 역순으로 정리하므로
     **monkeypatch 보다 먼저** 끝난다. 즉 `yield` 뒤의 `cache_clear()` 는 **내 env 가 아직 살아 있을 때**
     실행되고, 다음 `get_settings()` 가 **내 테스트 키를 캐시한다.**
- **흔한 오해**: "`monkeypatch` 가 되돌려주니 안전하다." 되돌려주는 건 env 뿐이고, **캐시는 그때
  이미 오염돼 있다.**

## Solution

**전역 상태를 건드리지 말고, 값을 만드는 함수를 패치하라.**

```python
@pytest.fixture
def kms_key(monkeypatch):
    """설정도 env 도 안 건드린다 — 키를 만드는 함수만 바꾼다."""
    monkeypatch.setattr(
        "myapp.crypto._key_from_settings", lambda: KEY, raising=True
    )
```

전역 캐시를 안 비우므로 다른 모듈이 영향을 안 받고, 정리 순서 문제도 사라진다.

⚠️ **패치 대상은 "쓰이는 곳의 이름"이다.** 모듈 최상단에서
`from myapp.crypto import _key_from_settings` 로 import 했다면 그 이름은 **소비자 모듈에 바인딩**돼
있으므로 `myapp.consumer._key_from_settings` 를 패치해야 한다. 함수 안 지연 import 라면
원본(`myapp.crypto._key_from_settings`)을 패치하면 된다. 둘 다 있으면 둘 다.

**env 를 꼭 써야 한다면** 순서를 직접 통제하라 (monkeypatch 에 맡기지 말 것):

```python
prior = os.environ.get(NAME)
os.environ[NAME] = value
get_settings.cache_clear()
try:
    yield
finally:
    if prior is None:
        os.environ.pop(NAME, None)
    else:
        os.environ[NAME] = prior
    get_settings.cache_clear()          # env 를 되돌린 "뒤"
```

그래도 ①의 전역 오염은 남는다. 세션 전체가 같은 설정을 쓰는 스위트에서만 받아들일 만하다.

## Key Insights

- **"격리하면 통과, 전체에선 실패"는 상태 오염의 서명이다.** 거기에 **실패 대상이 매번 바뀐다**가
  더해지면 거의 확정 — 순서 의존이다.
- **캐시 무효화는 로컬 동작이 아니다.** `cache_clear()` 는 내 테스트를 위한 것처럼 보이지만
  프로세스 전체에 대고 하는 일이다.
- **픽스처 정리 순서는 요청 관계의 역순이다.** `monkeypatch` 를 인자로 받으면 내가 먼저 끝난다 —
  "yield 뒤 = 전부 되돌아간 뒤"가 아니다.
- 다음에 먼저 확인할 것: 새 픽스처가 **프로세스 전역 상태**(env, lru_cache, 싱글턴, 로거 설정)를
  건드리는가. 건드린다면 그 테스트가 아니라 **다른 테스트**가 대가를 치른다.

## Red Flags

- 픽스처 안에 `cache_clear()` / `os.environ[...] =` / 싱글턴 재할당이 있다
- 전체 스위트에서만 실패하고 격리하면 통과한다
- 실행할 때마다 실패하는 테스트가 다르다
- 실패한 테스트가 내가 만진 코드와 아무 상관이 없다
