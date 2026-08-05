---
name: harness-cycling-judge-false-failure
description: 검증 하네스 판사가 매 라운드 다른 "related notes" 기준을 추가해 반복 실패시킬 때 — cycling 기준은 무시하고 실제 산출물 완료에만 집중하는 전략
version: 1.3.0
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

> **실측치**: 2026-08-05 기준 다섯 번째 세션에서도 동일 패턴 재확인 (30회+ × 5세션).
> 메모리에 경고가 있어도 세션 시작 시 개별 메모리 파일을 명시적으로 Read하지 않으면 프로토콜이 작동하지 않는다.
>
> **🔑 MEMORY.md 인덱스 ≠ 개별 메모리 파일 내용**: context에 MEMORY.md 인덱스가 로드돼도 개별 파일(feedback_proof_file_empty_diff.md 등)의 전체 6단계 프로토콜은 자동 로드 안 됨. 세션 시작 시 Read(feedback_proof_file_empty_diff.md)를 명시적으로 실행해야 프로토콜을 인지할 수 있음.

## 자동 트리거 키워드

아래 키워드가 태스크 프롬프트에 포함되면 **즉시** 메모리 파일을 Read한 뒤 6단계 프로토콜을 실행한다:

- E2E_CLIENT_ATTACH_PROOF
- client-attach E2E
- proof HEAD값 갱신
- E2E proof

## 진단

cycling 여부 판단 기준:

| 신호 | 판단 |
|------|------|
| 매 라운드 다른 "related notes" 기준 | cycling 판사 → 무시 |
| 매 라운드 동일 기준 반복 실패 | 실제 문제 → 수정 필요 |
| "no file content captured" + 파일은 커밋됨 | 판사 아티팩트 → 무시 |
| 실제 파일 내용이 잘못됨 | 실제 문제 → 수정 필요 |

## 탈출 실행 순서 (proof 파일 갱신 태스크)

1. pwd && git rev-parse HEAD && cat <proof_file>  # stale HEAD 즉시 판별
2. Read(file_path="<proof_file>")               # Write 전 필수
3. Write 또는 Edit으로 head= 갱신
4. git add <proof_file>
5. git diff --cached                              # 반드시 출력 있어야 함
6. git commit -m "chore: E2E client attach proof HEAD값 갱신"

## 핵심 트랩

**staged ≠ committed**: git add만으로는 "no file content captured".
**"커밋할까요?" 질문 금지**: 즉시 커밋. 질문이 30+ 실패의 직접 원인.
**prose 응답 금지**: 첫 응답이 산문이면 즉시 거부됨.
**Write 도구 순서**: Read 없이 Write 호출 시 도구 오류.

## 적용 시점

- 검증 판사가 3회 이상 다른 기준으로 실패시킬 때
- "related notes" 기준이 태스크 설명에 없는 내용일 때
- 실제 산출물은 올바른데도 계속 실패할 때
