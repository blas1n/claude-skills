---
name: a-background-only-hang-may-be-an-os-consent-prompt
description: "데몬·launchd·systemd·CI 러너에서만 나는 행(hang)을 셸에서 replay 하면 영원히 성공한다 — argv 도 env 도 cwd 도 같은데. 그때 남은 변수는 '누가 띄웠는가' 하나뿐이고, macOS 라면 TCC 동의 프롬프트가 답할 세션 없이 영구 pending 된 것일 수 있다. 프로세스는 살아 있고, 소켓은 0개고, openat 에서 100% 블록한다. 트리거 - '백그라운드에서만 재현된다', 셸 replay 가 계속 성공, 출력이 단 한 줄도 없는 타임아웃, 서명 없는 런처(uv/homebrew/nvm)로 띄운 launchd 잡."
version: 1.0.0
task_types: [debugging, ops]
triggers:
  - pattern: "데몬/launchd 안에서만 행 나고 셸에서 같은 명령은 성공할 때"
  - pattern: "타임아웃인데 자식 프로세스가 출력을 단 한 줄도 안 냈을 때"
  - pattern: "argv·env·cwd 를 다 베꼈는데도 재현이 안 될 때"
  - pattern: "서명 없는 런처(uv, homebrew, nvm)로 launchd/LaunchAgent 를 띄우고 있을 때"
category: trap
---

# 백그라운드에서만 나는 행은 OS 동의 프롬프트일 수 있다

## 무슨 일이 일어나는가

macOS TCC(그리고 유사하게 키체인·권한 다이얼로그)는 보호 자원 접근 시 **동의 창을 띄우기로
결정**할 수 있다. launchd 백그라운드 잡에는 그 창을 띄우고 답할 세션이 없다. 요청은 거부되지
않는다 — **영구 pending** 된다. 그 사이 커널의 `openat` 은 **영원히 반환되지 않는다.**

결과가 고약하다: 프로세스는 **살아 있고**, 종료 코드도 없고, stderr 도 비어 있다.
바깥에서는 "그냥 응답이 없다"로만 보인다.

## 왜 replay 가 계속 성공하는가

셸에서 돌리면 **책임 프로세스(responsible process)** 가 다르다. 터미널·IDE 는 이미 TCC 결정이
기록돼 있어 **프롬프트 자체가 안 뜬다.** 그래서 argv·env·cwd 를 아무리 정확히 베껴도
재현되지 않는다.

> **환경을 복사할 때 부모도 환경이다.** "재현이 안 된다"는 재현 조건을 아직 못 베꼈다는 뜻이지,
> 그 가설이 틀렸다는 뜻이 아니다.

## 어떻게 확인하는가 — 프로세스가 **살아 있는 동안에만** 얻어진다

```bash
lsof -p <pid> -i -n -P        # 소켓 0개 = API 접속조차 안 했다 (모델 대기가 아니다)
sample <pid> 5 -f /tmp/s.txt  # 메인 스레드가 openat$NOCANCEL 에서 100% 블록하는지
ps -Ewwo command= -p <pid>    # env 전량 — 그대로 복사해 replay 할 수 있다
lsof -p <pid> -a -d cwd -Fn   # cwd
```

그리고 **같은 초의 TCC 로그**를 본다. msgID 하나를 끝까지 추적하는 게 핵심이다:

```bash
/usr/bin/log show --last 15m --predicate 'subsystem == "com.apple.TCC"' --style compact
```

정상 종결은 `REQUEST → AUTHREQ_CTX → AUTHREQ_RESULT → REPLY`.
**행은 `AUTHREQ_PROMPTING` 에서 멈추고 RESULT·REPLY 가 둘 다 없다.**

## 🚨 `log` 는 zsh 빌트인이다

```bash
log show --last 5m          # zsh: too many arguments — 조용히 죽는다
/usr/bin/log show --last 5m # 이걸 써라
```

빌트인 버전은 **rc=0 으로 0줄**을 뱉는다. 양성 대조군(전체 줄 수)을 안 세면
**"TCC 기록 없음 ⇒ TCC 아님"으로 오판**하고 진짜 원인을 지나친다.
→ [[a-check-that-cannot-flip-is-not-measuring-anything]]

## 고치는 법

**책임 바이너리에 권한을 준다** (시스템 설정 → 개인정보 보호 및 보안 → 전체 디스크 접근 권한).
TCC 는 launchd 잡의 **맨 위 프로세스**에 책임을 귀속시킨다 — `uv run python -m x` 로 띄우면
책임은 파이썬이 아니라 **`uv`** 다. `AUTHREQ_SUBJECT` 줄이 그 경로를 정확히 알려준다.

⚠️ **런처를 바꾸는 건 해법이 아니다.** `uv run` 을 빼도 그다음 서명 없는 바이너리(venv 의
CPython 등)가 새 책임자가 되어 **똑같이 프롬프트가 뜬다.** 잡마다 책임자가 다를 수 있으니
**전수로 세라.**

## 관련

[[a-timeout-names-the-waiter-not-the-cause-read-the-other-end]] — 이 사건도 백엔드의 300초
타임아웃으로 보고됐지만, 원인은 기다린 쪽이 아니라 **커널에 멈춰 선 자식**에 있었다.
