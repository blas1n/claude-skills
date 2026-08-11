---
name: compose-down-leaks-network-silently
description: compose 스택 네트워크에 `docker run --network <project>_default` 로 외부 컨테이너를 붙였다면, 그걸 먼저 지우지 않는 한 `docker compose down -v` 가 네트워크를 못 지운다 — 그런데 **exit 0** 을 낸다("Resource is still in use" 는 stdout 뿐). 실행마다 네트워크가 하나씩 새면서 정리는 성공으로 보고된다. 트리거: compose 스택에 프로브/테스트 컨테이너 붙이기, ephemeral 스택 teardown, `docker network ls` 에 프로젝트 네트워크가 쌓임, "네트워크 이름이 이미 사용 중".
---

# `compose down -v` 는 붙어 있는 네트워크를 못 지우면서 성공이라고 한다

## Problem

일회용 compose 스택에 프로브/테스트 컨테이너를 붙인다. 격리 오버레이가 호스트 포트를 안 열기
때문에(그게 프로덕션과 충돌 안 나는 유일한 이유다) 스택에 닿으려면 **네트워크 안**에 있어야 한다:

```bash
docker compose -p "$P" -f base.yaml -f verify.yaml up -d --wait
docker run -d --name "$P-probe" --network "${P}_default" myimage sleep infinity
# ...프로브 실행...
docker compose -p "$P" -f base.yaml -f verify.yaml down -v      # ← 정리
```

- **증상**: `docker network ls` 에 `<project>_default` 가 **실행 횟수만큼 쌓인다.** 그런데
  teardown 은 매번 성공으로 기록된다.
- **실측**:

```
 Container P-svc-1 Removed
 Network P_default Removing
 Network P_default Resource is still in use     ← 못 지웠다
$ echo $?
0                                               ← 그런데 exit 0
```

- **근본 원인**: compose 는 **자기가 만든 것만** 안다. 외부에서 `docker run --network` 로 붙인
  컨테이너는 compose 의 프로젝트 레이블이 없으므로 `down` 이 지우지 않고, 엔드포인트가 남아
  있으니 `docker network rm` 이 거부된다. compose 는 그 거부를 **경고로 출력하고 넘어간다.**
- **흔한 오해**: "`down -v` 는 전부 지운다." → 전부가 아니라 **자기 프로젝트 것**만이다.

## Solution

**붙인 것을 먼저 떼라.** 순서가 전부다:

```bash
# teardown — 순서가 하중을 받는다
docker rm -f "$P-probe"                                   # 멱등: 없으면 exit 0
docker compose -p "$P" -f base.yaml -f verify.yaml down -v
```

`docker rm -f` 는 없는 컨테이너에 대해 exit 0 이고 `compose down` 도 없는 스택에 exit 0 이라,
이 순서는 그대로 **죽은 점유자의 잔해를 치우는 방어적 teardown** 으로도 쓸 수 있다.

검증까지 하려면 (권장 — 이 결함의 핵심은 조용하다는 것이다):

```bash
test -z "$(docker network ls --filter "label=com.docker.compose.project=$P" -q)"
```

부수 사실(실측, compose v5.1.1 / docker 29):
- 자동 생성 네트워크 이름 = **`<project>_default`**. 명시적 `networks:` 키가 없는 서비스가 전부 거기 붙는다.
- 그 네트워크에 붙은 외부 컨테이너는 compose 임베디드 DNS 로 **서비스 이름을 해석한다**
  (`svc` → 172.x.x.x). 그게 이 패턴이 성립하는 이유다.
- `docker run --network <없는 네트워크>` 는 **크게 실패한다** — 네트워크 이름 규칙이 틀리면
  조용히 잘못 붙는 게 아니라 기동이 죽는다(fail-closed).

## Key Insights

- **정리 명령의 exit code 는 "요청이 접수됐다"이지 "정리됐다"가 아니다.** compose 는 부분 실패를
  경고로 낮춘다. 상태를 관측하지 않으면 누수가 성공으로 보고된다.
- **오케스트레이터는 자기가 만든 것만 안다.** 그 경계 밖에서 자원을 붙였다면, 떼는 것도 내 책임이다.
- 이 결함은 **한 번에 하나씩 조용히** 자란다. 네트워크 하나는 아무 증상이 없고, 수백 개가 되면
  주소 공간이나 iptables 규칙에서 터진다 — 원인에서 아주 멀리 떨어진 곳에서.
- 다음에 먼저 확인할 것: teardown 후 **`docker network ls` / `docker ps -a` 가 실제로 비었는지.**
  테스트로 고정해라(단언 두 줄이면 된다).

## Red Flags

- `docker run --network <project>_default` 가 코드에 있는데 teardown 이 `compose down` 뿐이다
- teardown 로그에 "Resource is still in use" 가 보이는데 파이프라인은 green
- `docker network ls` 출력이 CI 실행 횟수에 비례해 길어진다
- teardown 성공을 exit code 로만 판단하고 **남은 자원을 세지 않는다**
