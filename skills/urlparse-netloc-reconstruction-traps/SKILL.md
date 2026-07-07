---
name: urlparse-netloc-reconstruction-traps
description: urllib.parse.urlparse로 URL 파싱 후 netloc 재조합 시 발생하는 두 침묵 버그 — userinfo 대소문자 소실과 cross-scheme 기본 포트 오삭제.
version: 1.0.0
task_types: [coding, bugfix]
triggers:
  - pattern: "URL 정규화, netloc 재조합, scheme/host 소문자화, 기본 포트 제거, urlparse, urlunparse"
---

# urllib.parse netloc 재조합 트랩

## 개요

`urllib.parse.urlparse` 결과를 수정 후 `urlunparse`로 재조합할 때 발생하는 두 가지 침묵 버그.
두 버그 모두 예외를 발생시키지 않아 테스트 없이는 발견하기 어렵다.

---

## 트랩 1: netloc.lower()가 userinfo를 소문자화

### 증상

```python
parsed = urlparse("https://User:Pass@EXAMPLE.COM/path")
normalized = urlunparse((scheme, parsed.netloc.lower(), path, ...))
# → "https://user:pass@example.com/path"   ← username/password 소문자화됨
```

RFC 3986 §3.2.1: userinfo는 case-sensitive. 소문자화 시 인증 실패 가능.

### 원인

`parsed.netloc`은 `userinfo@host:port` 전체 raw 문자열이므로 `.lower()`가 모두 적용된다.

### 해결책

`parsed.hostname`(이미 소문자 반환)을 쓰고 netloc을 컴포넌트 단위로 수동 재조합:

```python
host: str = parsed.hostname or ""          # 이미 소문자
port: int | None = parsed.port

if parsed.username is not None:
    userinfo = parsed.username             # 원본 대소문자 보존
    if parsed.password is not None:
        userinfo = f"{userinfo}:{parsed.password}"
    netloc = f"{userinfo}@{host}"
else:
    netloc = host

if port is not None:
    netloc = f"{netloc}:{port}"
```

---

## 트랩 2: cross-scheme 기본 포트 오삭제

### 증상

```python
def strip_default_port(scheme, port):
    if port in (80, 443):    # ← 버그: 스킴을 고려하지 않음
        return None
    return port

strip_default_port("http", 443)   # → None  ← 잘못된 삭제
strip_default_port("https", 80)   # → None  ← 잘못된 삭제
```

`http://example.com:443`에서 포트가 제거되어 전혀 다른 서비스를 가리키게 된다.

### 원인

"80 또는 443이면 기본 포트"라는 직관. 실제로 포트는 **스킴과 쌍**으로만 기본값이다.

### 해결책

스킴별 기본 포트 딕셔너리와 대조:

```python
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}

if port is not None and _DEFAULT_PORTS.get(scheme) == port:
    port = None
```

---

## 확인 테스트

```python
from toolkit.urlnorm import normalize_url

# 트랩 1: userinfo 보존
assert normalize_url("https://User:Pass@EXAMPLE.COM/") == "https://User:Pass@example.com"

# 트랩 2: cross-scheme 포트 보존
assert normalize_url("http://example.com:443/path") == "http://example.com:443/path"
assert normalize_url("https://example.com:80/path")  == "https://example.com:80/path"

# 정상 기본 포트 삭제
assert normalize_url("http://example.com:80/path")  == "http://example.com/path"
assert normalize_url("https://example.com:443/path") == "https://example.com/path"
```

---

## 적용 범위

같은 트랩이 발생하는 상황:
- git remote URL 정규화
- OAuth redirect_uri 비교
- docker registry URL 파싱
- curl/httpx에 URL을 구성해서 넘길 때
