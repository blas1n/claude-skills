---
name: stale-migration-pr-splits-alembic-head
description: 마이그레이션이 든 PR 은 열려 있는 동안 다른 마이그레이션이 머지되면 배포를 깨뜨리는 지뢰가 된다 — `down_revision` 이 더 이상 head 가 아닌 리비전을 가리켜 머지 순간 head 가 둘로 갈라지고 컨테이너가 재시작 루프에 빠진다. 그런데 **git 도 브랜치 CI 도 이걸 못 본다**(새 파일이라 충돌 없음 + 브랜치 자체 체인은 단일 head). 트리거 - 며칠 묵은 PR 머지, 마이그레이션 포함 PR, "CI green 인데 배포가 죽었다", `Multiple head revisions are present`, 순차 머지 큐에 마이그레이션 PR 이 둘 이상.
---

# 묵은 마이그레이션 PR 은 alembic head 를 쪼갠다

## Problem

BSVibe #757. 2일 묵은 PR, 머지 직전 상태는 **전부 초록이었다**:

```
lint-and-test = SUCCESS      pwa = SUCCESS
mergeStateStatus = CLEAN     mergeable = MERGEABLE
```

그런데 그대로 머지했으면 **백엔드가 재시작 루프**에 빠졌다.

- 이 PR 의 마이그레이션: `down_revision = "workspace_verify_slots"`
- PR 이 열려 있는 동안 다른 PR(#759)이 `safe_mode_decision_reason` 을 새 head 로 올림
- 머지 결과 체인이 **Y 자로 갈라짐** → `alembic upgrade head` 가
  `Multiple head revisions are present` 로 죽음 → 컨테이너 부팅 실패

`git rev-list --count HEAD..origin/main` = **7**. 브랜치는 7 커밋 뒤였다.

## 왜 아무도 못 잡는가 (핵심)

세 개의 안전장치가 **각자의 이유로 구조적으로 눈이 멀어 있다.**

### 1. git 충돌 감지 — 새 파일이라 충돌할 수가 없다

마이그레이션은 **새로 추가되는 파일**이다. 두 브랜치가 서로 다른 새 파일을 추가하면
git 은 아무 불평 없이 둘 다 받아들인다. 충돌은 *같은 줄*을 고쳤을 때 나는 것이고,
여기서 깨지는 건 **파일 안에 문자열로 적힌 그래프 간선**이다. git 은 그 간선을 모른다.

### 2. 브랜치 CI — 브랜치 자체 체인은 정상적으로 단일 head 다

브랜치에서 `alembic upgrade head` 를 돌리면 **통과한다.** 그 브랜치가 보는 체인은
`… → workspace_verify_slots → one_pr_one_watch` 로 멀쩡한 외줄이기 때문이다.
결함은 브랜치에도 base 에도 없고 **둘의 합집합에만** 존재한다.
→ 브랜치 CI 로는 원리상 절대 잡히지 않는다. 재실행해도, 몇 번을 돌려도 green 이다.

### 3. `mergeStateStatus: CLEAN` — 텍스트 머지 가능성만 말한다

`CLEAN` / `MERGEABLE` 은 "충돌 없이 텍스트를 합칠 수 있다"는 뜻이지
"합친 결과가 의미상 성립한다"는 뜻이 아니다. **초록의 의미를 넓게 읽지 마라.**

## Solution

### 머지 전 점검 (묵은 PR + 마이그레이션이면 항상)

```bash
# 1. 얼마나 뒤쳐졌나
git fetch origin
git rev-list --count HEAD..origin/main      # 0 이 아니면 아래를 반드시 실행
```

```bash
# 2. base 의 현재 head 를 계산하고, PR 의 down_revision 과 대조
python3 - <<'EOF'
import re, os, glob
d = 'backend/data/migrations/versions'
revs, downs = {}, {}
for f in glob.glob(d + '/*.py'):
    s = open(f).read()
    r  = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)', s, re.M)
    dn = re.search(r'^down_revision(?::\s*[^=]+)?\s*=\s*["\']([^"\']+)', s, re.M)
    if r:
        revs[r.group(1)] = os.path.basename(f)
        downs[r.group(1)] = dn.group(1) if dn else None
parents = {v for v in downs.values() if v}
heads = [k for k in revs if k not in parents]
print("HEADS:", [(h, revs[h]) for h in heads])
assert len(heads) == 1, f"SPLIT HEAD: {heads}"      # ← 이 줄이 지뢰를 밟는다
EOF
```

`len(heads) != 1` 이면 머지 금지. 처방:

1. `git rebase origin/main`
2. `down_revision` 을 **base 의 현재 head** 로 교정
3. 단일 head 재확인 (위 스크립트)
4. **일회용 PG 컨테이너**에서 실제로 증명 — 통과 문구만 믿지 말고 DB 를 직접 볼 것

```bash
docker run -d --name freshpg-$$ -e POSTGRES_PASSWORD=fresh \
  -e POSTGRES_USER=x -e POSTGRES_DB=x -p 15499:5432 pgvector/pgvector:pg16
BSVIBE_FRESH_PG_URL="postgresql+asyncpg://x:fresh@127.0.0.1:15499/x" \
  uv run pytest tests/test_alembic_fresh.py -q
# 양성 대조 — "1 passed" 를 믿지 말고 결과를 직접 확인
docker exec freshpg-$$ psql -U x -d x -Atc "select version_num from alembic_version;"
docker exec freshpg-$$ psql -U x -d x -Atc "\di"        # 새 인덱스가 실제로 생겼나
docker rm -f freshpg-$$
```

⚠️ 이 테스트는 `_drop_everything()` 을 호출한다. **절대 살아 있는 DB 를 가리키지 마라.**
반드시 `BSVIBE_FRESH_PG_URL` 로 일회용 컨테이너를 지목할 것.

### 리베이스하면 head 고정 테스트가 충돌한다 (이건 정상)

두 PR 이 같은 head 리터럴을 고쳤으므로 **텍스트 충돌**이 난다. 이건 git 이 잡아주는
부분이라 반갑다. head 는 내 리비전으로 유지하고, 체인 주석에 중간 리비전을 끼워 넣는다.
head 리터럴은 보통 **한 파일이 아니라 여러 파일**에 박혀 있다
→ `alembic-revision-id-32-chars-and-pinned-head`

## Key Insights

- **초록의 범위를 정확히 읽어라.** 브랜치 CI 가 증명하는 명제는 "이 브랜치 단독으로
  성립한다"이지 "main 에 합쳤을 때 성립한다"가 아니다. 결함이 **합집합에만** 사는
  종류라면, 그 결함을 볼 수 있는 관측자는 어디에도 배치돼 있지 않다.
- **텍스트 충돌 없음 ≠ 의미 충돌 없음.** 파일 안에 문자열로 적힌 그래프 간선
  (`down_revision`)은 git 에게 그냥 글자다. 순서·의존성이 문자열로 표현되는 모든 것이
  같은 사각지대를 갖는다 — Django `dependencies`, 순서 있는 seed 파일, lockfile 의 수기 핀.
- **묵은 PR 은 시간이 지날수록 위험해지는데 화면상 상태는 변하지 않는다.** 초록 배지는
  머지된 날이 아니라 **CI 가 돈 날**의 사실이다. 며칠 묵은 PR 의 초록은 과거형이다.
- 한 줄로: **"CI 가 통과했다"가 아니라 "이 결함을 볼 수 있는 관측자가 있었나"를 물어라.**

## Red Flags

- `git rev-list --count HEAD..origin/main` 이 0 이 아닌 PR 에 마이그레이션이 들어 있다
- 순차 머지 큐에 마이그레이션 든 PR 이 **둘 이상** 떠 있다 (서로가 서로를 묵히게 만든다)
- 배포 직후 `Multiple head revisions are present` / 컨테이너 재시작 루프
- PR 이 며칠째 초록인 채로 방치돼 있다 — 초록의 **날짜**를 확인하라
- 마이그레이션 파일이 diff 에서 `create mode`(신규 파일)로 잡힌다 → git 충돌 감지 대상 아님
