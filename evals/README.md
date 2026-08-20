# PatchPilot Harness Eval

Harness 자체를 검증하는 영역이다. 제품 코드를 고치는 것이 목적이 아니라,
**Orchestrator의 재시도 상태 전이가 실제로 일어나는지**를 결정론적으로 확인하는 것이 목적이다.

운영 실행(`/patchpilot`)에서는 버그가 한 번에 고쳐지면 재시도 경로가 한 번도 실행되지 않는다.
그래서 재시도 경로는 "언젠가 실패했을 때" 우연히 검증되는 상태로 남는다.
Eval은 결함을 의도적으로 주입해 그 경로를 **매번 같은 방식으로** 지나가게 만든다.

---

## 1. 검증 대상 전이

시나리오는 세 개다. `--scenario` 를 생략하면 `harness-eval-001` 이 실행된다.

### `harness-eval-001` — PRODUCT_CODE_DEFECT 재시도 루프

```text
Planner
  -> Developer 1차
  -> Fault Injection          (계획 범위 안)
  -> Tester FAIL
  -> PRODUCT_CODE_DEFECT
  -> retry_count = 1
  -> Developer 2차
  -> Tester PASS
  -> Reviewer APPROVED
  -> SUCCESS
```

### `harness-eval-002` — PLAN_DEFECT 재계획 라우팅

```text
Planner 1차
  -> Developer 1차
  -> Fault Injection          (계획 범위 밖)
  -> Tester FAIL
  -> PLAN_DEFECT
  -> retry_count = 1
  -> Planner 2차              (plan.md 갱신)
  -> Developer 2차
  -> Tester PASS
  -> Reviewer APPROVED
  -> SUCCESS
```

### `harness-eval-003` — ENVIRONMENT_ERROR 즉시 종료 라우팅

```text
Planner
  -> Developer 1차
  -> Fault Injection          (테스트 실행에 필요한 런타임 리소스 삭제)
  -> Tester FAIL
  -> ENVIRONMENT_ERROR
  -> retry_count = 0          (재시도 예산을 소비하지 않는다)
  -> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출
  -> BLOCKED                  (blocked_reason = ENVIRONMENT_ERROR)
```

앞의 두 시나리오가 "재시도가 실제로 일어나는가" 를 본다면, 이 시나리오는 반대로
**"재시도가 실제로 일어나지 않는가"** 를 본다. (`CLAUDE.md §20`, `patchpilot.md §5`)

세 전이 모두 눈으로 확인하지 않는다. `eval_harness.py` 의 `assert` 가 `reports/<run-id>/` 산출물과
제품 코드 상태만 근거로 자동 판정한다.

---

## 2. 구성

```text
evals/
├── README.md                       # 이 문서 (실행 절차)
├── eval_harness.py                 # setup / inject / assert / finish / teardown / promote / selftest
├── fixtures/
│   ├── HARNESS-EVAL-001.md         # eval 전용 고정 Task (PRODUCT_CODE_DEFECT)
│   ├── tip.py                      # 결함이 있는 제품 코드 (설치 대상)
│   ├── test_tip.py                 # 위 결함을 잡는 테스트 (설치 대상)
│   ├── HARNESS-EVAL-002.md         # eval 전용 고정 Task (PLAN_DEFECT)
│   ├── service_charge.py           # 결함이 있는 대상 모듈 (설치 대상)
│   ├── charge_rounding.py          # 정상 동작하는 협력 모듈 (설치 대상)
│   ├── test_service_charge.py      # 대상 모듈 계약 테스트 (설치 대상)
│   ├── test_charge_rounding.py     # 협력 모듈 계약 테스트 (설치 대상)
│   ├── HARNESS-EVAL-003.md         # eval 전용 고정 Task (ENVIRONMENT_ERROR)
│   ├── conftest_settlement_runtime.py  # 런타임 리소스를 읽는 테스트 부트스트랩 (설치 대상)
│   └── settlement_runtime.json     # 삭제 대상이 되는 런타임 리소스 (설치 대상)
└── faults/
    ├── retry_001.py                # 재시도 루프 검증용 결함 정의 (계획 범위 안)
    ├── plan_defect_001.py          # 재계획 라우팅 검증용 결함 정의 (계획 범위 밖)
    └── env_error_001.py            # 즉시 종료 라우팅 검증용 결함 정의 (리소스 삭제)
```

시나리오별 설치 대상은 다음과 같다. eval 실행 중에만 설치되고 teardown에서 제거된다.
`sample-project/` 에는 평소에 존재하지 않는다.

