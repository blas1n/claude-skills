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
