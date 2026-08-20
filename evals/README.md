# PatchPilot Harness Eval

Harness 자체를 검증하는 영역이다. 제품 코드를 고치는 것이 목적이 아니라,
**Orchestrator의 재시도 상태 전이가 실제로 일어나는지**를 결정론적으로 확인하는 것이 목적이다.

운영 실행(`/patchpilot`)에서는 버그가 한 번에 고쳐지면 재시도 경로가 한 번도 실행되지 않는다.
그래서 재시도 경로는 "언젠가 실패했을 때" 우연히 검증되는 상태로 남는다.
Eval은 결함을 의도적으로 주입해 그 경로를 **매번 같은 방식으로** 지나가게 만든다.

---

## 1. 검증 대상 전이

```text
Planner
  -> Developer 1차
  -> Fault Injection
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 1
  -> Developer 2차
  -> Tester PASS
  -> Reviewer APPROVED
  -> SUCCESS
```

이 전이는 눈으로 확인하지 않는다. `eval_harness.py` 의 `assert` 가 `reports/<run-id>/` 산출물과
제품 코드 상태만 근거로 자동 판정한다.

---

## 2. 구성

```text
evals/
├── README.md                     # 이 문서 (실행 절차)
├── eval_harness.py               # setup / inject / assert / finish / teardown / promote
├── fixtures/
│   ├── HARNESS-EVAL-001.md       # eval 전용 고정 Task
│   ├── tip.py                    # 결함이 있는 제품 코드 (설치 대상)
│   └── test_tip.py               # 위 결함을 잡는 테스트 (설치 대상)
└── faults/
    └── retry_001.py              # 재시도 루프 검증용 결함 정의
```

