---
name: notion-mcp-large-page-content-truncates-the-call
description: Notion MCP `create-pages` 에 큰 `content`(대략 10KB+, 한글이면 `\uXXXX` 이스케이프로 3배 부풀어 더 빨리)를 넘기면 툴 호출 JSON 자체가 중간에서 잘려 `InputValidationError: could not be parsed as JSON` 이 난다 — 내용 문제가 아니라 크기 문제다. **create(앞부분) → update-page `insert_content` `{"type":"end"}`(뒷부분)** 으로 나눠라. 문서 아카이빙처럼 긴 마크다운을 옮길 때 반드시 걸린다. 트리거 - Notion 에 긴 문서 이관, create-pages 가 JSON 파싱 에러, 한글 문서를 Notion 페이지로.
version: 1.0.0
task_types: [workflow, content_writing]
triggers:
  - pattern: "Notion MCP 로 긴 마크다운 문서를 페이지로 만들 때"
  - pattern: "notion-create-pages 가 InputValidationError / could not be parsed as JSON 을 낼 때"
  - pattern: "한글 문서를 Notion 에 아카이빙할 때"
  - pattern: "여러 문서를 한 번의 create-pages 호출로 만들려 할 때"
category: trap
---

# Notion MCP 는 큰 content 에서 호출 자체가 잘린다

## Problem

2026-09-12, 세션 인수인계 5건(각 5~21KB 마크다운)을 Notion 으로 아카이빙했다.

- 5.6KB 문서 → ✅ 한 번에 성공
- 10KB 문서 → ❌ `InputValidationError: ... could not be parsed as JSON`

에러 본문이 결정적이다:

```
You sent (first 200 of 17184 bytes): {"parent": {...}, "pages": [{"properties": ...
Common causes: unescaped backslashes, unescaped control characters, or truncated output.
```

**`17184 bytes` 를 보냈다고 하면서 JSON 이 안 닫혔다** — 내용이 잘못된 게 아니라
**호출이 중간에서 끊긴** 것이다. 같은 내용을 반으로 나누니 둘 다 통과했다.

### 한글은 3배로 부푼다

툴 호출 JSON 에서 비ASCII 는 `\uXXXX` 로 이스케이프된다. 한글 1자 = **6바이트**.

| 원본 마크다운 | 호출 JSON 실측 |
|---|---|
| 10,339 bytes (한글 위주) | **17,184 bytes** |

그래서 "10KB 문서"가 실제로는 17KB 페이로드다. **원본 크기로 판단하지 마라.**

## Rule

### 나눠서 만들어라 — create 로 앞부분, insert_content 로 뒷부분

```
1) notion-create-pages
   parent: {type: "page_id", page_id: "<부모>"}
   allow_async: false            # ← id 를 즉시 받아야 다음 단계가 된다
   pages: [{properties: {title}, icon, content: "<앞 절반>"}]
   → 반환된 page id 를 받는다

2) notion-update-page
   page_id: "<위에서 받은 id>"
   command: "insert_content"
   position: {"type": "end"}     # ← 뒤에 이어 붙인다
   allow_async: false
   content: "<뒷 절반>"
```

**끊는 자리**: 마크다운의 `---` 나 최상위 `##` 경계. 표나 코드펜스 **안**에서
자르면 두 조각 다 렌더가 깨진다.

### 목표 크기

| 상황 | 한 호출당 content |
|---|---|
| 영문 위주 | ~10KB 이하 |
| **한글 위주** | **~5KB 이하** (JSON 에서 3배가 된다) |
| 여러 페이지를 한 번에 | 합계로 따져라 — `pages` 배열 전체가 한 호출이다 |

### 순서

부모 페이지를 먼저 만들고(`creation_mode: "draft"` 로 private draft), 그 `page_id`
아래에 자식들을 하나씩 만든다. **자식을 배열로 한꺼번에 만들지 마라** — 합계가 넘는다.

```
create(부모, draft)  → id
  for 문서 in 문서들:
      create(자식, parent=id, content=앞)  → child_id
      update(child_id, insert_content, content=뒤)
```

### 실패해도 재시도로 낫지 않는다

크기 문제라서 같은 페이로드를 다시 보내면 **같은 자리에서 또 잘린다.**
에러를 보면 즉시 분할로 전환하라 — "일시적 오류" 가설에 시간을 쓰지 마라.

## 곁가지 — 원문 아카이빙의 정직성

역사 기록(인수인계·회고·요청)은 **원문 그대로** 옮긴다. 다만 나중 세션이 반증한
대목이 있으면 **원문을 고치지 말고** 인용 블록으로 정정 주석만 덧붙여라:

```markdown
> ⚠️ 이 절은 다음 세션(09-08)에서 반증됐다. 실제는 164·4 였고 …
```

원문을 고치면 "그때 무엇을 믿었나"가 사라지고, 안 고치면 다음 사람이 틀린 진단을
근거로 삼는다. **덧붙이기가 둘 다 지킨다.**

## Checklist

- [ ] content 가 한글 위주면 원본 크기 × 3 으로 페이로드를 어림했나
- [ ] 5KB(한글)/10KB(영문) 넘으면 **처음부터** create + insert_content 로 계획했나
- [ ] 끊는 자리가 표·코드펜스 **밖**인가
- [ ] 부모 id 가 필요하면 `allow_async: false` 로 받았나
- [ ] 여러 페이지를 `pages` 배열에 담았다면 **합계**를 따졌나
- [ ] 원문 아카이빙이면 본문을 고치지 않고 정정을 **덧붙였나**

## Related

- `a-living-doc-repeats-a-fact-and-updates-only-one-copy` — 문서 이주 시 무엇이 살아있나를 먼저 재는 법
- `mcp-remote-tools-attach-race` — MCP 툴 가용성 관련 함정
