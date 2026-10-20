---
name: headless-raf-throttle-measures-the-harness
description: 헤드리스 브라우저에서 재생·애니메이션 fps 를 재면 페이지가 아니라 **하네스의 프레임 제한**을 잴 수 있다 — 유휴 rAF 간격(아무것도 안 그릴 때)을 먼저 재서 기준선을 확인하고, fps 판정은 headed 로 하라. 트리거 - requestAnimationFrame 재생 루프, Playwright/Puppeteer 로 fps·jank 측정, "재생이 9fps 로 끊긴다", 성능 수치를 검증 보고서에 적을 때.
---

# 헤드리스 rAF 제한은 페이지 성능이 아니다

## Problem

- 증상: Playwright(`chromium.launch({channel:'chrome'})`, 기본 headless)로 rAF 재생 루프를 3초 돌리니 9.3 fps. 페이지가 느린 것처럼 보였다.
- 근본 원인: 보이지 않는 헤드리스 창에서 Chrome 이 rAF 를 7~15 fps(간격 66~133ms)로 제한했다. 페이지는 **아무것도 안 그려도** 같은 간격이었다.
- 흔한 오해: "프레임마다 SVG·표를 다시 그려서 무겁다" → 렌더 최적화부터 손대기. 실제 1회 렌더는 중앙값 0.5ms 였다.

## Solution

1. fps 를 의심하면 먼저 **유휴 기준선**을 잰다: 페이지 작업 없이 rAF 콜백 간격만 기록.
   ```js
   await page.evaluate(()=>new Promise(res=>{let last=performance.now(),g=[];
     const f=t=>{g.push(t-last);last=t;g.length<30?requestAnimationFrame(f):res(g)};requestAnimationFrame(f);}));
   ```
   기준선이 16ms 가 아니면 측정 환경 문제다.
2. 렌더 비용은 rAF 와 분리해서 잰다: 입력 이벤트를 동기로 N회 dispatch 하고 `performance.now()` 차이의 중앙값/p95.
3. fps 수치는 `headless:false` 로 다시 잰다(이번: 60 fps). 보고서에는 어떤 모드로 쟀는지 함께 적는다.
4. 재생 진행은 경과 시간 기반(`advance(t, elapsedMs, speed)`)으로 짜 두면 프레임이 떨어져도 시간축은 맞는다 — 진행 거리로 fps 를 추정하지 마라.

## Key Insights

- 측정값이 나쁘면 "무엇을 쟀는가"부터: 대상 없이 잰 값(기준선)과 비교하지 않은 숫자는 하네스를 잰 것일 수 있다.
- 렌더 비용(ms/업데이트)과 프레임률(fps)은 다른 질문이다. 전자는 헤드리스에서도 유효하고 후자는 아니다.

## Red Flags

- fps 가 30·15·7.5 처럼 60 의 약수 근처에 붙는다.
- 렌더 1회는 수 ms 인데 fps 만 낮다.
- headless 에서만 끊기고 사람이 열면 부드럽다.
