---
name: turbopack-rejects-symlinked-node-modules-in-worktree
description: 워크트리에서 npm ci 를 아끼려고 node_modules 를 메인 체크아웃으로 심링크하면 tsc·vitest 는 통과하고 `next build`(Turbopack)만 "Symlink [project]/node_modules is invalid, it points out of the filesystem root" 로 패닉한다. 워크트리마다 진짜 설치를 해라.
---

# Turbopack rejects a node_modules symlink that leaves the project root

## Problem

- 증상: git worktree 의 `web/` 에서 `ln -s ../../main/web/node_modules node_modules` 로 설치를 건너뜀.
  `tsc --noEmit` ✓, `vitest run` ✓ — 그런데 `next build` (Next 16.3, Turbopack) 가
  `FATAL: An unexpected Turbopack error occurred … Symlink [project]/node_modules is invalid, it points out of the filesystem root`
  로 죽는다 (`try_get_next_package → find_package`).
- 근본 원인: Turbopack 은 프로젝트 루트를 파일시스템 루트로 삼고, 그 밖을 가리키는 심링크를 따라가지 않는다.
  tsc·vitest(node resolution)는 심링크를 그냥 따라가므로 **앞 단계 게이트가 전부 초록**이다.
- 흔한 오해: "타입체크·유닛이 됐으니 의존성은 멀쩡하다" — 빌드 도구마다 해석기가 다르다.

## Solution

1. 워크트리에선 심링크 대신 진짜 설치: `rm node_modules && npm ci` (npm 캐시 덕에 수십 초).
2. 심링크를 꼭 써야 한다면 루트 **안**을 가리키게(불가능한 경우가 대부분) — 그냥 설치하라.
3. 워크트리 생성 스크립트가 있으면 설치 단계를 거기에 넣어라.

## Key Insights

- 게이트 순서가 tsc → vitest → build 이면 심링크 문제는 **마지막 단계에서만** 드러난다. 설치를 아낀 시간보다 빌드 재시도가 비싸다.
- 패닉 메시지의 `points out of the filesystem root` 가 결정적 단서 — 버그 리포트 링크에 속지 마라.

## Red Flags

- 워크트리 + `node_modules -> ../../…` 심링크
- `TurbopackInternalError` / `next-panic-*.log` 가 방금 만든 워크트리에서만
- 메인 체크아웃에선 같은 커밋이 빌드된다
