---
name: zsh-word-splitting-fails-the-edit-and-the-grep-that-checks-it
description: zsh 는 `$var` 를 단어 분할하지 않는다 — `FILES=$(find ...)` 뒤 `sed ... $FILES` 는 목록 전체를 **파일명 하나**로 넘겨 15개 치환이 전부 실패한다. 진짜 위험은 실패 자체가 아니라, 바로 뒤 검증 `grep ... $FILES` 가 **같은 관용구를 공유해 함께 죽는 것**이다: 편집도 안 되고 검증도 "잔여 없음"처럼 보인다. 배열 `FILES=(...)` + `"${FILES[@]}"` 를 쓰고, 검증은 편집과 **다른 방식으로 대상을 지정**하라. 트리거 - zsh 에서 여러 파일 일괄 치환, `$(find)`/`$(grep -l)` 결과를 명령에 전달, 치환 후 grep 으로 확인, "No such file or directory" 에 목록 전체가 찍힐 때.
version: 1.0.0
task_types: [refactor, devops, debugging]
triggers:
  - pattern: "zsh 에서 $(find) 나 $(grep -l) 결과를 변수에 담아 sed/grep 에 넘길 때"
  - pattern: "여러 파일에 같은 치환을 일괄 적용하고 바로 grep 으로 검증할 때"
  - pattern: "에러 메시지 하나에 파일 목록 전체가 한 덩어리로 찍힐 때"
  - pattern: "bash 에서 되던 스크립트가 zsh 에서 조용히 다르게 동작할 때"
category: trap
---

# zsh 는 단어 분할을 안 하고, 그래서 편집과 검증이 같이 죽는다

## Problem

2026-09-12, 문서 이주 중 15개 파일의 경로 참조를 일괄 치환했다.

```bash
# ❌ bash 라면 동작하고 zsh 에서는 전부 실패한다
FILES=$(find STATUS.md HANDOFF.md audit design architecture -name "*.md")
sed -E -i '' -e "s#old#new#g" $FILES
grep -rn '~/Docs' $FILES          # 검증
```

zsh 는 **`$var` 를 단어 분할하지 않는다** (`SH_WORD_SPLIT` 이 기본 off — POSIX 셸과
다른, zsh 의 의도된 설계다). 그래서 `$FILES` 는 개행이 든 **파일명 하나**가 된다:

```
sed: STATUS.md
HANDOFF.md
audit/multiuser-readiness-2026-09-10.md
... (15개 전부) ...
architecture/ux-design.md: No such file or directory
```

에러는 났다. **하지만 진짜 문제는 그 다음이다.**

### 검증이 같은 버그로 함께 죽는다

바로 뒤 `grep -rn '~/Docs' $FILES` 도 **같은 관용구를 썼다.** grep 도 같은 이유로
실패했고, 출력은 이랬다:

```
ugrep: warning: STATUS.md
HANDOFF.md
... : No such file or directory
```

`grep` 이 매치를 못 냈다 = **"잔여 참조 없음"으로 읽힌다.** 즉:

| | 의도 | 실제 |
|---|---|---|
| 편집 | 15개 파일 치환 | **0개 치환** |
| 검증 | 잔여 참조 확인 | **매치 0건 → "깨끗함"** |

**편집이 실패한 것과 검증이 통과한 것이 같은 원인에서 나왔다.** 에러 텍스트를
안 읽고 "매치 0건"만 봤다면 아무것도 안 바꾼 채로 커밋했을 것이다.

> 스크립트에서 **작업과 그 작업의 검증이 같은 관용구를 공유하면, 그 관용구의
> 버그는 검증을 통과시키는 방향으로 작동한다.** 이건 우연이 아니라 구조다 —
> 검증은 보통 "대상 위에서 뭔가를 찾는" 형태이고, 대상 지정이 깨지면 "못 찾음"이 된다.

## Rule

### 1. zsh 에서는 배열을 써라

```bash
# ✅ 배열 + 개별 인자 전개
FILES=(STATUS.md HANDOFF.md audit/*.md design/*.md architecture/*.md)
echo "대상 ${#FILES[@]}건"          # ← 먼저 개수를 찍어라
sed -E -i '' -e "s#old#new#g" "${FILES[@]}"
```

`${#FILES[@]}` 로 **개수를 먼저 출력**하는 습관이 이 함정을 즉시 드러낸다.
1이 나오면 분할이 안 된 것이다.

다른 방법:

```bash
find . -name "*.md" -print0 | xargs -0 sed -i '' -e 's#old#new#g'   # 이식성 최고
FILES=(${(f)"$(find . -name '*.md')"})                               # zsh: 개행 분할
setopt SH_WORD_SPLIT                                                  # 권장하지 않음(전역 동작 변경)
```

### 2. 검증은 편집과 **다른 방식으로** 대상을 지정하라

```bash
# ❌ 같은 변수 → 같은 버그 → 거짓 초록
grep -rn 'old' "${FILES[@]}"

# ✅ 독립적으로 트리를 다시 훑는다. 편집 대상 지정이 틀렸어도 이건 찾아낸다
grep -rn 'old' --include="*.md" . | grep -v node_modules
```

**검증은 편집이 무엇을 대상으로 삼았는지 몰라야 한다.** 편집의 범위 산정이
틀렸을 때 그걸 잡는 게 검증의 일이기 때문이다.

### 3. 양성 대조군 한 줄

치환이 실제로 일어났는지는 "옛 문자열이 없다"가 아니라 **"새 문자열이 있다"**로 세라.

```bash
echo "=== 치환됨 ==="; grep -rhoE 'new-pattern' --include="*.md" . | sort | uniq -c
echo "=== 잔여 ===";   grep -rn  'old-pattern' --include="*.md" .
```

부재만 세면 "대상이 0개였다"와 "전부 치환됐다"를 구분할 수 없다.

## Checklist

- [ ] `$(...)` 결과를 명령 인자로 넘기고 있나 → 배열로 바꿨나
- [ ] 편집 전에 **대상 개수**를 출력했나
- [ ] 검증이 편집과 **다른 경로로** 대상을 찾나
- [ ] 부재(옛 것 없음)뿐 아니라 **존재(새 것 있음)**도 세나
- [ ] 도구의 에러 출력을 실제로 읽었나 — 목록 전체가 한 파일명으로 찍히면 이 함정이다

## Related

- `a-check-that-cannot-flip-is-not-measuring-anything` — 검사가 구조상 한쪽 판정만 낼 수 있는 경우. 이 스킬은 그 원인이 **검사와 작업의 공유 관용구**인 변종이다
- `bulk-code-transform-costs-more-than-it-saves` — 일괄 변환 자체의 손익
- `piped-gate-masks-exit-code` — 파이프가 실패를 가리는 형제 함정
