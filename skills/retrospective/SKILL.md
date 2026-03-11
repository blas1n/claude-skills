---
name: retrospective
description: 어려웠던 작업에서 통찰을 추출해 claude-skills에 자산화 (Self-Evolution)
---

# Retrospective: Self-Evolution

핵심 질문: **"무엇이 어려웠고, 어떻게 극복했는가?"**

어려움을 겪은 경험을 스킬 자산으로 변환하는 프로세스.
순조로운 작업은 대상이 아님 — 예상과 달랐던 것, 실패 후 발견한 것만 자산화 대상.

---

## Step 1: 대화 흐름 리뷰

이번 대화에서 무엇을 시도했는지 돌아보기:

- 어떤 접근을 먼저 시도했는가?
- 어디서 막혔는가?
- 무엇이 예상과 달랐는가?

git은 보조 수단으로 사용:
- 브랜치 분기점 기준으로 `git log --oneline` 참조
- 변경 범위가 큰 경우 `git diff` 참조

---

## Step 2: 어려움 추출 (핵심)

다음 질문에 답하기:

1. **무엇이 예상과 달랐나?** (가정 vs 현실)
2. **어떤 가정이 틀렸나?** (문서, 이전 지식, 직관)
3. **무엇을 새로 발견했나?** (도구, 프레임워크, 패턴의 예상치 못한 동작)
4. **어떤 접근이 실패했고, 왜?**
5. **최종 해결책의 핵심 인사이트는?**

---

## Step 3: 통찰 정제

자산화 가치 판단 기준:

> "이 경험이 없었다면, 다음에도 같은 실수를 반복할 것인가?"

- **Yes** → 반드시 자산화
- **Maybe** → 기존 스킬에 케이스 추가
- **No** → 자산화 불필요 (이미 알고 있는 것)

---

## Step 4: 자산 유형 결정

| 유형 | 대상 | 저장 위치 |
|------|------|-----------|
| 새 스킬 | 재현 가능한 패턴/방법론 | `~/.claude/claude-skills/main/skills/<name>/SKILL.md` |
| 기존 스킬 업데이트 | 빠진 케이스/예외 | 해당 스킬 파일에 섹션 추가 |
| 프로젝트 지식 | 프로젝트 특화 사항 | `.claude/CLAUDE.md` 또는 프로젝트 memory |

---

## Step 5: 스킬 파일 생성

skill-template.md 를 기반으로 새 스킬 파일 작성:

1. `~/.claude/claude-skills/main/skills/<slug>/SKILL.md` 에 Write
2. **커밋은 하지 않음** — 호스트의 auto-commit 폴러가 자동 처리
3. 작성 완료 후 사용자에게 어떤 인사이트가 자산화되었는지 간략 보고

---

## 스킬 이름 규칙

- kebab-case 사용: `docker-dind-setup`, `playwright-web-e2e`
- 구체적 기술/패턴명 포함: `pydantic-settings-gotchas` (O), `config-tips` (X)
- 프레임워크 + 문제 영역: `fastapi-async-db-session`, `react-state-hydration`