`harness-eval-001`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/tip.py` | `sample-project/src/expense/tip.py` |
| `fixtures/test_tip.py` | `sample-project/tests/test_tip.py` |

`harness-eval-002`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/charge_rounding.py` | `sample-project/src/expense/charge_rounding.py` |
| `fixtures/service_charge.py` | `sample-project/src/expense/service_charge.py` |
| `fixtures/test_charge_rounding.py` | `sample-project/tests/test_charge_rounding.py` |
| `fixtures/test_service_charge.py` | `sample-project/tests/test_service_charge.py` |

`harness-eval-003`

| fixture | 설치 경로 |
| --- | --- |
| `fixtures/tip.py` | `sample-project/src/expense/tip.py` |
| `fixtures/test_tip.py` | `sample-project/tests/test_tip.py` |
| `fixtures/conftest_settlement_runtime.py` | `sample-project/tests/conftest.py` |
| `fixtures/settlement_runtime.json` | `sample-project/config/settlement_runtime.json` |

`harness-eval-003` 은 제품 버그와 그 테스트를 `harness-eval-001` 과 공유한다. 이 시나리오가
바꾸는 변수는 제품 버그가 아니라 결함의 종류 하나이기 때문이다. 시나리오는 동시에 실행되지
않고 `setup` 은 설치 대상이 이미 존재하면 거부하므로, 설치 경로를 공유해도 서로 간섭하지 않는다.

`sample-project/config/` 처럼 setup이 새로 만든 디렉터리는 상태 파일의 `created_dirs` 에
기록되고 teardown에서 비어 있을 때 함께 제거된다. 빈 디렉터리는 `git status` 에 나타나지
않으므로 상태 비교만으로는 복구 여부를 확인할 수 없기 때문이다.

`evals/.eval-run/state.json` 은 실행 중 상태(시나리오, 설치 목록, 원상태 스냅샷, 주입 기록)를
담는 임시 파일이며 Git에 커밋하지 않는다.

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

### 3-5. PLAN_DEFECT는 Planner의 실수를 기다려서 만들지 않는다

`harness-eval-002` 의 핵심은 **plan 1차의 좁은 범위가 실수가 아니라 정답** 이라는 데 있다.

Planner 1차 시점에 `charge_rounding.py` 는 정상 동작한다. 결함은 `service_charge.py` 에만
있으므로, `CLAUDE.md §17`(최소 변경)과 `planner.md §3-4`(범위를 가능한 한 좁힌다)에 따르면
수정 허용 파일 목록은 `service_charge.py` 하나로 수렴한다. 어떤 성실한 Planner가 와도 같다.

그 뒤 Harness가 **허용 목록 밖** 인 `charge_rounding.py` 에 결함을 주입한다. 이 순간
plan.md의 원인 분석이 현재 코드 기준으로 사실이 아니게 된다. `harness-eval-001` 이 제품 코드를
사후적으로 깨뜨리는 것과 같은 방식으로, 여기서는 **계획이 사후적으로 불완전해진다.**

`faults/plan_defect_001.py` 는 주입 전에 `precheck` 로 plan 1차의 허용 목록을 읽고,
주입 대상이 이미 목록 안에 있으면 **주입하지 않고 실패시킨다.** 전제가 깨진 채로 eval이
조용히 통과하는 일을 막기 위해서다.

### 3-6. Developer만으로는 고칠 수 없다는 것이 구조로 보장된다

`tests/test_charge_rounding.py` 는 협력 모듈의 `round_to_unit` 을 **직접** 호출해 검증한다.
따라서 `service_charge.py` 안에서 무엇을 해도 이 테스트는 통과시킬 수 없다.

Developer는 `CLAUDE.md §3-2` 에 따라 허용 목록 밖 파일을 수정할 수 없으므로, 같은 plan.md로
Developer를 다시 부르면 change-log에 "범위 밖 수정 필요" 만 남기고 중단한다.
이것이 `CLAUDE.md §14` 의 `PLAN_DEFECT` 정의 — 같은 계획으로는 요구사항을 만족할 수 없어
Planner를 다시 불러야 하는 상태 — 와 정확히 일치한다.

### 3-7. Planner 재호출 증거는 Harness가 스냅샷으로 남긴다

Planner는 운영과 동일하게 `plan.md` **하나만** 쓴다. 운영 `/patchpilot` 의 규칙은 바뀌지 않는다.

