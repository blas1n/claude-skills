---
name: bulk-code-transform-costs-more-than-it-saves
description: 리팩터에서 N곳을 자동 변환(ast.unparse · 넓은 정규식 · sed)하면 대상 밖까지 바꾸거나 값을 틀리게 계산한다 — 그리고 테스트는 통과하므로 diff 를 한 줄씩 읽어야만 드러난다. 손익분기점은 생각보다 훨씬 높다(N≈20+). 트리거 - "N곳을 한 번에 고치자", ast.unparse/NodeTransformer 로 파일 재작성, `re.sub` 로 리터럴 변환, sed -i 일괄 치환, 대량 테스트 픽스처 갱신.
---

# 일괄 코드 변환은 아끼는 것보다 많이 부순다

## Problem

리팩터가 20곳쯤을 같은 모양으로 바꿔야 한다. 손으로 하기 지겨우니 자동화한다.
2026-08-31 한 PR 에서 **세 번 연속** 당했다.

### ① `ast.unparse` 는 편집 도구가 아니라 **전체 재작성** 도구다

```python
tree = ast.parse(src); Transformer().visit(tree)
path.write_text(ast.unparse(tree))        # ❌
```

* **증상**: diff 가 `570 deletions / 147 insertions`. 바꾼 건 11곳인데.
* **원인**: AST 에 **주석이 없다.** unparse 는 주석·빈 줄·서식·따옴표 스타일을
  전부 잃는다. docstring 은 AST 노드라 살아남으므로 **손실이 눈에 잘 안 띈다.**
* 이 저장소처럼 주석이 *왜 이렇게 했는지*를 담는 곳에서는 코드보다 주석이 더 비싸다.

### ② 넓은 정규식은 대상 밖을 문다 — 그리고 **값을 틀리게 계산한다**

```python
re.sub(r'\{((?:[\w-]+\s*:\s*(?:true|false)\s*,?\s*)+)\}', flat, src)   # ❌
```

* `prefs({ quiet_hours_enabled: true })` → `prefs(true)` — 매트릭스가 아닌데 잡혔다
* `expect.objectContaining({ telegram: true })` → `objectContaining(true)` — 같은 이유
* 그리고 `(...)+` 는 **마지막 반복만** 그룹에 남긴다. `{a:true, b:true, c:false}` 에서
  본문을 `c:false` 로만 보고 **false 를 만들었다.** 문법은 맞고 값만 틀렸다.

**타입체커도 테스트도 이걸 다 잡지 못한다** — 문법이 유효하고 타입이 맞으면
"의도와 다른 값"은 통과한다. 잡은 것은 **diff 를 한 줄씩 읽은 것**뿐이었다.

## Solution

**손익분기점을 다시 계산하라.** 자동 변환의 비용은 *쓰는 시간*이 아니라
**diff 전체를 검수하는 시간 + 오적용 복구 시간**이다.

| 대상 수 | 권장 |
|---|---|
| ~20곳 이하 | **손으로.** Edit 도구로 하나씩. 대개 자동화 스크립트 쓰는 시간보다 빠르다 |
| 그 이상 | 자동화하되 **아래 규칙 전부** |

자동화한다면:

1. **`ast.unparse` 금지.** 대신 AST 로 **위치만** 찾고 텍스트를 그 줄에서 바꿔라.
   ```python
   for kw in node.keywords:
       if kw.arg == "matrix": lines_to_touch.add(kw.value.lineno)   # ✅ 위치만
   ```
2. **치환마다 `count == 1` 을 단언하라.** 문자열이 여러 곳에 있으면 실패하게.
   ```python
   assert s.count(old) == 1, old[:60]
   ```
3. **`git diff` 를 눈으로 전부 읽어라.** 줄 수가 예상과 다르면 멈춰라 —
   이게 ①을 잡은 유일한 신호였다.
4. **되돌릴 수 있게 하라**: 커밋 안 된 상태에서만 돌리고, 이상하면 `git checkout --`.

## Key Insights

* **주석은 AST 에 없다.** 코드를 보존하는 도구가 *이유*를 보존한다는 보장은 없다.
* **문법 유효 + 타입 통과 ≠ 의미 보존.** 정규식이 만든 `false` 는 완벽히 유효했다.
* **diff 크기가 첫 번째 센서다.** "11곳 바꿨는데 570줄이 지워졌다" 는 읽기 전에
  이미 이상하다. 변경 규모를 **예상하고** 나서 diff 를 봐라.
* 이건 [[deletion-pr-needs-an-absence-guard-and-a-control]] 의 자매 문제다 —
  거기서는 *마커 사이*를 자르다 사이의 것을 가져갔고, 여기서는 *패턴 주변*을
  바꾸다 주변의 것을 가져갔다. **범위를 텍스트로 정하면 범위는 우연에 맡겨진다.**

## Red Flags

- diff 의 삭제 줄 수가 변경 대상 수와 자릿수가 다르다.
- `ast.unparse` / `NodeTransformer.visit` 후 `write_text`.
- 정규식에 `(...)+` 나 `.*` 가 있고 그 그룹을 값 계산에 쓴다.
- "테스트 통과하니까 됐다" — 값이 틀려도 통과할 수 있는 변환이었나?
