# E2E Checklist Template

기능 작업 시 `docs/e2e/<feature-name>-checklist.md`로 복사해 사용.

---

# E2E Checklist: <feature-name>

Created: <YYYY-MM-DD>
Type: <web | api | cli | library>

## Happy Path

- [ ] <주요 시나리오 1: 정상적인 입력 → 기대 결과>
- [ ] <주요 시나리오 2: 일반적인 사용 흐름>

## Edge Cases

- [ ] <빈 입력 / 최소값>
- [ ] <최대값 / 경계값>
- [ ] <동시성 / 중복 요청>

## Error Handling

- [ ] <잘못된 입력 → 적절한 에러 메시지>
- [ ] <외부 서비스 장애 → graceful degradation>
- [ ] <권한 없는 접근 → 403/401>

## Playwright Scenarios (웹 프로젝트)

웹 프로젝트의 경우, 위 체크리스트 항목을 Playwright 테스트로 변환:

```typescript
// tests/e2e/<feature>.spec.ts
import { test, expect } from '@playwright/test';

test('<시나리오 1>', async ({ page }) => {
  await page.goto('/<경로>');
  // 검증 로직
});
```