재호출을 증명하기 위해 Harness가 두 시점의 `plan.md` 를 복사해 둔다.

| 산출물 | 복사 시점 |
| --- | --- |
| `plan-1.md` | `inject` 실행 시 (Developer 1차 종료 후, Planner 2차 호출 전) |
| `plan-2.md` | `assert` / `finish` 실행 시 |

`assert` 는 두 파일의 해시, 수정 허용 파일 목록, 예상 원인 본문이 실제로 달라졌는지 판정한다.

`harness-eval-003` 은 같은 스냅샷을 반대 방향으로 쓴다. 결함 주입 시점의 `plan-1.md` 와
종료 시점의 `plan.md` 해시가 **같다는 것** 이 Planner가 다시 호출되지 않았다는 증거가 된다.

### 3-8. ENVIRONMENT_ERROR 도 실제 실행 결과로만 만든다

`test-result-N.md` 의 `STATUS:` 나 실패 원인 분류 문자열을 Harness가 대신 써 넣지 않는다는
원칙은 세 시나리오 모두 같다. `harness-eval-003` 에서 Tester가 실제로 겪는 것은 다음이다.

```text
ImportError while loading conftest 'sample-project/tests/conftest.py'.
E   RuntimeError: 정산 런타임 설정 리소스를 찾을 수 없습니다: sample-project/config/settlement_runtime.json
```

pytest는 종료 코드 4로 끝나고 테스트는 한 건도 수집되지 않는다. "코드가 틀렸다" 가 아니라
"실행 환경이 준비되지 않아 실행 자체가 불가능하다" 는 상태가 실행 결과로 드러난다.
(`tester.md §3` 의 `ENVIRONMENT_ERROR` 기준)

### 3-9. 실행 환경 오류는 제품 코드를 깨뜨려서 만들지 않는다

`env_error_001` 은 제품 코드를 한 글자도 고치지 않는다. 제품 코드를 깨뜨리면
`PRODUCT_CODE_DEFECT` 로 분류하는 것이 **옳은 판정** 이 되어 검증하려는 경로를 지나가지 못한다.

대신 테스트 실행에 필요한 런타임 리소스(`sample-project/config/settlement_runtime.json`)를
지운다. 이 리소스는 제품 코드가 아니라 실행 환경이 배치하는 파일이고, 없으면 수집 단계에서
실행이 중단되므로 원인이 제품 코드 바깥에 있다는 것이 실행 결과만으로 드러난다.

### 3-10. 삭제는 이번 eval이 설치한 untracked 리소스로만 제한한다

파일 삭제는 되돌릴 수 없으므로 결함 정의와 Harness가 같은 조건을 **각각** 검사한다.
하나라도 어긋나면 지우지 않고 즉시 실패한다.

| 조건 | 확인 주체 |
| --- | --- |
| `sample-project/` 안의 상대 경로 (절대 경로·상위 경로 참조 거부) | `eval_harness.py` |
| 심볼릭 링크가 아님 | `eval_harness.py` |
| Git 추적 파일이 아님 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 이번 eval의 `setup` 이 설치한 파일임 | `eval_harness.py` / `env_error_001.precheck_fs` |
| 파일 내용에 `patchpilot-eval:env_error_001` 표식이 있음 | `env_error_001.precheck_fs` |

실제 삭제는 결함 정의가 아니라 `eval_harness.py` 한 곳에서만 수행한다. 파일을 지우는 코드가
여러 곳에 흩어지면 안전 조건을 한곳에서 보장할 수 없기 때문이다.

### 3-11. 즉시 종료 전이는 "일어나지 않은 일" 로 판정한다

`harness-eval-001` / `harness-eval-002` 는 재시도가 일어났다는 증거(2차 산출물)를 찾는다.
`harness-eval-003` 은 반대로 다음이 **하나도 없어야** 통과한다.

* `change-log-2.md` (Developer 2차)
* `test-result-2.md` (Tester 2차)
* `review.md` (Reviewer)
* `plan.md` 의 변경 (Planner 2차)
* `state.json` 의 `retry_count > 0`, `attempts` 2건, `review.verdict` 값

산출물이 없다는 사실만으로는 "Agent가 호출되지 않았다" 와 "호출됐지만 파일을 쓰지 않았다" 를
구분할 수 없다. 그래서 `state.json` 의 `retry_count` / `attempts` / `review` 기록을 함께 본다.
Orchestrator는 어떤 경로로 끝나든 `state.json` 과 `report.md` 를 남겨야 하므로
(`patchpilot.md §10`), 이 세 값이 비어 있다는 것은 라우팅이 실제로 즉시 종료됐다는 뜻이다.

