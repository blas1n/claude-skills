---
name: agent-executor-host-cwd-leak
description: 워커/오케스트레이터가 코딩 에이전트(opencode/codex/claude-code 같은 HTTP 또는 subprocess 어댑터)를 호출할 때 per-task workspace 를 명시 안 하면, 에이전트는 부모 프로세스의 cwd 를 상속해 호스트 source repo 에 silent edit 을 누적함. 워커가 별도 temp clone 에서 `git status` 를 돌려도 변경 0 으로 보고됨. 진짜 변경은 호스트 working tree 에 있음.
---

# Agent executor host-cwd leak

## 증상

코딩 에이전트가 동작은 하는데 결과물이 0:

- `repo_cloned` 로그 OK
- `artifact_changed_files_captured captured=0` 매 turn 반복
- 11+ turn 돌고도 deliverable 비어있음
- 에이전트 토큰 비용은 정상 (LLM 은 일을 하고 있음)
- 하지만 호스트 `git status` 가 의외의 modified files 를 보임 — 그 내용이 task description 과 의미상 일치

## 진단 한 줄

> "에이전트 cwd 가 어디로 바운드 되었나?"

3 가지 확인:

```bash
# 1. 워커 프로세스의 cwd (subprocess executor 라면 자식이 상속)
lsof -p $WORKER_PID | grep cwd

# 2. 호스트 source repo 의 working tree
cd /path/to/host-source-repo && git status

# 3. 에이전트 HTTP API 가 directory 를 어떻게 받는지 라이브 probe
curl -X POST "$AGENT_URL/session" -H 'Content-Type: application/json' -d '{}' | jq .directory
curl -X POST "$AGENT_URL/session?directory=/tmp" -H 'Content-Type: application/json' -d '{}' | jq .directory
```

호스트 `git status` 에 modified files 가 나오면 끝 — leak 확정.

## 4 패턴

| 채널 | 결정 메커니즘 | 디폴트 | leak 시점 |
|------|---|---|---|
| HTTP API (opencode 등) | body 또는 query param | 프로세스 cwd | API 호출에 directory 안 보내면 |
| subprocess CLI (codex/claude-code) | `cwd=` argument | 부모 cwd | `cwd=workspace_dir` 안 넘기면 |
| Docker exec | `--workdir` | container WORKDIR | 명시 누락 |
| LSP / 임베디드 | rootUri/rootPath | 호출자 cwd | initialize() 에 rootUri 누락 |

핵심: 모든 채널에 **"내가 cwd 를 명시했나?"** 단일 질문으로 환원.

## opencode 1.15.x 함정 (구체)

opencode HTTP `POST /session` 의 경우:

```
POST /session            → directory: process cwd  (default)
POST /session  body: {"directory":"/tmp"}  → directory: process cwd  (BODY IGNORED)
POST /session?directory=/tmp                → directory: /private/tmp  ✓
```

body 의 `directory` 는 silent ignore. query param 만 인정. 문서에 명시 안 됨, 라이브 probe 로만 확인 가능. 

```python
# Wrong (silently broken)
await client.post("/session", json={"directory": workspace_dir})

# Right
await client.post("/session", json={}, params={"directory": workspace_dir})
```

## subprocess executor 함정

```python
# Wrong — fallback "." = parent cwd
workspace = context.get("workspace_dir") or "."

# Right — fail loud
workspace = context.get("workspace_dir")
if not workspace:
    raise ValueError("workspace_dir required for subprocess executor")
```

`"."` 폴백은 production 에서 거의 안 hit 하지만, 한번 hit 하면 leak 이 호스트로 직행함.

## 진단을 미궁에 빠뜨리는 함정

E33-스타일 "git status 기반 변경 캡처" 가 워커 측 per-task workspace 에서 정직하게 돌면, leak 이 있어도 0 으로 보고됨 — **정확하게** 0 으로. 그래서 진단이 "에이전트가 일을 안 한다" 로 흘러감.

반전 신호:
- opencode session_diff (또는 에이전트의 내부 snapshot) 에는 file changes 가 있는데
- 워커의 captured=0
- 호스트 source repo 에 modified files 누적

이 3 조합이면 cwd leak 99%.

## 복구

1. **즉시**: 에이전트 호출에 directory 명시 (API 별 채널)
2. **방어층**: 워커 launchd plist `WorkingDirectory` 를 source repo 가 아닌 중립 디렉토리(`/tmp` 또는 worker-local var dir) 로 변경. 그러면 leak 이 일어나도 source repo 가 아닌 /tmp 로 감
3. **회수**: 호스트에 누적된 변경 중 의미 있는 산출물은 `git stash`/branch 로 살릴 수 있음. 본 세션 사례에서 trust flake fix 가 호스트에 자연 산출된 케이스가 있었음 — salvage 결정은 별건

## TDD 가능한 회귀 테스트

```python
def test_session_create_passes_workspace_dir_as_directory_query():
    serve = _FakeServe()
    executor = _executor_with(serve)
    await _drain(executor.execute("p", {"workspace_dir": "/var/folders/bsvibe-task-XX"}))

    url = serve.session_request_urls[0]
    qs = parse_qs(urlparse(url).query)
    assert qs.get("directory") == ["/var/folders/bsvibe-task-XX"]
```

테스트 fake 가 raw URL 을 capture 해야 함 (body 만 보면 안 됨 — query param 미스 못 잡음).

## 출처

BSVibe E32→E33→E34 dogfood (2026-06-16). PR #341 (E35). 11 act-turn 돌며 captured=0 누적, 호스트 source repo 에 3 파일 silent leak. Lift E33 의 git-diff 캡처가 정확하게 동작했지만 워커가 잘못된 디렉토리를 봤기 때문에 leak 을 가렸음.
