---
name: uv-git-dependency-cache-trap
description: uv aggressively caches git dependencies — uv sync/pip install won't fetch latest commits without explicit cache clean + lock upgrade
version: 1.0.0
---

# uv Git Dependency Cache Trap

## Problem

`uv sync` or `uv pip install` with a git dependency (`pkg @ git+https://...`) installs a **cached old version** even after the remote repo has been updated.

- 증상: 라이브러리의 새 기능/수정이 코드에 없음. `inspect.getsource()`로 확인하면 구버전 소스가 보임
- 근본 원인: uv는 git ref(commit hash)를 `uv.lock`에 고정하고, 캐시에 빌드된 wheel을 보관. `uv sync`는 lock 파일의 commit hash가 바뀌지 않는 한 캐시를 그대로 사용
- 흔한 오해: `uv pip install --reinstall "pkg @ git+https://..."` 하면 최신이 설치될 것이라고 가정 — 실제로는 uv 캐시에서 같은 wheel을 다시 설치

## Solution

3단계로 강제 업데이트:

```bash
# 1. 캐시 제거
uv cache clean <package-name>

# 2. lock 파일에서 해당 패키지 commit hash 업데이트
uv lock --upgrade-package <package-name>

# 3. 새 버전 설치
uv sync
```

### 검증

```bash
# 설치된 소스 확인
python3 -c "import <pkg>; print(<pkg>.__file__)"
# 특정 기능 존재 여부 확인
grep "expected_function" /path/to/installed/module.py
```

## Key Insights

- `uv pip install --reinstall --no-cache` 조합도 uv의 내부 캐시를 완전히 우회하지 못할 수 있음 — `uv cache clean`이 필수
- `uv lock --upgrade-package`가 핵심 — 이것 없이는 lock 파일의 commit hash가 그대로라서 `uv sync`가 같은 버전을 계속 설치
- git dependency를 사용할 때는 `uv.lock`의 commit hash를 확인하는 습관 필요: `grep "commit" uv.lock | grep <pkg>`

## Red Flags

- 라이브러리 GitHub 소스에는 있는 코드가 설치된 패키지에 없음
- `pip show <pkg>`에서 버전은 같은데 기능이 다름
- `--reinstall`해도 동일한 구버전이 설치됨
- 새로 추가된 클래스/메서드에서 `AttributeError` 발생