---

## 4. 실행 절차 — `harness-eval-001` (PRODUCT_CODE_DEFECT)

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
`--scenario` 를 생략하면 `harness-eval-001` 이 실행된다.

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

Agent 실행 없이 harness 자체의 회귀만 확인하려면 `selftest` 를 쓴다. (§9)

```bash
uv run python evals/eval_harness.py selftest
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

## 5. 실행 절차 — `harness-eval-002` (PLAN_DEFECT)

§4와 다른 부분만 적는다. 나머지는 동일하다.

### 5-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-002
```

모듈 2개와 테스트 2개를 설치한다. 이 시점의 `charge_rounding.py` 는 **정상** 이다.

### 5-2. Planner 1차

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-002.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-002` 가 된다.

`plan.md` 의 수정 허용 파일 목록은 `sample-project/src/expense/service_charge.py` 하나여야 한다.
이 시점에는 그것이 **옳은 계획** 이다. (§3-5)

### 5-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 5-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

이때 두 가지가 함께 일어난다.

1. `reports/<run-id>/plan-1.md` 에 Planner 1차 산출물이 복사된다.
2. `plan-1.md` 의 수정 허용 파일 목록을 `precheck` 로 검사한 뒤, 목록 **밖** 인
   `charge_rounding.py` 에 결함을 주입한다.

### 5-5. Tester 1차

`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `PLAN_DEFECT` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester가 실제로 보게 되는 것은 다음이다.

* `tests/test_charge_rounding.py` 4건 실패 — 협력 모듈을 직접 호출하는 계약 테스트
* `tests/test_service_charge.py` 2건 실패 — 정산 단위 올림이 관여하는 경우만
* 나머지 통과 — Developer 1차가 고친 나머지 배분 동작은 정상이다

즉 "Developer의 수정은 계획대로 동작하는데, 계획이 범위에 넣지 않은 파일 때문에 요구사항을
만족할 수 없다" 는 상태가 실제 실행 결과로 드러난다.

### 5-6. FAIL 라우팅

`PLAN_DEFECT` 이므로 `retry_count` 를 1 증가시키고 `current_stage` 를 `PLANNING` 으로 되돌린 뒤
**Planner** 를 다시 호출한다. (`CLAUDE.md §20`, `patchpilot.md §5`)

### 5-7. Planner 2차

`planner` 를 재계획 사유와 함께 호출한다. 필수 입력은 다음이다.

* 기존 `reports/<run-id>/plan.md`
* `reports/<run-id>/test-result-1.md`
* 현재 코드

갱신된 `plan.md` 는 수정 허용 파일 목록에 `charge_rounding.py` 를 추가하고, 이전 계획의 어느
판단이 부족했는지를 명시해야 한다. (`planner.md §3`)

### 5-8. Developer 2차 이후

시도 번호 `N = 2` 로 Developer → Tester → Reviewer 를 §4-7 ~ §4-10과 동일하게 진행한다.
Developer 2차가 주입된 결함을 제거해야 한다.

### 5-9. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 판정 직전에 현재 `plan.md` 를 `plan-2.md` 로 복사한 뒤 1차와 비교한다.

---

## 6. 실행 절차 — `harness-eval-003` (ENVIRONMENT_ERROR)

§4와 다른 부분만 적는다. 나머지는 동일하다.

