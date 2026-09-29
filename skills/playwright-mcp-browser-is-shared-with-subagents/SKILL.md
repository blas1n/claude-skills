---
name: playwright-mcp-browser-is-shared-with-subagents
description: Playwright MCP 브라우저는 메인 세션과 병렬 서브에이전트가 **같은 브라우저·같은 탭**을 쓴다. 에이전트가 돌고 있는 동안 MCP 로 라이브 검증을 하면 남의 navigate/입력이 끼어들어 "URL 과 결과가 안 맞는다", "안 부른 데이터가 뜬다" 같은 유령 버그가 보인다. 트리거 - 백그라운드 에이전트가 떠 있는 상태의 browser_navigate/evaluate 검증, 결과와 URL 불일치, 네트워크 기록에 요청이 없는데 화면엔 데이터, 페이지가 갑자기 다른 페이지로 바뀜.
---

# Playwright MCP 브라우저는 공용이다 — 병렬 에이전트가 있으면 검증은 독립 헤드리스로

## Problem
2026-09-29 hpgg: 워크트리 서브에이전트 4개가 병렬로 UI 를 만들고 있을 때, 메인 세션이 MCP 브라우저로 라이브 전적검색을 검증했다.
- 증상: URL 은 `region=KR` 인데 결과는 "아메리카", 서버 로그엔 그 요청이 없음, 화면의 "09:25 기준"은 에이전트가 픽스처를 녹화한 시각, `performance` 에도 API 요청 0건 — 그리고 마지막엔 `main` 이 **전장 상세 페이지**(에이전트 작업물)로 바뀌어 있었다.
- 근본 원인: MCP 서버 프로세스 하나가 브라우저 하나를 띄우고, 메인과 서브에이전트가 전부 그 탭을 조작한다. 내 evaluate 사이사이에 에이전트의 navigate 가 끼어들었다.
- 흔한 오해: "URL 동기화 버그" · "CF 엣지 캐시" · "프로덕션에 픽스처가 섞였다" — 세 가설을 차례로 쫓으며 코드를 읽었다. 전부 헛다리.

## Solution
1. 백그라운드 에이전트가 하나라도 돌고 있으면 MCP 브라우저로 검증하지 않는다.
2. 레포에 설치된 playwright 로 **독립 헤드리스 스크립트**를 돌린다(새 브라우저 인스턴스, 요청 로깅 포함):
```js
// web/.check-tmp.mjs — node 가 web/node_modules 에서 playwright 를 찾도록 web/ 안에 둔다(NODE_PATH 는 ESM 에 안 먹는다)
import { chromium } from 'playwright';
const b = await chromium.launch(); const p = await b.newPage();
const calls = []; p.on('request', r => r.url().includes('api.') && calls.push(r.url()));
await p.goto(URL); /* 사람처럼 selectOption → fill → press('Enter') */
console.log(p.url(), calls, (await p.locator('main').innerText()).slice(0, 300));
await b.close();
```
3. 서브에이전트 프롬프트에도 "시각 검증은 자기 헤드리스 스크립트로, 공용 MCP 브라우저 금지"를 적는다.

## Key Insights
- 이상한 결과가 **내가 한 조작으로 설명되지 않으면**, 코드보다 먼저 "누가 이 브라우저를 같이 쓰는가"를 의심하라.
- 합성 이벤트(value setter + requestSubmit)로 폼을 조작한 검증은 그 자체로 신뢰도가 낮다 — 실제 입력 API(fill/selectOption/press)로.

## Red Flags
- 백그라운드 Agent 가 실행 중인데 `mcp__playwright__*` 로 검증 중
- 네트워크 기록/서버 로그에 요청이 없는데 화면엔 데이터가 있음
- evaluate 사이에 `location.href`·페이지 제목이 바뀜
