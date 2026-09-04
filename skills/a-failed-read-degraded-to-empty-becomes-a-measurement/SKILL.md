---
name: a-failed-read-degraded-to-empty-becomes-a-measurement
description: 읽기 실패를 `[]`/`false`/`0` 으로 degrade 하면, 그 비어 있음 자체로 UI·규칙이 주장을 만드는 순간 blip 한 번이 "안 잰 것"을 단언한다. 트리거 - `.catch(() => [])`, `?? false`, `except: return None`, "never blanks the surface" 주석, "blip 때 조용히 잘못된 안내가 뜬다", 인수인계가 넘긴 미확인 결함 후보.
---

# 읽기 실패를 falsy 로 접으면 측정으로 세탁된다

## Problem

부분 실패에 강하려고 선택적 표면을 이렇게 접는다:

```ts
listWorkers().catch(emptyOnApiError<Worker>),   // → []
```

주석은 보통 *"never blanks the surface"* 라고 적혀 있고, 그 자체는 맞다.
**문제는 그 다음이다** — 소비자가 비어 있음을 **대답으로** 읽는다:

```ts
hasLiveWorker: workers.some(w => w.heartbeat_fresh),   // [] → false
```

`false` 가 두 뜻을 겸한다:
* **재서** 없다 (물어봤고 살아있는 워커가 없다)
* **못 재서** 없다 (`/workers` 가 500 이었다)

⇒ **blip 한 번이 안 잰 것을 단언한다.**

### 갈림길: 비어 있음이 *대답*인가, 그냥 *없음*인가

같은 파일 안에서도 갈린다. 실측 사례:

| 표면 | `[]` 의 의미 | degrade 대상 |
|---|---|---|
| `deliverables` | 붙일 산출물이 없다 → 링크만 안 뜸 | `[]` 로 접어도 된다 |
| `workers` | **"당신 일을 집어갈 게 없다"** → 화면이 뒤집힘 | `null` (unknown) 이어야 한다 |

⇒ 판별 질문: **"이 리스트가 비면 사용자에게 무슨 문장이 뜨는가?"**
문장이 뜨면 그건 대답이고, 읽기 실패는 그 대답이 될 수 없다.

## Solution

### 1. 크기부터 재라 — 증상은 소비자 하나지 결함 전체가 아니다

인수인계/버그리포트는 **자기가 본 소비자 하나**를 적는다. 필드를 grep 해서
**소비자를 전부 세라.** 실측에서 보고된 건 하나(온보딩 부활)였는데 실제로는 둘이었고,
**보고 안 된 쪽이 훨씬 넓었다**:

| 소비자 | 주장 | 추가 조건 |
|---|---|---|
| 온보딩 체크리스트 | *"아직 생산할 수 없다"* | 런 창이 비어야 함 (좁다) |
| waiting 필 | *"이 런을 집어갈 게 없다"* | **없음** — 활성 런 있는 누구나 (넓다) |

### 2. 세 번째 상태를 만들고, truthiness 를 끊어라

```ts
hasLiveWorker: boolean | null;      // null = 읽기가 실패해서 모른다

function unknownOnApiError<T>(e: unknown): T[] | null {
  if (e instanceof ApiError || e instanceof TypeError) return null;
  throw e;                          // 비-API 예외는 그대로 전파
}
```

소비자는 **`=== false` / `=== true`** 로 묻는다. `!x` 와 `x &&` 는 `null` 을 조용히
삼키므로 타입만 바꾸면 컴파일러는 아무것도 안 잡아준다 — **호출부를 손으로 세라.**

### 3. ⭐ unknown 을 **통째로 억제하지 마라** — 판정을 바꾸는 주장만 막아라

여기가 반대 방향 결함이 태어나는 자리다. "모르면 아무 말도 하지 말자"는
그럴듯하지만 틀렸다.

```ts
// ❌ 순진한 수정 — unknown 이면 안내를 끈다
const firstRun = !placeholder && hasLiveWorker === true ? false : ...

// ✅ 모르는 것이 판정을 바꾸는지 물어라
const cannotProduce = !hasProducts || hasLiveWorker === false;
```

`hasProducts` 가 false 면 워커 답이 **무엇이든** 생산할 수 없다 →
**unknown 이어도 주장해도 된다.** 통째로 억제했으면 그 화면이 존재하는 이유인
*신규 사용자*를 blip 중에 버렸을 것이다.

⇒ 판별식: **"모르는 값을 true 로 놔도, false 로 놔도 결론이 같은가?"**
같으면 주장하라. 갈리면 침묵하라.

### 4. 대조군을 반드시 같이 심어라

`unknown → 주장 안 함` 테스트만 있으면 **주장 자체를 지워도 초록**이다.

* `unknown` → 안 뜬다
* **`재서 false`** → **여전히 뜬다** ← 이게 없으면 기능을 지운 것과 구분 안 됨
* `재서 true` → 안 뜬다
* `unknown 인데 판정을 못 바꾸는 자리` → **뜬다**