### 6-1. setup

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-003
```

제품 모듈과 테스트(001과 동일), 테스트 부트스트랩 `conftest.py`, 런타임 리소스
`config/settlement_runtime.json` 네 개를 설치한다. 이 시점에는 리소스가 **정상적으로 존재** 하며
`test_tip.py` 만 제품 버그로 실패한다.

### 6-2. Planner

Task 경로는 다음을 사용한다.

```text
evals/fixtures/HARNESS-EVAL-003.md
```

run-id 형식은 `RUN-YYYYMMDD-HHMM-HARNESS-EVAL-003` 이 된다.

### 6-3. Developer 1차

`developer` 를 시도 번호 `N = 1` 로 호출한다. 산출물은 `change-log-1.md` 다.

### 6-4. Fault Injection

Developer 1차가 끝나고 **Tester를 호출하기 전에** 한 번만 실행한다.

```bash
uv run python evals/eval_harness.py inject --run-id <run-id>
```

이때 두 가지가 함께 일어난다.

1. `reports/<run-id>/plan-1.md` 에 Planner 1차 산출물이 복사된다.
   (Planner가 다시 호출되지 않았음을 나중에 해시로 판정하기 위한 기준이다)
2. §3-10의 조건을 모두 통과한 경우에만 런타임 리소스를 삭제한다.

### 6-5. Tester 1차

`test-result-1.md` 는 `STATUS: FAIL`, 실패 원인 분류는 `ENVIRONMENT_ERROR` 가 되어야 한다.

Tester에게 결함 주입 사실을 알리지 않는다. Tester가 실제로 보게 되는 것은 conftest 로딩 실패로
테스트가 한 건도 수집되지 않는 pytest 출력뿐이다. (§3-8)

### 6-6. FAIL 라우팅 — 여기서 끝난다

`ENVIRONMENT_ERROR` 는 코드 결함이 아니므로 **`retry_count` 를 증가시키지 않고** 즉시
`BLOCKED` 로 종료한다. (`CLAUDE.md §20`, `patchpilot.md §5`)

Developer도 Planner도 Reviewer도 다시 호출하지 않는다. Orchestrator는 `report.md` 와
`state.json` 만 마감한다. `blocked_reason` 은 `ENVIRONMENT_ERROR` 다.

### 6-7. 자동 검증 + teardown

```bash
uv run python evals/eval_harness.py finish --run-id <run-id>
```

`finish` 는 검증 결과와 무관하게 teardown을 수행한다. 삭제된 런타임 리소스는 복구하지 않는다.
teardown이 나머지 fixture와 함께 정리하고, setup이 만든 `sample-project/config/` 디렉터리도
비어 있으면 제거한다.

---

## 7. 자동 검증 항목

`assert` / `finish` 가 판정하는 항목이다. 하나라도 실패하면 eval은 FAIL이다.

### 7-1. 재시도 후 성공하는 시나리오 공통 (`harness-eval-001` 기준 25항목 + teardown 2항목 = 27항목)

| 구분 | 항목 |
| --- | --- |
| 산출물 | `plan.md`, `change-log-1.md`, `change-log-2.md`, `report.md` 존재 |
| 결함 주입 | `fault-injection.md` 존재, 주입이 Developer 1차 이후에 이루어짐 |
| Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| Tester 1차 | 주입된 결함의 실패 테스트 기록 (001 `test_tip` / 002 `test_charge_rounding`) |
| 라우팅 | 실패 원인 분류가 시나리오의 기대 분류와 일치 (001 `PRODUCT_CODE_DEFECT` / 002 `PLAN_DEFECT`) |
| Developer 2차 | `change-log-2.md` 가 `test-result-1.md` 를 근거로 참조 |
| Tester 2차 | 첫 줄이 `STATUS: PASS`, 고정 실행 명령 기록 |
| Reviewer | 첫 줄이 `VERDICT: APPROVED` |
| 상태 | `state.json` 의 `retry_count == 1` |
| 상태 | `state.json` 의 `final_status == SUCCESS`, `current_stage == DONE`, `blocked_reason` 없음 |
| 상태 | `attempts` 2건, `[0]` 이 FAIL/기대 분류, `[1]` 이 PASS |
| 결함 제거 | 결함 표식이 사라지고 대상 파일 해시가 실제로 변경됨 |
| 테스트 무결성 | fixture 테스트 함수가 하나도 사라지지 않고 `skip` 이 추가되지 않음 |
| 범위 | eval 실행이 기존 추적 파일을 변경하지 않음 |
| 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |

### 7-2. `harness-eval-002` 추가 항목 (10항목, 총 35 + teardown 2 = 37항목)

| 구분 | 항목 |
| --- | --- |
| Planner 1차 | `plan-1.md` 스냅샷 존재 |
| 주입 전제 | 주입 대상이 `plan-1.md` 의 수정 허용 파일 목록 **밖** |
| 주입 전제 | `plan-1.md` 의 수정 허용 파일 목록이 `service_charge.py` 하나로 한정됨 |
| Planner 2차 | `plan-2.md` 스냅샷 존재 |
| Planner 2차 | `plan-1.md` 와 `plan-2.md` 의 내용(sha256)이 실제로 다름 |
| Planner 2차 | `plan-2.md` 가 1차 허용 목록을 유지하면서 주입 대상 파일을 추가 |
| Planner 2차 | `plan-2.md` 가 `test-result-1.md` 를 재계획 근거로 참조 |
| Planner 2차 | `plan-1.md` 와 `plan-2.md` 의 "예상 원인" 본문이 다름 |
| Developer 2차 | `change-log-2.md` 의 변경 파일에 주입 대상 파일이 포함됨 |
| 범위 준수 | Developer가 바꾼 파일이 모두 `plan-2.md` 의 수정 허용 목록 안에 있음 |

`plan-1.md` / `plan-2.md` 는 `promote` 시 대표 결과에도 함께 복사된다.

### 7-3. `harness-eval-003` 항목 (26항목 + teardown 2 = 28항목)

즉시 종료 시나리오는 §7-1의 "재시도 성공" 항목들(Developer 2차 / Tester 2차 / Reviewer /
`final_status == SUCCESS`)을 쓰지 않는다. 판정 항목 전체는 다음과 같다.

| # | 구분 | 항목 |
| --- | --- | --- |
| 1 | 산출물 | `plan.md` 존재 |
| 2 | 산출물 | `plan-1.md` 스냅샷 존재 |
| 3 | 산출물 | `change-log-1.md` 존재 |
| 4 | 결함 주입 | `fault-injection.md` 존재 |
| 5 | 결함 주입 | 주입이 Developer 1차 이후에 이루어짐 |
| 6 | Tester 1차 | 첫 줄이 `STATUS: FAIL` |
| 7 | Tester 1차 | 고정 실행 명령 `uv run pytest sample-project/tests -q` 기록 |
| 8 | Tester 1차 | 주입된 실행 환경 오류 증상(`settlement_runtime.json`) 기록 |
| 9 | 라우팅 | 실패 원인 분류가 `ENVIRONMENT_ERROR` |
| 10 | 미호출 | Planner 2차가 호출되지 않음 (`plan.md` 해시가 `plan-1.md` 와 동일) |
| 11 | 미호출 | Developer 2차가 호출되지 않음 (`change-log-2.md` 없음) |
| 12 | 미호출 | Tester 2차가 호출되지 않음 (`test-result-2.md` 없음) |
| 13 | 미호출 | Reviewer가 호출되지 않음 (`review.md` 없음) |
| 14 | 상태 | `state.json` 존재 |
| 15 | 상태 | `retry_count == 0` (재시도 예산 미소비) |
| 16 | 상태 | `final_status == BLOCKED` |
| 17 | 상태 | `current_stage == DONE` |
| 18 | 상태 | `blocked_reason == ENVIRONMENT_ERROR` |
| 19 | 상태 | `attempts` 1건 |
| 20 | 상태 | `attempts[0]` 이 FAIL / `ENVIRONMENT_ERROR` |
| 21 | 상태 | `review.verdict` 없음 |
| 22 | 무결성 | 삭제된 런타임 리소스가 복구되지 않음 |
| 23 | 무결성 | eval 테스트가 약화되지 않음 |
| 24 | 범위 | 기존 추적 파일이 변경되지 않음 |
| 25 | 산출물 | `report.md` 존재 |
| 26 | 산출물 | `report.md` 에 BLOCKED 종료와 사유가 기록됨 |
| 27 | 복구 | eval fixture 제거 (teardown) |
| 28 | 복구 | teardown 후 `sample-project/` 상태가 setup 시점 스냅샷과 동일 |

`plan-1.md` 는 `promote` 시 대표 결과에도 함께 복사된다. 이 시나리오의 승격 필수 목록에는
`change-log-2.md` / `test-result-2.md` / `review.md` 가 들어가지 않는다. 존재하지 않는 것이
정상이기 때문이다.

---

## 8. 실패했을 때

`reports/<run-id>/eval-result.md` 의 표에서 `FAIL` 인 행의 "근거" 열을 먼저 본다.

| 증상 | 확인할 곳 |
| --- | --- |
| `test-result-1.md` 가 `STATUS: PASS` | 결함 주입이 Developer 1차 이후에 실행됐는지 (`fault-injection.md` 시각) |
| 실패 원인 분류가 기대 분류와 다름 | `test-result-1.md` 의 pytest 원본 출력과 Tester 판단 근거 |
| `retry_count != 1` | Orchestrator가 `CLAUDE.md §20` 라우팅을 따랐는지 |
| 결함이 제거되지 않음 | `change-log-2.md` 의 수정 가설과 주입 대상 파일의 실제 내용 |
| `plan 1차와 2차의 내용이 실제로 다름` 이 FAIL | Planner 2차가 호출됐는지, `plan.md` 를 덮어썼는지 |
| `plan 1차 수정 허용 파일 목록이 계획대로 한정됨` 이 FAIL | Planner 1차가 범위를 넓게 잡았는지 (`plan-1.md` §7) |
| 복구 실패 | `git status --porcelain -- sample-project` 를 직접 확인 |
| `실패 원인 분류가 ENVIRONMENT_ERROR` 가 FAIL | Tester가 실행 환경 오류를 제품 코드 결함으로 봤는지 (`tester.md §3`) |
| `Developer 2차가 호출되지 않음` 이 FAIL | Orchestrator가 `ENVIRONMENT_ERROR` 를 재시도 경로로 라우팅했는지 (`patchpilot.md §5`) |
| `삭제된 런타임 리소스가 복구되지 않음` 이 FAIL | Agent가 실행 환경을 임의로 되살렸는지 |

`inject` 가 `주입 전제 조건 위반` 으로 실패하는 경우는 두 가지다. 어느 쪽이든 결함을 주입하지
않고 중단하므로 제품 코드는 그대로 남는다.

* `ANCHOR` 를 찾지 못함 → Developer 1차가 대상 함수를 모듈 최상위에 유지하지 않았다.
* `precheck` 거부 → Planner 1차가 주입 대상을 이미 수정 허용 파일 목록에 넣었다.
  `harness-eval-002` 의 전제(계획 범위 밖 결함)가 성립하지 않는다는 뜻이다.
* `precheck_fs` 거부 또는 Harness 삭제 조건 위반 → 삭제 대상이 §3-10의 조건을 만족하지 않는다.
  파일을 지우지 않고 중단하므로 `sample-project/` 는 그대로 남는다.

---

## 9. selftest — harness 자체의 회귀 확인

시나리오가 늘어나면 `eval_harness.py` 의 판정 코드가 공유된다. 이때 가장 큰 위험은
**기존 `harness-eval-001` 의 판정이 조용히 달라지는 것** 이다.

```bash
uv run python evals/eval_harness.py selftest
```

Agent를 실행하지 않고 수 초 안에 다음을 확인한다.

| 항목 | 근거 |
| --- | --- |
| `harness-eval-001` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_001_CHECK_NAMES` (25항목) |
| `harness-eval-002` 검증 항목 이름과 순서가 골든 목록과 일치 | `GOLDEN_002_CHECK_NAMES` (35항목) |
| 보존된 대표 결과가 현재 판정 코드에서도 전부 PASS | `reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/` |
| 모든 시나리오의 task / fault / fixture 파일 존재 | `SCENARIOS` 정의 |
| 시나리오별 설치 경로가 서로 겹치지 않음 | `SCENARIOS` 정의 |
| `replan_checks` 시나리오의 결함이 `precheck` 를 갖고 계획 범위 밖을 대상으로 함 | 결함 정의 |
| 즉시 종료 시나리오의 삭제 대상이 설치 목록 안이고 `precheck_fs` 를 갖춤 | 결함 정의 |
| 즉시 종료 시나리오의 기대 종료 상태가 라우팅 규칙과 일치 | `SCENARIOS` 정의 |
| plan / change-log 파서가 목록 항목만 인식 | 보존된 대표 결과의 실제 산출물 |

