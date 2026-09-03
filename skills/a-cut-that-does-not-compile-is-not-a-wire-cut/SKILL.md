---
name: a-cut-that-does-not-compile-is-not-a-wire-cut
description: 가드를 실증하려고 코드를 되돌렸는데 그 치환이 문법 오류를 만들면, 빨강은 나오지만 아무것도 증명되지 않는다 — 그리고 빨강이 나왔으므로 성공처럼 읽힌다. 이걸 잡는 신호는 초록/빨강이 아니라 **돌아간 테스트 개수**다. 트리거 - 전선 절단/mutation 실증, sed·python 로 소스 되돌리기, "가드가 진짜 잡는지 확인", 절단 후 실패 수가 예상과 다를 때.
---

# 컴파일 안 되는 절단은 전선 절단이 아니다

## Problem

가드가 진짜로 무언가를 잡는지 보려면 구현을 되돌려 빨강을 봐야 한다(전선 절단).
그런데 **되돌리는 행위 자체가 코드를 깨뜨리면** 빨강은 나오지만 명제는 안 걸린다.

실측 — 쉘에서 치환 문자열을 만들다 이스케이프가 남았다:

```bash
# 의도: const cannotProduce = !(view.hasProducts && view.hasLiveWorker);
cut "$FILE" "..." "const cannotProduce = !(view.hasProducts \&\& view.hasLiveWorker);"
#                                                            ↑↑ 백슬래시가 파일에 그대로 들어갔다
```

결과: 그 파일은 **파싱 실패 → 수집조차 안 됨**. 러너는 나머지 파일만 돌렸다.

```
=== CUT 2 ===
 ✓ test/brief-data.test.tsx (13 tests)
      Tests  13 passed (13)      ← 24개여야 하는데 13개
```

**빨강이 아니라 "그 파일이 없음"** 이었다. 그리고 `tail -8` 로 자른 출력에서는
초록만 보여서 *"절단해도 안 빨개진다 = 가드가 약하다"* 로 **정반대로 읽힐** 뻔했다.

### 왜 잘 속나

* 절단은 **일부러 부수는** 작업이라 뭔가 깨져 보이는 것이 **기대되는 결과**다
* 러너는 수집 실패를 보통 다른 파일 결과와 **같은 요약 줄**에 섞어 보여준다
* 복구 치환은 (망가진 문자열을 그대로 찾으므로) **성공한다** → 흔적이 안 남는다

## Solution

### 1. 절단 전에 기준 개수를 박아라

```bash
BASE=$(run_tests | grep -oE 'Tests +[0-9]+ (passed|failed)' ...)   # 예: 24
# 절단 후: 총 실행 수가 BASE 와 같은가? 다르면 절단이 아니라 사고다.
```

**총 실행 수 = 통과 + 실패.** 이 값이 변하면 절단이 무효다.
`Test Files N passed (M)` 의 **M(총 파일 수)** 도 같은 센서다.

### 2. 치환은 쉘 문자열로 만들지 마라

`&` 는 sed 에서 매치 전체를 뜻하고, `\&` 는 쉘/도구 층마다 다르게 살아남는다.
**파이썬 heredoc 안에서 리터럴로** 쓰고 쉘을 거치지 않게 하라:

```bash
python3 - "$FILE" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = "const cannotProduce = !view.hasProducts || view.hasLiveWorker === false;"
new = "const cannotProduce = !(view.hasProducts && view.hasLiveWorker);"
assert old in s, "pattern not found"
p.write_text(s.replace(old, new, 1))
PY
```

`<<'PY'` (따옴표) 로 쉘 확장을 통째로 끄는 것이 핵심이다.

### 3. 절단 후 첫 확인은 "빨강인가"가 아니라 "빌드되는가"

타입 있는 언어면 절단 상태에서 `tsc --noEmit` / `mypy` 를 먼저 돌려라.
**컴파일이 깨지면 그 절단은 폐기하고 다시 만들어라.**

### 4. 출력을 자르지 마라

`| tail -8` 이 파일별 결과를 잘라내면 이 사고가 보이지 않는다.
파일별 줄과 총계 줄을 **둘 다** 남기는 필터를 써라:

```bash
... | grep -E "^ *(✓ test|× |Test Files|Tests )"
```

## Key Insights

- **빨강은 절단의 성공 신호가 아니다.** 절단은 *특정 명제 하나*가 죽는 것을 증명해야
  하는데, 컴파일 오류는 **전부**를 죽이고 그 구분이 요약에서 사라진다.
- **가장 값싼 센서는 돌아간 테스트 개수다.** 초록/빨강보다 먼저 봐라 —
  개수가 변하면 무슨 짓을 했든 실험이 아니다.
- **복구가 성공하는 것이 함정을 덮는다.** 망가뜨린 문자열을 그대로 찾아 되돌리므로
  파일은 멀쩡해지고, 무효했던 실험만 노트에 "빨강 확인"으로 남는다.
- 절단 스크립트도 코드다. **쉘을 거치는 치환은 쓰지 마라** — `&`, `\`, `!`, 개행이
  전부 층마다 다르게 산다.
