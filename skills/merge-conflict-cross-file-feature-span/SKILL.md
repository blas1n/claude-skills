---
name: merge-conflict-cross-file-feature-span
description: 브랜치 충돌 해결 시 상대 브랜치가 추가한 기능이 여러 파일에 걸쳐 있을 때, 충돌 마커가 있는 파일만 수정하면 다른 파일의 변경이 누락되어 런타임 오류가 발생하는 패턴.
metadata:
  type: skill
---

# 병합 충돌 해결 — 기능이 여러 파일에 걸친 경우

## 증상

충돌 파일을 수정하고 커밋했는데, 테스트에서 `AttributeError` 또는 `ImportError`가 발생:

```
AttributeError: 'SomeModel' object has no attribute 'new_field'
```

상대 브랜치가 추가한 기능이 모델(또는 스키마) 파일과 사용 파일 두 군데를 건드렸는데,
충돌 마커가 있는 사용 파일만 수정하고 모델 파일은 놓친 것.

## 원인

병합 충돌 해결 시 "충돌 마커(`<<<<<<<`)가 있는 파일"에만 집중하는 경향이 있다.
그러나 상대 브랜치가 추가한 **기능 커밋 하나**가 여러 파일을 건드렸을 경우,
충돌 마커가 없는 파일에도 추가가 필요한 변경이 있을 수 있다.

Git의 3-way 병합은 두 브랜치가 **같은 줄을 다르게 수정**할 때만 충돌 마커를 삽입한다.
상대 브랜치가 **새 줄을 추가**하고 우리 브랜치가 그 줄을 건드리지 않았다면,
Git은 그 추가를 자동 병합하려 한다 — 하지만 같은 위치가 이미 삭제되어 있거나
다른 파일에 의존성이 있다면 조용히 누락된다.

## 예시 (실제 발생 케이스)

- **main**: `metrics.py`에 `period_start`/`period_end` 필드 추가 + `report.py`에서 해당 필드 사용
- **이 브랜치**: `report.py`의 다른 줄(`_SEP`) 수정
- **충돌**: `report.py`에서 `_SEP` 줄만 충돌 마커 표시
- **실수**: `report.py`만 수정 → `metrics.py`의 필드 추가를 놓침
- **결과**: 테스트에서 `AttributeError: 'SourceMetrics' object has no attribute 'period_start'`

## 해결 방법

### 1. 상대 브랜치 기능 커밋의 파일 목록 먼저 확인

충돌 해결 시작 전, 머지 베이스 이후 상대 브랜치가 건드린 파일 전체를 파악한다:

```bash
# 머지 베이스 이후 main에서 추가된 커밋들이 건드린 파일 전체 목록
git diff $(git merge-base main HEAD) main --stat

# 또는 특정 커밋이 건드린 파일
git show <commit-hash> --stat
```

### 2. 각 파일에 필요한 변경이 있는지 확인

```bash
# main이 각 파일에 뭘 추가했는지 확인
git diff $(git merge-base main HEAD) main -- <파일경로>
```

### 3. 충돌 마커 없어도 누락 여부 검토 후 적용

충돌 마커가 없는 파일도 상대 브랜치의 변경이 논리적으로 필요한지 검토.
특히 **모델/스키마 파일 + 사용 파일** 패턴에서 자주 발생.

## 예방 체크리스트

충돌 해결 시작 전:

```bash
BASE=$(git merge-base main HEAD)

# main이 건드린 파일 전체 목록
git diff $BASE main --stat

# 이 브랜치가 건드린 파일 전체 목록
git diff $BASE HEAD --stat
```

두 목록을 비교해서:
- 겹치는 파일 → 충돌 마커 확인 후 수동 해결
- 겹치지 않는 파일 중 main쪽 → 논리적 의존성 확인 (모델↔사용 관계)

## 트리거 조건

이 스킬이 필요한 상황:
- 병합 충돌 해결 후 `AttributeError`, `ImportError`, `NameError` 발생
- 테스트가 "존재하지 않는 속성/메서드"를 찾지 못함
- 상대 브랜치가 새 기능을 추가했고, 그 기능이 데이터 모델과 사용 코드를 함께 수정한 경우