결함 제거 여부, 테스트 약화 여부, git 상태는 실행 환경에 의존하므로 replay 대상이 아니다.
항목 이름과 순서만 유지하고 판정은 건너뛴다. 이 세 항목은 라이브 실행으로만 검증된다.

아직 대표 결과가 없는 시나리오(`harness-eval-003`)는 replay 대상이 아니다. 정의가 실제 파일 및
운영 라우팅 규칙과 맞물려 있는지만 확인한다. 대표 결과를 승격한 뒤 `REGRESSION_EXAMPLES` 에
골든 목록과 함께 추가한다.

승격된 대표 결과에 시나리오가 요구하는 산출물이 빠져 있으면 판정 replay는 성립하지 않는다.
이때는 조용히 넘어가지 않고 `판정 replay 범위` 항목에 무엇이 없어서 어디까지만 대조했는지를
남긴다. 현재 `harness-eval-002` 의 대표 결과가 여기에 해당한다. (`plan-1.md` / `plan-2.md` 누락)

---

## 10. 새로운 결함 추가

`evals/faults/<fault_id>.py` 에 다음을 정의하면 `--fault <fault_id>` 로 선택할 수 있다.
결함 유형은 두 가지다. `FAULT_KIND` 를 생략하면 제품 코드 주입(`code_injection`)으로 본다.

