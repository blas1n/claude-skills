---
name: a-config-slot-cannot-hold-two-legitimate-producers
description: 버그 리포트가 "설정이 잘못된 곳을 가리킨다"로 진단했을 때 — 설정을 고치기 전에 그 슬롯을 먹이는 생산자가 몇 개인지부터 세라. 둘이면 설정은 절대 해법이 될 수 없고, 제안된 수정을 한 칸만 앞으로 돌려보면 그게 드러난다. 그리고 그 한계는 이미 코드 어딘가에서 "우회"로 문서화돼 있다.
---

# 설정 슬롯 하나에 정당한 생산자가 둘 들어가면, 설정은 해법이 아니다

## Problem

- **증상**: 어떤 클라이언트만 401/403/불일치로 죽는다. 다른 클라이언트는 멀쩡하다.
  리포트는 설정 값 하나를 범인으로 지목한다 — *"`X_URL` 이 A 를 가리키는데 B 여야 한다"*.
- **근본 원인**: 그 슬롯을 먹이는 **정당한 생산자가 둘**이다. A 도 맞고 B 도 맞다.
  슬롯은 하나니까 **어느 값을 넣어도 한쪽은 죽는다.** 결함은 값이 아니라 **검증기가 하나라는 것**이다.
- **흔한 오해**: "멀쩡한 클라이언트가 있으니 설정은 대체로 맞고, 틀린 건 한 칸뿐이다."
  실제로는 **멀쩡한 쪽이 그 설정의 유일한 수혜자**고, 그게 문제를 몇 달 숨긴다.

실제 사례(BSVibe #1017): `bsvibe products list` 가 prod 에서 401.
리포트 진단은 *"`USER_JWT_JWKS_URL` 이 Supabase 를 가리킨다"*.
그런데 CLI 토큰은 Supabase 세션 JWT 가 **아니라** 우리 임베디드 OAuth 의 ES256 액세스
토큰이었다(`sub` 가 `UserRow.id`, `supabase_user_id` 가 아님). 설정을 우리 발급자로
돌리면 **PWA 가 죽고, CLI 는 `sub` 때문에 그래도 못 들어온다.**

## Solution

### 1. 제안된 수정을 **한 칸 앞으로 돌려봐라** (코드만 읽으면 된다)

설정을 리포트가 말하는 값으로 바꿨다고 가정하고 **체인 끝까지** 따라가라:

- 다른 클라이언트는 여전히 통과하나?  → 아니면 설정은 해법이 아니다
- 통과한 뒤 **다음 층**이 그 principal 을 쓸 수 있나? (식별자 공간이 같은가?)

두 질문 중 하나라도 아니오면 **코드를 쓰기 전에** 진단이 끝난다.

### 2. 페이로드의 **클래스**를 먼저 실측해라 — 설정과 대조하지 말고

```bash
# 설정이 무엇을 가리키는지가 아니라, 실제 크리덴셜이 무엇인지부터
python3 -c "
import json,base64,pathlib
t=json.loads(pathlib.Path('~/.config/app/credentials.json').expanduser().read_text())['access_token']
pad=lambda s:s+'='*(-len(s)%4)
h,p,_=t.split('.')
print(json.loads(base64.urlsafe_b64decode(pad(h))))   # alg, kid
print(json.loads(base64.urlsafe_b64decode(pad(p))))   # iss, sub, aud
"
```

`iss`·`aud`·`sub` **의 모양**이 답이다. `sub` 가 어느 식별자 공간에 사는지가 특히 중요하다 —
서명이 통과해도 다음 층에서 조용히 403 이 된다.

### 3. **우회를 찾아라 — 우회의 주석이 진단이다**

한계가 오래됐다면, 누군가 이미 **그 메커니즘을 탈출해서** 한 기능만 살려 놨다.
그 탈출구의 주석이 제약을 정확히 이름 붙여 놓는다.

```
# Mounted outside the auth-gated v1 router because that gate accepts
# only a Supabase session JWT, and a PAT must also be mintable from a
# browserless host holding an ES256 access token.
```

⇒ 검색어는 증상이 아니라 **"이 기능만 왜 다르게 배선돼 있나"** 다:
`grep -n "outside\|bypass\|except\|special-case\|mounted.*before" ` + 라우터/미들웨어 마운트 지점.

### 4. 해법은 **검증기를 둘로** — 단, 분기는 결정적으로

```python
# iss 는 unverified 로 읽되 "어느 검증기를 돌릴지"에만 쓴다. 절대 신뢰하지 않는다.
# try-A-then-B 폴백이 아니다: 순차 시도는 실패를 뭉개고(만료된 세션 JWT 가
# "잘못된 액세스 토큰"으로 보고된다) 매 실패마다 쓸데없는 DB 왕복을 한다.
if unverified_issuer(token) == our_issuer:
    return await verify_our_access_token(token, session=session)
return await verify_session_jwt(token)
```

## Key Insights

- **"설정이 틀렸다"는 진단은 생산자가 하나일 때만 성립한다.** 둘이면 값을 바꾸는 건
  죽는 쪽을 바꾸는 것뿐이다. **먼저 세라: 이 슬롯을 정당하게 먹이는 게 몇 개인가.**
- **서명 검증을 통과하는 것과 다음 층이 그 principal 을 쓸 수 있는 것은 다른 명제다.**
  `sub` 가 다른 식별자 공간에 살면 401 을 고쳐도 403 이 나온다. 체인 끝까지 돌려봐라.
- **한 라우터만 게이트 밖에 마운트돼 있으면 그건 스타일이 아니라 상처다.**
  누군가 제약에 부딪혀 하나만 구했고, 나머지는 그대로 막힌 채 남아 있다.
- **멀쩡한 클라이언트가 결함을 숨긴다.** 스위트가 전부 초록인 이유도 같다 — 테스트가
  살아 있는 쪽 크리덴셜만 쓴다. 회귀 가드는 **죽은 쪽 발급자가 실제로 내준 토큰**이어야 한다.

## Red Flags

- 이슈/인수인계가 환경변수 이름을 범인으로 지목하고 **"둘 다여야 하는 것으로 보인다"** 라고 덧붙일 때
  ← 슬롯이 하나라는 걸 리포트 스스로 눈치챘다는 신호다
- 같은 크리덴셜이 어떤 엔드포인트는 통과하고 어떤 엔드포인트는 401
  ← 검증기가 여러 개고 신뢰 루트가 갈렸다. **에러 본문을 끝까지 읽어라** —
  "invalid bearer" 와 "JWKS resolution failed" 는 다른 병이다
- 한 라우터/핸들러만 `include_router` 위치가 다르거나 자기 전용 auth 리졸버를 들고 있을 때
- "PWA 는 멀쩡한데 CLI 만", "브라우저는 되는데 헤드리스만" — **크리덴셜 클래스가 갈린 자리**다
- 스위트는 전부 초록인데 prod 는 죽어 있다 ← 테스트가 **자기가 서명한 토큰**을 쓴다
