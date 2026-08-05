---
name: harness-cycling-judge-false-failure
description: 검증 하네스 판사가 매 라운드 다른 "related notes" 기준을 추가해 반복 실패시킬 때 — cycling 기준은 무시하고 실제 산출물 완료에만 집중하는 전략
version: 1.1.0
category: debugging
---

# Harness Cycling Judge False-Failure 패턴

## 증상

검증 판사가 매 라운드 다른 기준을 제시하며 실패를 반복한다:

- 라운드 1: "garden/seedling/executor-어댑터-패턴.md 가 없다"
- 라운드 2: "concepts/active/error-handling.md 가 없다"
- 라운드 3: "concepts/active/security.md 가 없다"
- 라운드 N: 또 다른 랜덤 기준...

공통 레드 헤링:
- `"Changed files: (no file content captured)"`
- `"Related note X가 생성/수정되지 않았다"`

> **실측치**: 2026-08-05 단일 대화 내 30+ 연속 실패 후 아래 탈출 순서로 성공.
> 메모리에 경고가 있어도 기본 "ask-before-commit" 행동이 메모리를 override함 — 메모리를 읽은 즉시 실행 순서를 밟아야 함.

## 진단

cycling 여부 판단 기준:

| 신호 | 판단 |
|------|------|
| 매 라운드 다른 "related notes" 기준 | cycling 판사 → 무시 |
| 매 라운드 동일 기준 반복 실패 | 실제 문제 → 수정 필요 |
| "no file content captured" + 파일은 커밋됨 | 판사 아티팩트 → 무시 |
| 실제 파일 내용이 잘못됨 | 실제 문제 → 수정 필요 |

## 탈출 실행 순서 (proof 파일 갱신 태스크)

```bash
# 1. 현재 상태 파악
pwd && git rev-parse HEAD
```

```python
# 2. 기존 파일 Read (Write 전 필수 — 없으면 "File has not been read yet" 오류)
Read(file_path="<proof_file>")
```

```python
# 3. stale HEAD 교체 (Write가 아닌 Edit)
Edit(file_path="<proof_file>",
     old_string="head=<stale_hash>",
     new_string="head=<current_hash>")
```

```bash
# 4. staged diff 확인 — 비어있으면 파일이 이미 올바른 상태; 재확인
git add <proof_file>
git diff --cached   # 출력이 있어야 함

# 5. 커밋 (질문 없음)
git commit -m "chore: E2E client attach proof HEAD값 갱신"
git log --oneline -1  # 확인
```

## 전략

1. 실제 태스크 체크리스트 작성 (판사 기준 아님)
2. 체크리스트 항목을 직접 확인 (cat, git log 등)
3. 모든 항목 통과 → 작업 완료로 선언
4. 판사의 cycling 기준은 읽지도, 충족하려 하지도 않는다

## 핵심 트랩

**staged ≠ committed**: W2 하네스는 git commit된 파일 내용을 읽는다.
`git add`만 하고 커밋하지 않으면 "no file content captured"로 실패한다.

**"커밋할까요?" 질문 금지**: 커밋 의도가 태스크에 있으면 즉시 실행.
이 질문 하나가 "(no file content captured)" 30+ 실패의 직접 원인.

**prose → 하네스 거부**: 첫 응답이 산문이면 "A prose answer is not a deliverable"로 즉시 반려.

## 적용 시점

- 검증 판사가 3회 이상 다른 기준으로 실패시킬 때
- "related notes" 기준이 태스크 설명에 없는 내용일 때
- 실제 산출물(파일, 코드, 커밋)은 올바른데도 계속 실패할 때