### 10-1. `code_injection` — 제품 코드에 결함을 덧붙인다

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `FAULT_ID` | O | 결함 식별자 |
| `TARGET_PATH` | O | 주입 대상 파일 경로 (저장소 루트 기준) |
| `MARKER` | O | 주입/제거 여부를 문자열 비교로 판정하기 위한 표식 |
| `ANCHOR` | O | 주입 전제 조건이 되는 문자열 |
| `DESCRIPTION` | O | 결함 내용 한 줄 설명 |
| `FAULT_CODE` | O | 주입되는 코드 |
| `is_applied(source)` | O | 이미 주입되어 있는지 판정 |
| `apply(source)` | O | 주입된 새 내용을 반환. 전제 조건 위반 시 `ValueError` |
| `precheck(plan_allowed_files)` | | 있으면 주입 전에 호출된다. `plan.md` 의 수정 허용 파일 목록을 받아 계획 범위에 대한 전제를 검사하고, 위반 시 `ValueError` 를 낸다 |

`retry_001` 처럼 `precheck` 가 없으면 호출되지 않으므로 기존 결함 정의는 그대로 동작한다.

### 10-2. `resource_removal` — 설치된 런타임 리소스를 삭제한다

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `FAULT_KIND` | O | `"resource_removal"` |
| `FAULT_ID` | O | 결함 식별자 |
| `TARGET_PATH` | O | 삭제 대상 경로. `sample-project/` 안이어야 하고 `installs` 에 있어야 한다 |
| `MARKER` | O | 삭제 대상이 이번 eval의 fixture 사본인지 내용으로 확인하기 위한 표식 |
| `DESCRIPTION` | O | 결함 내용 한 줄 설명 |
| `SYMPTOM` | | 주입 이후 Tester가 보게 되는 증상. `fault-injection.md` 에 기록된다 |
| `precheck_fs(context)` | O | 삭제 전제 조건 검사. 위반 시 `ValueError` |
| `is_applied(context)` | | 이미 삭제되었는지 판정 |

