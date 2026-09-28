---
name: renamed-project-dir-breaks-venv-shebangs
description: 프로젝트 폴더 이름을 바꾸면(mv old new) `.venv/bin/*` 콘솔 스크립트의 shebang 이 옛 절대경로를 가리켜 `uv run pytest/mypy` 가 "Failed to spawn … No such file or directory" 로 죽는다 — 바이너리는 멀쩡히 있고 `uv sync` 는 "Audited" 로 아무것도 안 고친다. 트리거 - 레포/폴더 rename 직후, "Failed to spawn" 인데 .venv/bin 에 파일이 있음, ruff 는 되는데 pytest 만 안 됨.
---

# 폴더를 옮기면 venv 스크립트가 옛 집을 가리킨다

## Problem

- 증상: `uv run mypy collector/` → `error: Failed to spawn: mypy — No such file or directory (os error 2)`. 그런데 `ls .venv/bin` 에 `mypy`·`pytest` 가 **있다**. `uv sync --frozen` 은 "Audited 30 packages" 만 찍고 끝. `uv run python -c 'import sys; print(sys.prefix)'` 는 올바른 `.venv` 를 가리킨다.
- 근본 원인: 콘솔 스크립트는 생성 시점의 **절대경로 shebang** 을 박는다 (`#!/Users/…/hotsmeta/.venv/bin/python`). 폴더를 `hotsmeta → hpgg` 로 바꾸자 그 인터프리터 경로가 사라졌고, 커널이 스크립트를 exec 할 때 "No such file" 은 **스크립트가 아니라 shebang 의 인터프리터**가 없다는 뜻이다. `uv sync` 는 설치된 배포판의 메타데이터만 대조하므로 "이미 설치됨"으로 판단해 스크립트를 다시 쓰지 않는다.
- 흔한 오해: 파일이 있는데 "No such file" 이니 PATH·cwd·dev 그룹 미설치를 의심한다. ruff 는 네이티브 바이너리라 멀쩡히 돌아서 더 헷갈린다.

## Solution

1. `head -1 .venv/bin/pytest` — shebang 경로가 현재 폴더와 다른지 본다. 이게 유일한 확정 신호.
2. `rm -rf .venv && uv sync --frozen` (또는 `uv sync --reinstall`). venv 는 재생성 가능한 로컬 산출물이다.
3. 임시로 급하면 `.venv/bin/python -m pytest` 는 shebang 을 안 거쳐서 돈다 — 진단용으로만.

## Key Insights

- exec 의 ENOENT 는 **대상 파일 또는 그 인터프리터**가 없다는 뜻이다. 파일이 보이면 shebang 을 읽어라.
- 네이티브 바이너리(ruff)는 통과하고 파이썬 엔트리포인트(pytest·mypy)만 죽으면 이 함정이다.
- 폴더/레포 rename 을 한 세션의 다음 세션은 게이트 전에 venv 부터 재생성하라. 이번엔 `| tail` 파이프가 실패를 가려 게이트가 "통과"처럼 흘렀다 — [[piped-gate-masks-exit-code]].
