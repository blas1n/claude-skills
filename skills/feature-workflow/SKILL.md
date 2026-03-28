---
name: feature-workflow
description: TDD+E2E 전체 워크플로우. 기능 작업 시작 전 테스트/체크리스트 작성, 구현, 검증, 커밋까지 안내.
version: 1.0.0
---

# Feature Workflow: TDD + E2E

기능 구현의 전체 수명주기를 안내하는 스킬.
테스트 먼저 → 구현 → 검증 → 커밋.

## Iron Laws

1. **테스트 없이 프로덕션 코드 없음** - 실패하는 테스트가 먼저
2. **검증 없이 커밋 없음** - 모든 테스트 통과 + e2e 체크리스트 확인 후 커밋
3. **실패 무시 금지** - 실패 항목은 수정 완료까지 반복

---

## Phase 1: Setup (코딩 전)

### 1a. 유닛 테스트 작성 (RED)

구현할 기능의 핵심 동작을 테스트로 먼저 정의:

```bash
# Python
uv run pytest tests/test_<feature>.py -v  # → 실패 확인 (RED)

# Node
npm test -- --testPathPattern=<feature>   # → 실패 확인 (RED)
```

**체크포인트**: 테스트가 올바른 이유로 실패하는지 확인 (ImportError 등이 아닌 기능 미구현으로 실패)

### 1b. E2E 체크리스트 작성

`docs/e2e/<feature>-checklist.md` 파일 생성 (e2e-checklist-template.md 참조):

#### 웹 프로젝트 판단 기준
- UI/프론트엔드 컴포넌트 포함 (React, Vue, Next.js, Svelte 등)
- 브라우저 인터랙션이 필요한 기능 (폼, 네비게이션, 렌더링 등)

#### 웹 프로젝트인 경우
- Playwright 테스트를 직접 작성 (`tests/e2e/<feature>.spec.ts`)
- playwright.config가 없으면 설치/설정부터 진행:
  ```bash
  npm init playwright@latest
  ```
- 체크리스트의 각 항목을 `test()` 블록으로 변환

#### 비웹 프로젝트인 경우
- 체크리스트를 markdown으로 작성
- Phase 3에서 Claude가 항목별로 직접 검증

---

## Phase 2: Implementation (GREEN → REFACTOR)

TDD RED-GREEN-REFACTOR 사이클:

1. **GREEN**: 테스트를 통과하는 최소한의 코드 작성
2. **REFACTOR**: 테스트가 통과하는 상태에서 코드 정리
3. 각 사이클마다 테스트 실행으로 확인

```bash
# Python
uv run pytest tests/ --tb=short -q

# Node
npm test
```

---

## Phase 3: Verification (전체 검증)

### 유닛 테스트 + 커버리지

```bash
# Python
uv run pytest tests/ --cov=<src_dir> --cov-fail-under=80

# Node
npm test -- --coverage
```

### E2E 검증

**웹 프로젝트**: Playwright 실행
```bash
npx playwright test
```

**비웹 프로젝트**: 체크리스트 항목별 검증
- `docs/e2e/<feature>-checklist.md` 읽기
- 각 `- [ ]` 항목에 대해 실제 실행/확인
- 통과 시 `- [x]`로 업데이트

### 실패 시

- 실패 원인 분석 → 수정 → Phase 2로 돌아감
- 모든 항목 통과까지 반복

---

## Phase 4: Commit

모든 검증 통과 후:

```bash
# 코드 품질 확인
uv run ruff check <src_dir>/        # Python
uv run ruff format --check <src_dir>/

# 커밋
git add <관련_파일들>
git commit -m "feat(<scope>): <설명>"
```

**주의**: PreToolUse 훅이 git commit 시 자동으로 테스트를 재실행하여 검증함.
테스트 실패 시 커밋이 차단됨.