`context` 는 `target` / `installed` / `tracked` / `exists` / `content` 를 담은 dict다.
실제 삭제는 `eval_harness.py` 가 §3-10의 조건을 함께 확인한 뒤 수행한다.
결함 정의는 무엇을 지울지와 지워도 되는 조건만 선언한다.

---

## 11. 새로운 시나리오 추가

`eval_harness.py` 의 `SCENARIOS` 에 `Scenario` 항목 하나를 추가한다. 절차 코드는 고치지 않는다.

| 필드 | 설명 |
| --- | --- |
| `scenario_id` | `--scenario` 로 지정하는 식별자 |
| `task` | eval 전용 고정 Task 경로 |
| `fault` | 기본 주입 결함 |
| `installs` | (fixture 파일명, 설치 경로) 목록 |
| `expected_category` | Tester 1차가 기록해야 하는 실패 원인 분류 |
| `expected_failing_token` | `test-result-1.md` 에 남아야 하는 실패 테스트 식별 문자열 |
| `transition` | `eval-result.md` 에 기록할 검증 대상 전이 |
| `outcome` | 종료 형태 (선택, 기본값 `SUCCESS_AFTER_RETRY`). 즉시 종료는 `BLOCKED` |
| `expected_retry_count` | `state.json` 의 기대 `retry_count` (선택, 기본값 1) |
| `expected_attempts` | `state.json` 의 기대 `attempts` 개수 (선택, 기본값 2) |
| `expected_blocked_reason` | 즉시 종료 시 기대 `blocked_reason` (선택) |
| `forbidden_artifacts` | 즉시 종료 시 존재하면 안 되는 (산출물, 주체) 목록 (선택) |
| `failing_token_check_name` | 실패 증상 기록 항목의 이름 (선택) |
| `expected_plan1_allowed` | Planner 1차가 확정해야 하는 수정 허용 파일 목록 (선택) |
| `snapshot_plan` | inject 시점에 `plan-1.md` 스냅샷을 남길지 (선택) |
| `replan_checks` | Planner 재호출(재계획) 전이를 검증할지 (선택, `snapshot_plan` 전제) |
| `promoted_files` | 승격 시 필수인 산출물 (선택, 비우면 기본 목록) |
| `extra_promoted_files` | 승격 시 함께 복사할 추가 산출물 (선택) |

추가한 뒤에는 반드시 `selftest` 로 기존 시나리오의 회귀를 확인한다.
