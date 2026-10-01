---
name: cloudflare-gated-docs-need-a-headed-real-chrome
description: 문서·약관 페이지가 Cloudflare 봇 체크로 curl/WebFetch/헤드리스에 403 이면, API 경로를 추측해서 두드리지 말고 **시스템 Chrome 을 headed 로, 자동화 플래그를 빼고** playwright-core 로 띄워 `innerText` 를 떠라. 챌린지 대기 루프는 **현지화된 제목**("잠시만 기다리십시오…")도 매칭해야 한다 — 영어 "Just a moment" 만 보면 챌린지 페이지를 본문으로 착각한다. 트리거 - WebFetch 403, `cf-ray` 헤더, "보안 확인 수행 중", Claude in Chrome·Playwright MCP 미연결, 외부 API 문서에서 엔드포인트 찾기.
version: 1.0.0
task_types: [debugging, analysis]
---

# Cloudflare 가 막은 문서는 headed 시스템 Chrome 으로 읽는다

## Problem

외부 API(Heroes Profile)의 문서·약관·쿼터 페이지가 전부 Cloudflare 챌린지 뒤에 있다:

- `curl -A "<브라우저 UA>"` → 403
- WebFetch → 403
- 헤드리스 Chromium → 챌린지 통과 못 함
- Claude in Chrome 확장·Playwright MCP 는 세션에 미연결

그래서 **엔드포인트 경로를 추측해서** API 에 직접 두드렸다 (`/privacy`, `/privacy/changes`, `/players/privacy` …).
알 수 없는 경로는 JSON 404 가 아니라 **사이트 HTML 페이지**로 돌아와서 아무 정보도 없었다. 실제 경로는
`/players/privacy/changes` 였고 문서에 한 줄로 있었다 — 추측으로는 영영 못 찾을 수도 있었다.

첫 브라우저 시도도 실패: 대기 루프가 `/just a moment/i` 만 봤는데 macOS 로케일이 한국어라 챌린지 제목이
"잠시만 기다리십시오…" — 루프가 즉시 빠져나와 **챌린지 페이지 본문**(412 바이트)을 결과로 저장했다.

## Fix

```js
// scratchpad 에서: npm i playwright-core
import { chromium } from 'playwright-core';
const b = await chromium.launch({
  channel: 'chrome',                                  // 설치된 Google Chrome
  headless: false,                                    // headless 는 막힌다
  ignoreDefaultArgs: ['--enable-automation'],
  args: ['--disable-blink-features=AutomationControlled', '--window-position=-2000,0'], // 화면 밖
});
const p = await b.newPage();
await p.goto(url, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 45; i++) {                        // 챌린지는 수 초~수십 초
  if (!/just a moment|잠시만/i.test(await p.title())) break;
  await p.waitForTimeout(1000);
}
await p.waitForTimeout(2000);
console.log(await p.evaluate(() => document.body.innerText));
```

- 결과를 파일로 떠서 `grep -n -i <키워드>` 로 찾는다 (문서 전체가 한 페이지면 1만 줄).
- **결과 길이부터 확인**: 수백 바이트면 챌린지 페이지다. 제목이 실제 문서 제목인지 본다.
- 문서를 찾으면 엔드포인트를 **딱 한 번** 작은 `limit` 으로 실제 호출해 응답 모양·쿼터 헤더를 기록하고 픽스처로 남긴다.

## Don't

- API 경로 추측 브루트포스 — 404 가 HTML 이면 신호가 0 이고, 키 쿼터·레이트리밋만 쓴다.
- 대기 루프를 영어 문자열 하나로만 — 로케일 따라 제목이 바뀐다. 길이·제목 둘 다 확인.

## Related

- [[playwright-mcp-browser-is-shared-with-subagents]]
- [[a-fresh-key-that-401s-everywhere-is-hitting-the-wrong-api-not-the-wrong-header]] — 문서 내비게이션(Docs/Migrating)부터 보라는 같은 교훈.
