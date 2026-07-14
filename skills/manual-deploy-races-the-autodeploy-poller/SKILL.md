---
name: manual-deploy-races-the-autodeploy-poller
description: 배포 폴러(launchd/cron, N초 주기)가 이미 같은 compose 명령을 돌리고 있는데 손으로 `docker compose up`을 치면 두 프로세스가 같은 컨테이너를 동시에 recreate 하다가 "container name is already in use" 충돌 → 컨테이너가 Exited 로 남고 **프로덕션이 죽는다**. 트리거: 머지 후 수동 배포, "이 프로젝트는 자동배포 안 되는 것 같다"는 판단, 컨테이너 이름 충돌.
---

# 수동 배포가 자동배포 폴러와 경합해서 프로덕션을 내린다

## Problem

머지 후 "배포해야지" 하고 손으로 친다:

```bash
docker compose -p myproj -f compose.yaml -f compose.prod.yaml up -d --build backend worker
```

그런데 **launchd/cron 폴러가 120초마다 같은 명령**을 돌리고 있었다.

- **증상**:
  ```
  Error response from daemon: Conflict. The container name "/abc123_myproj-backend-1"
  is already in use by container "9c03ae...". You have to remove (or rename) that container
  ```
  그리고 잠시 뒤 `docker ps -a`:
  ```
  abc123_myproj-worker-1   Created          ← 폴러가 만든 유령
  myproj-backend-1         Exited (1)       ← 프로덕션 다운
  ```
- **근본 원인**: compose 의 recreate 는 *기존 컨테이너를 임시 이름(`<hash>_<name>`)으로 rename → 새 컨테이너 생성 → 옛것 제거* 순서다. 두 프로세스가 이걸 동시에 하면 **rename 중간 상태에서 이름이 겹쳐** 양쪽 다 실패하고, 옛 컨테이너는 stop 된 채 남는다.
- **흔한 오해 (내가 한 실수)**: **"이 프로젝트는 자동배포 대상이 아니다"** 라고 *부분 grep* 으로 단정했다.
  `autodeploy.sh` 상단의 `PROJECTS=(...)` 배열에 이름이 없어서 아니라고 판단했는데,
  **파일 아래쪽에 그 프로젝트만을 위한 별도 블록**이 있었다 (`# --- myproj (separate block) ---`).

## Solution

**배포 전에 "누가 이미 배포하고 있는가"를 확인한다.**

```bash
# 1) 폴러/스케줄러가 있는가
launchctl list | grep -i deploy          # macOS
systemctl list-timers | grep -i deploy   # linux
crontab -l | grep -i deploy

# 2) 스크립트를 grep 하지 말고 READ 한다 (별도 블록이 아래에 있을 수 있다)
grep -n "myproj" ~/scripts/autodeploy.sh   # 배열만 보지 말 것
tail -40 ~/logs/autodeploy.log             # 최근에 이 프로젝트를 배포했는가?
```

**폴러가 있으면 → 손대지 말고 머지만 하면 된다.** 알아서 배포된다.

정말 손으로 해야 하면 **폴러를 먼저 멈춘다**:

```bash
launchctl unload ~/Library/LaunchAgents/com.x.autodeploy.plist
# ... 배포 + 검증 ...
launchctl load   ~/Library/LaunchAgents/com.x.autodeploy.plist
```

### 사고 후 복구

```bash
docker ps -a | grep myproj                      # <hash>_ 접두사 유령들을 찾는다
docker rm -f <hash>_myproj-backend-1 <hash>_myproj-worker-1
docker compose -p myproj ... up -d --build      # 이름이 비었으니 이제 성공
```

## Key Insights

- **머지 = 배포인 환경에서 수동 배포는 이득이 0이고 리스크만 있다.** 폴러가 2분 안에 한다.
- **`grep` 한 줄로 "없다"를 결론짓지 마라.** 배열/목록에 없다고 처리 대상이 아닌 게 아니다 —
  같은 파일 아래에 예외 블록이 있을 수 있다. **없음을 주장하려면 파일을 읽어라.**
  (부재를 검증하지 않는 확인은 확인이 아니다 — [[capability-guard-must-assert-presence]] 와 같은 뿌리)
- compose 의 recreate 는 원자적이지 않다. **동시 실행 = 이름 충돌 = 프로덕션 다운.**
- 컨테이너 이름에 `<hash>_` 접두사가 붙어 있으면 **recreate 가 중간에 깨진 것**이다. 즉시 정리하라.

## Red Flags

- 머지 직후 손으로 `docker compose up` 을 치려 한다 → **먼저 폴러를 확인했는가?**
- `Conflict. The container name ... is already in use`
- `docker ps -a` 에 `<hash>_<name>` 형태의 `Created`/`Exited` 컨테이너
- 배포 로그에 "Prod build failed!" 가 내가 배포한 시각과 겹친다
- "이 프로젝트는 자동배포 안 되는 것 같다"고 방금 결론냈다 → **스크립트를 끝까지 읽었는가?**