`fixtures/tip.py` 와 `fixtures/test_tip.py` 는 eval 실행 중에만 다음 위치에 설치되고
teardown에서 제거된다. `sample-project/` 에는 평소에 존재하지 않는다.

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/tip.py` | `sample-project/src/expense/tip.py` |
| `fixtures/test_tip.py` | `sample-project/tests/test_tip.py` |

`evals/.eval-run/state.json` 은 실행 중 상태(설치 목록, 원상태 스냅샷, 주입 기록)를 담는
임시 파일이며 Git에 커밋하지 않는다.

---

## 3. 설계 결정

### 3-1. 결함 제거는 Harness가 아니라 Developer 2차가 한다

`eval_harness.py` 는 결함을 **주입만** 하고 되돌리지 않는다.
Harness가 스스로 되돌리면 재수정 주체가 Developer가 아니게 되어
`FAIL -> 분석 -> 재수정 -> PASS` 전이의 검증 의미가 사라지기 때문이다.

Developer 2차는 `test-result-1.md` 를 읽고 실제 제품 코드 결함을 진단해 제거해야 한다.
제거 여부는 `assert` 가 결함 표식(`patchpilot-eval:retry_001`)의 부재와 파일 해시 변경으로 판정한다.

### 3-2. FAIL은 문자열 조작이 아니라 실제 테스트 실패로 만든다

`test-result-N.md` 의 `STATUS:` 를 임의로 `FAIL` 로 바꾸지 않는다.
Tester는 언제나 고정 명령 `uv run pytest sample-project/tests -q` 를 실제로 실행하고 그 결과를 기록한다.
`assert` 는 `test-result-1.md` 에 고정 실행 명령과 실패 테스트 이름이 남아 있는지도 함께 확인한다.

### 3-3. 운영 Harness는 건드리지 않는다

이 eval은 `.claude/agents/*.md` 와 `.claude/commands/patchpilot.md` 를 수정하지 않는다.
Agent는 자신이 eval 중이라는 사실을 모른 채 평소와 동일한 규칙으로 동작한다.
결함 주입 시점만 Orchestrator가 절차상 한 번 끼워 넣는다.

### 3-4. 결함 주입은 구현 세부사항에 의존하지 않는다

`faults/retry_001.py` 는 `tip.py` 끝에 후처리 래퍼를 덧붙인다.
Developer 1차가 함수 본문을 어떻게 고쳤든 모듈 최상위에 `def split_tip(` 정의만 있으면
동일하게 적용되므로 주입 결과가 결정론적이다. 전제 조건이 깨지면 주입하지 않고 실패한다.

---

## 4. 실행 절차

Orchestrator(메인 Claude Code 세션)가 아래 순서를 그대로 수행한다.
Agent 호출 규칙, `state.json` 필드, FAIL 라우팅, 재시도 예산은
`.claude/commands/patchpilot.md` 와 `CLAUDE.md §14 / §16 / §19 / §20` 을 그대로 따른다.

### 4-0. 사전 조건

`git status --porcelain -- sample-project` 가 깨끗한 상태에서 시작하는 것을 권장한다.
(더러워도 실행은 되지만, 복구 판정은 setup 시점 스냅샷과의 비교로 이루어진다.)

### 4-1. setup

```bash
uv run python evals/eval_harness.py setup
```

fixture를 설치하고 `sample-project/` 원상태를 스냅샷한다.

### 4-2. Planner

`.claude/commands/patchpilot.md §1~§2` 절차대로 run-id를 만들고 `reports/<run-id>/` 를 생성한 뒤
`planner` 를 호출한다. Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-001.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-001` 이 된다.

`reports/<run-id>/plan.md` 확인 후 진행한다.

### 4-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 4-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

`reports/<run-id>/fault-injection.md` 가 생성된다.

### 4-5. Tester 1차

`tester` 를 시도 번호 `N = 1` 로 호출한다.
`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `PRODUCT_CODE_DEFECT` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester는 평소처럼 실행 결과만 보고 판정한다.

### 4-6. FAIL 라우팅

`PRODUCT_CODE_DEFECT` 이므로 `retry_count` 를 1 증가시키고 Developer를 다시 호출한다.
(`CLAUDE.md §20`)

### 4-7. Developer 2차

`developer` 를 시도 번호 `N = 2` 로 호출한다.
프롬프트에 `test-result-1.md` 와 `change-log-1.md` 를 필수 입력으로 전달한다.
Developer 2차가 주입된 결함을 제거해야 한다.

### 4-8. Tester 2차

`tester` 를 시도 번호 `N = 2` 로 호출한다. `test-result-2.md` 가 `STATUS: PASS` 여야 한다.

### 4-9. Reviewer

`reviewer` 를 호출한다. `review.md` 가 `VERDICT: APPROVED` 여야 한다.

### 4-10. 보고서와 상태 마감

`report.md` 와 `state.json` 을 작성한다. 최종 상태는 `SUCCESS` 다.

### 4-11. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 검증이 실패하거나 검증 중 예외가 나더라도 `finally` 에서 teardown을 수행한다.
따라서 eval이 실패해도 `sample-project/` 는 정리된다.

* 종료 코드 `0` → eval PASS
* 종료 코드 `1` → eval FAIL (판정 근거는 `reports/<run-id>/eval-result.md`)

검증만 하고 teardown을 미루려면 `assert` 를, 정리만 하려면 `teardown` 을 쓴다.

```bash
uv run python evals/eval_harness.py assert --run-id <run-id>
uv run python evals/eval_harness.py teardown
uv run python evals/eval_harness.py status
```

### 4-12. 대표 결과 승격 (선택)

일반 실행 결과인 `reports/<run-id>/` 는 `.gitignore` 로 커밋되지 않는다.
검증에 통과한 대표 실행 하나만 골라 커밋 대상으로 복사한다.

```bash
uv run python evals/eval_harness.py promote --run-id <run-id>
```

`reports/examples/EVAL-<YYYYMMDD-HHMM>-HARNESS-EVAL-001/` 에 다음 파일이 복사된다.
`eval-result.md` 의 첫 줄이 `EVAL: PASS` 가 아니면 승격을 거부한다.

```text
fault-injection.md
change-log-1.md
test-result-1.md
change-log-2.md
test-result-2.md
review.md
report.md
state.json
plan.md          (있으면 함께 복사)
eval-result.md   (있으면 함께 복사)
```

폴더 이름을 직접 지정하려면 `--name EVAL-RETRY-001` 처럼 넘긴다.

---

## 5. 자동 검증 항목

`assert` / `finish` 가 판정하는 항목이다. 하나라도 실패하면 eval은 FAIL이다.

| 구분 | 항목 |
| --- | --- |
| 산출물 | `plan.md`, `change-log-1.md`, `change-log-2.md`, `report.md` 존재 |
| 결함 주입 | `fault-injection.md` 존재, 주입이 Developer 1차 이후에 이루어짐 |
| Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| Tester 1차 | 주입된 결함의 실패 테스트(`test_tip`) 기록 |
| 라우팅 | 실패 원인 분류가 `PRODUCT_CODE_DEFECT` |
| Developer 2차 | `change-log-2.md` 가 `test-result-1.md` 를 근거로 참조 |
| Tester 2차 | 첫 줄이 `STATUS: PASS`, 고정 실행 명령 기록 |
| Reviewer | 첫 줄이 `VERDICT: APPROVED` |
| 상태 | `state.json` 의 `retry_count == 1` |
| 상태 | `state.json` 의 `final_status == SUCCESS`, `current_stage == DONE`, `blocked_reason` 없음 |
| 상태 | `attempts` 2건, `[0]` 이 FAIL/`PRODUCT_CODE_DEFECT`, `[1]` 이 PASS |
| 결함 제거 | 결함 표식이 사라지고 대상 파일 해시가 실제로 변경됨 |
| 테스트 무결성 | fixture 테스트 함수가 하나도 사라지지 않고 `skip` 이 추가되지 않음 |
| 범위 | eval 실행이 기존 추적 파일을 변경하지 않음 |
| 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |

---

## 6. 실패했을 때

`reports/<run-id>/eval-result.md` 의 표에서 `FAIL` 인 행의 "근거" 열을 먼저 본다.

| 증상 | 확인할 곳 |
| --- | --- |
| `test-result-1.md` 가 `STATUS: PASS` | 결함 주입이 Developer 1차 이후에 실행됐는지 (`fault-injection.md` 시각) |
| 실패 원인 분류가 `PRODUCT_CODE_DEFECT` 가 아님 | `test-result-1.md` 의 pytest 원본 출력과 Tester 판단 근거 |
| `retry_count != 1` | Orchestrator가 `CLAUDE.md §20` 라우팅을 따랐는지 |
| 결함이 제거되지 않음 | `change-log-2.md` 의 수정 가설과 실제 `tip.py` 내용 |
| 복구 실패 | `git status --porcelain -- sample-project` 를 직접 확인 |

`inject` 가 `주입 전제 조건 위반` 으로 실패하면 Developer 1차가 `split_tip` 을 모듈 최상위 함수로
유지하지 않았다는 뜻이다. 이 경우 결함을 주입하지 않고 중단하므로 제품 코드는 그대로 남는다.

---

## 7. 새로운 결함 추가

`evals/faults/<fault_id>.py` 에 다음을 정의하면 `--fault <fault_id>` 로 선택할 수 있다.

| 이름 | 설명 |
| --- | --- |
| `FAULT_ID` | 결함 식별자 |
| `TARGET_PATH` | 주입 대상 파일 경로 (저장소 루트 기준) |
| `MARKER` | 주입/제거 여부를 문자열 비교로 판정하기 위한 표식 |
| `ANCHOR` | 주입 전제 조건이 되는 문자열 |
| `DESCRIPTION` | 결함 내용 한 줄 설명 |
| `FAULT_CODE` | 주입되는 코드 |
| `is_applied(source)` | 이미 주입되어 있는지 판정 |
| `apply(source)` | 주입된 새 내용을 반환. 전제 조건 위반 시 `ValueError` |