## 셸/CLI 형태 — `2>/dev/null` + `[ -z "$x" ]` (2026-09-04 실측)

TypeScript 의 `.catch(() => [])` 와 **완전히 같은 결함**이 셸에선 이렇게 생겼다:

```bash
password=$(security find-generic-password -s "$SVC" -a "$ACC" -w 2>/dev/null)
if [ -z "$password" ]; then
  echo "SKIP: 라이브 E2E — Keychain 에 자격증명이 없다."     # ← 재지 않은 원인을 단언
```

`2>/dev/null` 이 **이유를 버리고**, `-z` 가 남은 유일한 신호다. 실측한 두 세계:

| rc | 뜻 | 옳은 처신 |
|---|---|---|
| `44` `errSecItemNotFound` | 진짜 부재 — **사람을 기다린다** | 조용한 SKIP |
| `36` `errSecInteractionNotAllowed` | **잠긴 keychain** — 항목이 있어도 못 읽는다 | **FAIL·알람** |

⭐ **셸에서 특히 위험한 이유**: 종료코드라는 **완벽한 신호가 바로 옆에 있었는데**
버렸다. JS 의 `catch` 는 최소한 에러 객체를 손에 쥐지만, `2>/dev/null` 은 진짜로
없앤다. 그리고 `$?` 는 다음 명령 하나면 사라진다.

### ⭐⭐ 이 결함의 진짜 비용 — 세탁된 문장이 **엔지니어링 진단**으로 자란다

이 로그는 매일 밤 *"Keychain 에 자격증명이 없다"* 를 찍었다. 사람은 그 문장을 근거로
원인을 추론했고, **세 세션이 keychain 실패를 *"에이전트가 비대화형이라서 / OS 경계"*
로 적었다 — 전부 틀렸다.** 잠긴 `login.keychain-db` 하나였다.

⇒ 세탁된 값의 소비자는 UI 만이 아니다. **로그를 읽는 사람도 소비자**이고, 그쪽 결함은
   화면 한 줄이 아니라 **여러 세션의 방향**으로 나타난다.

⇒ 그리고 이 결함은 **오늘 참일 수 있다**. 오늘의 호출은 44 를 내므로 문장은 *우연히*
   맞다. 36 이 나오는 자리는 사람이 자격증명을 **넣는 바로 다음**이다 — 즉 이 문장이
   틀리는 순간은 하필 **사람이 방금 한 일을 의심하게 되는 순간**이다.
   *"지금은 맞으니 나중에"* 로 넘기지 마라. 틀릴 시점이 최악의 시점이다.

### 처방 — 판정을 순수 함수로 빼라

```bash
kc_err=$(mktemp)
password=$(security find-generic-password ... -w 2>"$kc_err"); kc_rc=$?   # ⚠ 바로 다음 줄
[ -n "$password" ] && kc_has=1 || kc_has=0
verdict=$(keychain_credential_verdict "$kc_rc" "$kc_has")   # ok|absent|unreadable
```

* **모르는 rc 는 전부 `unreadable`** — 미래의 새 코드가 '조용한 SKIP' 으로 떨어지면
  안 된다. **틀리려면 알람이 과한 방향으로 틀려라.**
* **비밀 값은 판정 함수에 넘기지 마라** — 사유는 로그로 나가고 `set -x` 는 인자를 찍는다.
  비었는지만 `0/1` 로 접어서 넘긴다.
* 판정을 러너 본체에 두면 **영원히 테스트되지 않는다**(docker 스택 + 70~90초 E2E 를
  지나야 닿는 줄이었다). 순수 함수 + 라이브러리 로드 확인(`declare -F`)이 짝이다.

## Key Insights

- **`[]` 는 값이 아니라 문장이다.** "비어 있음이 화면에 무슨 말을 만드는가"를 물으면
  어떤 표면이 `null` 이 필요한지 즉시 갈린다. 같은 `Promise.all` 안에서도 갈린다.
- **보고된 증상은 소비자 하나다.** 세탁된 unknown 의 결함 개수 = 그 필드의 **소비자 수**.
  고치기 전에 grep 으로 세라 — 안 보고된 쪽이 더 넓을 수 있다.
- **타입을 `| null` 로 바꿔도 컴파일러는 안 잡는다.** `null` 은 falsy 라서
  `!x` · `x && y` 가 전부 통과한다. 호출부는 **손으로** 세야 한다.
- **unknown 은 침묵의 이유가 아니라 조건이다.** 모르는 값이 결론을 못 바꾸는 자리에서는
  그대로 주장하라. 안 그러면 과다주장을 고치다 과소주장을 만든다.
- 산문 주석(*"degrades to [] on a blip (never blanks the Brief)"*)이 **결함을 계약으로**
  적어두고 있을 수 있다. 고칠 때 **문서의 그 줄까지** 같이 고쳐라.
