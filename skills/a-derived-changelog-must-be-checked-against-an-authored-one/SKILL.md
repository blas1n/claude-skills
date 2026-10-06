---
name: a-derived-changelog-must-be-checked-against-an-authored-one
description: 데이터 diff 로 "무엇이 바뀌었나"를 자동 생성하면(게임 빌드·설정·스키마·가격표) 유닛 테스트는 파서만 증명하고 **귀속**(어느 이름에 붙였나)은 증명하지 못한다 — 사람이 쓴 변경 기록이 있는 구간 하나를 골라 줄 단위로 대조하라. 그리고 같은 (필드, 이전→이후)가 주인 없는 엔트리에도 나오면 그건 공통 변경이다. 트리거 - 빌드/버전 diff 로 변경 내역 생성, 내부 ID→사람이 읽는 이름 매핑, "공지 없는 변경" 감지, diff 결과를 사용자 화면에 노출, 자동 changelog.
version: 1.1.0
task_types: [coding, evaluation, data]
triggers:
  - pattern: "generate a changelog / patch notes / what-changed list from a data diff"
  - pattern: "map internal ids of changed entries to user-facing names"
  - pattern: "detect unannounced changes between two builds or versions"
  - pattern: "label or filter raw diff fields so users can read what changed"
  - pattern: "an official changelog article that gets edited after publishing"
category: trap
---

# A derived changelog must be checked against an authored one

## 사례 (HPGG #62, 2026-09-30)
히오스 빌드 두 개의 영웅 XML 을 diff → 바뀐 숫자를 **이름이 가장 잘 맞는 특성**에 붙여 "공지 없는 핫픽스"로 표시. 유닛 테스트 16개 초록, 실데이터 97650 출력도 그럴듯했다.
공식 노트가 있는 구간(97771→98304, 2.57 패치)을 돌려 **노트와 줄 단위로 대조**하자 두 가지가 드러났다:
- 가로쉬·키히라·화이트메인·이렐 특성 수치 13/13 일치 — 파서는 맞다.
- **말가니스 특성 3개 0.1→0.15** — 노트엔 없음. 실제는 고유 능력 "흡혈의 손길" 10%→15%. 그 값이 **모든 피해 효과**(기본 공격·기술·특성 전용 효과)에 복사돼 있어서, 특성 이름을 가진 엔트리 3개만 매핑되고 나머지는 버려졌다 → 특성 변경으로 둔갑.

유닛 테스트는 "이 엔트리가 이 특성에 붙는가"만 물었다. "이 변경이 정말 이 특성의 변경인가"는 **사람이 쓴 기록**만 답할 수 있었다.

## 규칙
1. **대조 구간을 먼저 찾아라.** 자동 생성하려는 변경 중 사람이 쓴 기록(패치 노트·릴리스 노트·마이그레이션 PR)이 겹치는 구간이 하나라도 있으면 그걸로 돌리고, 세 칸으로 세라: 일치 / 우리만 있음 / 노트만 있음. **"우리만 있음"이 귀속 오류의 서식지**다(진짜 무공지 변경도 여기 산다 — 하나씩 원본을 열어 구분).
2. **같은 (필드, 이전→이후)가 주인 없는 엔트리에도 나오면 공통 변경이다.** 귀속된 것만 보지 말고, 버려진 변경과 같은 모양인지 대조해 그 그룹 전체를 뺀다. 코드: `shared = {(leaf, old, new) for c in changes if owner(c) is None}` 후 귀속분에서 제외.
3. **대조군을 테스트에 박아라.** "그 값이 원본 diff 에는 있다"(`MalGanisWeaponDamage 0.1→0.15 in changes`)를 먼저 단언하고 나서 "화면 결과엔 없다"를 단언 — 안 그러면 파서가 아예 못 읽어도 초록.
4. 노트가 **반올림**할 수 있다(0.075 → "8%"). 불일치 중 정밀도 차이는 오류가 아니다.

## 같이 나온 함정 (같은 작업)
- **같은 파일 이름 두 빌드 → 이름 키 dict 가 하나로 합쳐진다.** old/new 를 한 번에 받아 `{name: text}` 로 돌려주면 new 가 old 를 덮어 diff 0. 키는 **내용 해시**(ckey)로. 가짜 CDN 을 세운 통합 테스트가 잡았다 — 파일 단위 유닛 테스트는 못 잡는다.
- **"현재" 표시를 전역 하나로 두면 두 번째 항목 종류가 섞이는 순간 무너진다.** 노트만 있을 땐 "통계에 포함된 최신 노트 하나"가 맞았지만, 한 영웅의 핫픽스가 다른 모든 영웅 노트의 표시를 가져갔다. 표시는 **보는 주체(영웅) 기준**으로.

