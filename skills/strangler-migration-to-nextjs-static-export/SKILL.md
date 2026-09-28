---
name: strangler-migration-to-nextjs-static-export
description: Vite/바닐라 TS 멀티페이지를 Next.js(App Router, output export) + Tailwind v4 로 옮길 때 — 페이지를 한 번에 다 다시 쓰지 말고 옛 명령형 모듈을 새 셸 안에서 돌리는 스트랭글러 방식과, 그때 조용히 터지는 세 함정(루트 `static/` 자동 export, 층 없는 레거시 CSS 가 유틸리티를 이김, 레거시 클래스명을 테스트 훅으로 재사용). 트리거 - Next 이전, output export + GitHub Pages, Tailwind v4 에 기존 CSS 공존, "디자인이 이상하게 섞인다", dist 에 모르는 폴더.
---

# 스트랭글러로 Next static export 에 옮기기 — 그리고 조용한 함정 셋

## Problem

UI 전면 개편 + 프레임워크 이전을 한 PR 에서 하면 모든 페이지를 동시에 다시 쓰게 되고, 동작 회귀를 e2e 로 잡기 전에 PR 이 거대해진다. 그래서 셸과 첫 페이지만 React 로 쓰고 나머지는 옛 코드를 그대로 돌리는데, 그 공존에서 세 가지가 **에러 없이** 틀어진다.

1. **루트 `static/` 폴더** — 리다이렉트 스텁을 `web/static/` 에 뒀더니 `dist/static/hots/*.html` 로 튀어나왔다. Next 는 프로젝트 루트의 `static/` 을 **폐기된 레거시 정적 폴더로 아직 인식**해 export 에 복사한다. 경고 없음.
2. **층 없는 레거시 CSS** — Tailwind v4 유틸리티는 `@layer utilities` 안에 있다. 레거시 CSS 를 그냥 import 하면 **층 밖(unlayered) 규칙이 모든 층을 이긴다**. `a { color: … }`, `body { background: … }`, `dl/dd` 같은 맨 선택자가 새 컴포넌트의 유틸리티를 덮었다.
3. **레거시 클래스명 = 테스트 훅** — e2e 셀렉터를 살리려고 새 컴포넌트에 `role-card`·`mover-row`·`map-card`·`badge` 를 붙였더니, 레거시 CSS 의 같은 이름 규칙이 박스·테두리를 덧입혔다(KPI `dl` 에 카드 배경까지).

## Solution

1. 옛 페이지는 **`dangerouslySetInnerHTML` 골격 + `useEffect` 에서 옛 모듈 `run()`**. React 는 그 안쪽을 재조정하지 않으므로 명령형 DOM 조작과 싸우지 않고 `<template>` 도 동작한다. StrictMode 이중 effect 는 `useRef` 가드로.
   ```tsx
   const started = useRef(false);
   useEffect(() => { if (started.current) return; started.current = true; void load().then((m) => m.run(slug)); }, []);
   return <div dangerouslySetInnerHTML={{ __html: html }} />;
   ```
2. 레거시 CSS 는 **층에 가두고 유틸리티 아래에** 둔다. 그리고 `html/body/a/*` 같은 전역 규칙은 지우거나 스코프를 건다.
   ```css
   @layer theme, base, legacy, components, utilities;
   @import "tailwindcss/theme.css" layer(theme);
   @import "tailwindcss/preflight.css" layer(base);
   @import "tailwindcss/utilities.css" layer(utilities);
   @import "./legacy.css" layer(legacy);
   ```
3. 새 컴포넌트의 테스트 훅은 **`data-*` 속성**(`data-card="role"`)으로. 레거시 클래스명을 재사용하지 마라 — e2e 를 새 훅으로 고치는 게 싸다.
4. 루트 폴더 이름에 `static`·`public`·`app`·`pages` 를 쓰지 마라 (`legacy-redirects/` 처럼). export 후 `ls dist` 로 **모르는 폴더가 없는지** 본다.
5. `distDir` 을 주면 `output: "export"` 결과가 그 폴더로 간다 (기존 CI 의 `web/dist` 경로 유지 가능). 데이터 폴더는 빌드 전 스크립트로 `public/` 에 복사(gitignore)하고 점 파일(로그)은 필터.
6. e2e 는 `next start` 가 아니라 **Pages 의미론 정적 서버**(디렉터리→index.html, 없으면 404.html + 404)로 돌려야 404·trailing slash 가 실제와 같다.

7. **`output: "export"` + `distDir` 이면 `next build` 는 export 만 distDir 로 보내고 내부 산출물은 여전히 `.next` 에 쓴다** (`.next/BUILD_ID` 의 mtime 이 증거). 그래서 개발 서버가 `.next` 를 쓰면, 떠 있는 동안 빌드(e2e 포함)를 돌릴 때마다 청크가 덮여 폰에서 `Cannot find module './611.js'` (webpack-runtime / _document) 가 **무한 반복**된다. 개발 서버에 **전용 폴더**를 줘라 — `.next` 로 "분리"한 첫 수정은 같은 폴더라 재발했다.
   ```ts
   export default (phase: string) => ({ distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : (process.env.NEXT_DIST_DIR ?? "dist"), ... });
   ```
   검증은 재현 조건 그대로: dev 를 켠 채 빌드 → 페이지가 여전히 200 인가.
8. **e2e 가 `public/` 을 픽스처로 덮어쓰면** 떠 있는 개발 서버가 테스트 데이터를 서빙한다. e2e 스크립트 끝에서 실데이터를 되돌려라 (`playwright test; s=$?; node scripts/sync-data.mjs; exit $s`).

## Key Insights

- 셋 다 에러가 없다. 신호는 **스크린샷**(새 컴포넌트에 없는 테두리)과 **`ls dist`**(모르는 폴더) 뿐이다 — 이전 직후 둘 다 눈으로 봐라.
- CSS 우선순위는 v4 에서 "특이도"가 아니라 "층"이 먼저다: 층 밖 규칙은 `.text-white` 도 이긴다.
- 스트랭글러는 e2e 가 동작을 고정하고 있을 때만 안전하다. 첫 초록은 전선 하나를 끊어 빨개지는지 확인하라 — [[a-check-that-cannot-flip-is-not-measuring-anything]].
