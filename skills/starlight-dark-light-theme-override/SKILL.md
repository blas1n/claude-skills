---
name: starlight-dark-light-theme-override
description: Astro Starlight custom theme — overriding light theme with dark colors disables theme toggle silently
version: 1.0.0
task_types: [coding]
triggers:
  - pattern: "Starlight theme toggle not working, or light mode looks identical to dark mode"
---

# Starlight Dark/Light Theme Override Trap

## Problem

Starlight 커스텀 CSS에서 "다크 퍼스트" 디자인을 적용할 때, `:root[data-theme='light']`에도 다크 색상을 넣으면 테마 토글이 시각적으로 작동하지 않는다.

## Wrong Approach

```css
/* `:root`에 다크 색상 설정 */
:root {
  --sl-color-black: #0a0b0f;
  --sl-color-white: #f2f3f7;
}

/* 라이트 모드에도 동일한 다크 색상 → 테마 토글 무용지물 */
:root[data-theme='light'] {
  --sl-color-black: #0a0b0f;  /* 여전히 다크! */
  --sl-color-white: #f2f3f7;
}
```

사용자가 라이트 모드를 선택해도 화면이 변하지 않음.

## Correct Approach

```css
/* 공통 (폰트, 사이즈 등) */
:root {
  --sl-font: 'Plus Jakarta Sans', system-ui, sans-serif;
}

/* 다크 전용 */
:root[data-theme='dark'] {
  --sl-color-black: #0a0b0f;
  --sl-color-white: #f2f3f7;
  --sl-color-gray-5: #2a2d42;
  --sl-color-gray-6: #181926;
}

/* 라이트 전용 — 색상 반전 */
:root[data-theme='light'] {
  --sl-color-black: #ffffff;
  --sl-color-white: #111218;
  --sl-color-gray-5: #e4e6ee;
  --sl-color-gray-6: #f8f9fc;
}
```

## Key Rules

1. **`:root`에는 테마 무관한 값만** (폰트, 사이즈, 모션)
2. **색상은 반드시 `[data-theme='dark']`와 `[data-theme='light']` 각각에**
3. **gray 스케일은 반전**: dark의 gray-5(밝은 보더)가 light에서는 gray-5(밝은 배경)
4. **코드 블록도 조건부**: `pre` 스타일을 `[data-theme='dark'] pre`, `[data-theme='light'] pre`로 분리
5. **accent color**: 라이트 모드에서는 더 진한 톤 사용 (dark: #6366f1, light: #4f46e5)
