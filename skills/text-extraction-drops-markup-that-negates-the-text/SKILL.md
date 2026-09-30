---
name: text-extraction-drops-markup-that-negates-the-text
description: HTML 을 `.text()`/`get_text()`/innerText 로 긁으면 **의미를 뒤집는 마크업**(<s>/<del>/<strike> 취소선, <ins>, hidden, 인라인 옛 값)이 평문에 섞여 들어가 철회된 문장이 살아 있는 문장으로, "35 40" 같은 뭉친 숫자로 나온다. 스크래핑 파서를 쓰기 전에 원문에서 `<s>` 등을 grep 하라. 트리거 - 패치 노트·공지·약관·changelog 스크래핑, BeautifulSoup/HTMLParser 로 본문 추출, "40 50초"처럼 숫자가 두 개 붙은 줄, 수정 이력이 있는 공식 문서.
version: 1.0.0
task_types: [coding, data]
triggers:
  - pattern: "scrape official notes / announcements / changelogs from HTML"
  - pattern: "a parsed line contains two numbers back to back like '35 40'"
category: trap
---

# Text extraction drops markup that negates the text

## 사례 (HPGG #62, 2026-09-30)
블리자드 패치 노트를 파싱해 영웅별 ▲▼ 를 붙였다. 테스트 초록, 화면 정상. 분포를 보다가 방향 없는 줄에서 `재사용 대기시간이 40 50초 감소` 를 발견 → 원문 grep:
- `<s>Dwarf Toss cooldown increased by 2 seconds.</s>` — **줄 전체 취소선 = 블리자드가 철회한 변경.** 파서는 무라딘에게 ▼ 너프로 표시하고 있었다.
- `increased to <s>35</s> 40 from 30` — **인라인 취소선 = 수정 전 값.** 평문엔 "35 40".

`_Node.text()` 가 태그를 무시하고 자식 텍스트를 다 이었기 때문. 공식 문서는 **발행 후 고쳐지고, 고친 흔적을 취소선으로 남긴다.**

## 규칙
1. 파서 쓰기 전 원문에서 `grep -c '<s>\|<del>\|<strike>\|hidden' *.html` — 0 이 아니면 의미를 먼저 정해라.
2. 기본값: 취소선 안 텍스트는 **본문이 아니다**. 텍스트 수집기에서 해당 태그를 빈 문자열로(`if tag in {"s","del","strike"}: return ""`). 줄이 통째로 비면 그 줄도 사라진다.
3. 파서 버전을 올려 이미 저장된 결과를 재파싱시켜라 — 고친 파서가 과거 데이터에 안 닿으면 화면은 그대로다.
4. 테스트는 **실제 픽스처**에서 철회된 줄이 없는지 + 인라인은 새 값만 남는지(`"increased to 40 from 30"`) 둘 다.
5. 센서: 방향 판정이 안 되는 줄을 샘플로 40개쯤 읽어라. 숫자가 붙어 나오는 줄이 신호다.