## 사례 2 — 대조가 "틀렸다"고 말할 때도 원본을 열어라 (HPGG #138, 2026-10-06)
10/5 잘아타스 핫픽스(블리자드가 쓴 문장)를 98304→98348 diff 와 대조했다. **대조표만 보고 내린 판정 두 개가 틀렸다**:
- **"오귀속"으로 보인 것이 정답이었다.** 노트는 "공허 폭발 피해 −20%/−5%", diff 는 `XalatathOrbitalEruptionFinalDamageTier1..4` (400→320 … 700→665)를 특성 "전령의 소모"에 붙였다. 내부 코드명(OrbitalEruption = 공허 폭발)과 특성 id 가 우연히 같아 보여 "이름 접두어 오매칭"이라 결론 낼 뻔했다. 원본 XML 에서 그 효과를 **누가 부르는지** 추적하니 `CaseArray Validator="XalatathHasXalatathOrbitalEruptionTalent"` — 특성이 있을 때만 쓰이는 효과였다. 귀속은 맞았고 고칠 것이 없었다.
- **"전부 소음"으로 보인 것 안에 진짜가 있었다.** 고정 핵의 Modifications 10개가 대부분 `Catalog=Actor`(범위 표시 장판 크기)라 통째로 버리려 했다. 필드별로 보니 일부는 `Catalog=Effect, Field=…Radius, Type=MultiplyLevelModification` 1.5→1.25 — 노트의 "범위 보너스 50%→25%" 그 자체였다.

**규칙 5.** "우리만 있음 / 노트와 다름"으로 분류된 줄은 **이름이 아니라 참조로** 판정하라: 그 엔트리를 누가 부르는가(validator·CaseArray·Abil 링크)를 원본에서 한 번 따라가라. 이름 유사성으로 귀속을 의심하는 것도, 이름으로 귀속하는 것과 똑같이 추측이다.
**규칙 6.** 소음 필터는 **엔트리(묶음) 단위가 아니라 필드 단위**로. 한 묶음 안에 시각 효과와 실제 수치가 섞여 있다(`Catalog=Actor` 9개 + `Catalog=Effect` 1개).

## 사람이 읽게 만들기 (같은 작업)
- **숫자에 이름을 붙이는 근거는 필드다.** 리프 이름(`Amount`, `Range`, `Duration`, `FlightTime`, `UnifiedMoveSpeedFactor`)·특성 수정의 형제 `Field`·`Type`(Multiply → ×배율)·context(`Subtract` + `Cooldown` → "재사용 대기시간 **감소**", 대기시간 자체가 아님)로만 이름을 붙이고, 모르는 필드는 **이름 없이** 둔다 — 추측한 단어는 노트와 어긋나는 순간 신뢰를 잃는다. 단위 변환(0.7 → 70%)을 하고 노트 문장과 숫자가 그대로 맞는지 대조("공격력 증가량 70%→100%" = "피해 배율 70% → 100%").
- **소음의 모양**: 시각 액터(`CActor*`), 좌표(`@X/@Y/@Z`, Offset·Vertex 배열), 내부 틱(`Period`). 98348 한 빌드에서 27줄 → 13줄.
- 같은 old→new 가 이름 붙은 줄과 이름 없는 줄로 두 번 나오면(비용과 그 툴팁 사본) 이름 붙은 쪽 하나만.

## 사람이 쓴 기록도 움직인다
- **공식 글은 사후에 덧붙여진다.** 블리자드는 핫픽스를 새 글이 아니라 기존 패치 노트 맨 위에 "Hotfix - 10/5/2026" 섹션으로 붙이고, 뉴스 API 의 `lastUpdated` 는 **안 바뀐다.** "한 번 받은 글은 다시 안 받는다" 캐시는 이 섹션을 영원히 놓친다 → 최근 N일 글은 매번 다시 읽고, 처음 받은 날짜·빌드는 유지.
- **덧붙인 섹션은 본문과 마크업이 다르다**(붙여넣기: `span style=font-weight:700`, `(Q)` 키). 본문 파서를 재사용하지 말고 실제 HTML 을 픽스처로 저장해 따로 파싱.
- **번역은 늦게 온다.** 한국어 글엔 그 섹션이 아직 없다. 빈 칸을 영어로 채우기만 하면 한국어 페이지가 영어가 된다 — 대안은 diff 수치를 페이지 언어로 보여주고 원문을 접어 두는 것(번역이 오면 자동 교체).
