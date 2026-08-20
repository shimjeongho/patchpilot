# 🔧 PatchPilot

> **AI Coding Agent가 버그 수정 작업을 통제된 절차로 수행하도록 만드는 Harness Engineering 프로젝트**

PatchPilot은 Claude Code 위에 **Harness**를 설계한 프로젝트입니다. 버그 요구사항 하나를 입력하면 역할이 분리된 Agent들이 **계획 → 수정 → 테스트 → 실패 분석 → 재수정 → 리뷰 → 결과 보고** 과정을 정해진 상태 머신에 따라 수행합니다.

이 저장소의 결과물은 "Claude Code로 개발한 애플리케이션"이 아니라 **"Claude Code Agent가 안정적으로 개발 작업을 수행하도록 만든 통제 구조"** 그 자체입니다. Agent가 무엇을 할 수 있고, 무엇을 판정할 권한이 있으며, 실패했을 때 어디로 가는지를 규칙·도구 권한·파일 소유권으로 정의했습니다.

---

## 📌 왜 만들었는가

일반적인 AI Coding Agent 사용은 다음과 같습니다.

```text
사용자 요청  →  AI  →  코드 수정
```

이 구조에는 세 가지 문제가 있습니다.

- 수정이 **실제로 동작하는지** 확인하는 주체가 없습니다. AI의 "수정했습니다"라는 문장이 곧 결과가 됩니다.
- 실패했을 때 **무엇 때문에 실패했는지** 분류되지 않아, 다음 시도가 이전과 같은 실수를 반복합니다.
- 어디까지 고쳐야 하는지 경계가 없어 **요구사항과 무관한 변경**이 섞여 들어갑니다.

PatchPilot은 같은 작업을 다음 절차로 바꿉니다.

```text
요구사항
   → Planner    원인 분석 · 수정 범위 확정
   → Developer  계획 범위 안에서만 코드 수정
   → Tester     실제 pytest 실행 · PASS/FAIL 판정 · 실패 원인 분류
   → 실패 분석  분류에 따라 다음 행선지 결정
   → Developer  이전과 다른 근거로 재수정 (재시도 예산 소비)
   → Reviewer   실제 git diff 기반 최종 검토
   → 최종 결과  SUCCESS 또는 BLOCKED
```

핵심 차이는 **판정 권한의 분리**입니다. 코드를 고친 Agent가 스스로 성공을 선언할 수 없습니다. 테스트 통과 여부는 Tester만, 품질 승인은 Reviewer만, 최종 상태는 Orchestrator만 결정합니다. Orchestrator는 Agent의 설명 문장이 아니라 **산출물 파일의 첫 줄**(`STATUS:`, `VERDICT:`)만 보고 다음 단계를 정합니다.

---

## 🏗 Harness Architecture

```mermaid
flowchart TD
    TASK["Bug Task<br/>tasks/BUG-XXX.md"] --> PLAN

    PLAN["Planner"]
    DEV["Developer"]
    TEST["Tester<br/>uv run pytest sample-project/tests -q"]
    REV["Reviewer<br/>실제 git diff 검토"]

    PLAN --> DEV --> TEST --> STATUS

    subgraph ORC ["Orchestrator — 상태 전이 · 재시도 예산 · 최종 판정"]
        direction TB
        STATUS{"test-result-N.md 첫 줄"}
        BUDGET{"재시도 예산 남음?"}
        VERDICT{"review.md 첫 줄"}
    end

    STATUS -->|"STATUS: FAIL<br/>PRODUCT_CODE_DEFECT"| BUDGET
    STATUS -->|"STATUS: FAIL<br/>TEST_DEFECT · ENVIRONMENT_ERROR"| BLOCKED
    STATUS -->|"STATUS: PASS"| REV

    BUDGET -->|"예 → retry_count += 1"| DEV
    BUDGET -->|아니오| BLOCKED

    REV --> VERDICT
    VERDICT -->|"VERDICT: CHANGES_REQUESTED"| BUDGET
    VERDICT -->|"VERDICT: APPROVED"| SUCCESS

    SUCCESS(["SUCCESS"])
    BLOCKED(["BLOCKED"])

    PLAN -.->|plan.md| REPORTS
    DEV -.->|change-log-N.md| REPORTS
    TEST -.->|test-result-N.md| REPORTS
    REV -.->|review.md| REPORTS
    SUCCESS -.->|"report.md · state.json"| REPORTS
    BLOCKED -.->|"report.md · state.json"| REPORTS

    REPORTS[("reports/&lt;run-id&gt;/")]
```

### 실패 원인별 라우팅

Tester가 `STATUS: FAIL`을 반환하면 **실패 원인 분류**에 따라 행선지가 달라집니다.

| 실패 원인 분류 | 처리 | 재시도 예산 |
| --- | --- | --- |
| `PRODUCT_CODE_DEFECT` | Developer 재호출. 이전 `test-result`·`change-log`를 읽고 다른 근거로 수정 | 1회 소비 |
| `PLAN_DEFECT` | Planner 재호출하여 `plan.md` 갱신 후 Developer 루프 복귀 | 1회 소비 |
| `TEST_DEFECT` | 테스트를 자동 수정하지 않고 `BLOCKED`. 사람의 판단 필요 | 소비 없음 |
| `ENVIRONMENT_ERROR` | 코드 결함으로 취급하지 않고 즉시 `BLOCKED` | 소비 없음 |
| `UNKNOWN` | 1회만 추가 시도. 재발 시 `BLOCKED` | 1회 소비 |

재시도 예산은 **실행 전체에서 하나로 공유**하며 상한은 3회입니다. Reviewer의 `CHANGES_REQUESTED`로 인한 재수정도 같은 예산에서 차감됩니다. 예산을 초과하면 성공한 것처럼 처리하지 않고 `BLOCKED`로 종료합니다.

`SUCCESS`는 **최종 `test-result-N.md`가 `STATUS: PASS`이고 `review.md`가 `VERDICT: APPROVED`인 경우에만** 부여됩니다. 부분 성공을 `SUCCESS`로 올리지 않습니다.

---

## 🤖 Agent 역할

| Agent | 책임 | 산출물 |
| --- | --- | --- |
| **Planner** | 요구사항과 실제 코드를 읽고 원인 분석, 수정 허용 파일 목록·구현 단계·검증 방법·위험 요소 확정 | `plan.md` |
| **Developer** | `plan.md`의 허용 범위 안에서만 제품 코드 수정. 재시도 시 이전 실패 결과를 읽고 다른 가설 제시 | `change-log-N.md` |
| **Tester** | 고정 명령으로 전체 테스트 실행, PASS/FAIL 판정, 실패 원인 5종 분류, 필요 시 회귀 테스트 추가 | `test-result-N.md` |
| **Reviewer** | 실제 `git diff` 기준 최종 검토. 요구사항 충족·범위 이탈·테스트 무력화·회귀 위험 확인 | `review.md` |
| **Orchestrator** | Agent 호출 순서, 상태 전이, 재시도 예산, 최종 상태 결정 | `report.md`, `state.json` |

Orchestrator는 메인 Claude Code 세션이 `/patchpilot` 커스텀 커맨드로 수행합니다.

---

## 🔒 Agent 권한 분리

역할 분리를 프롬프트 문구로만 선언하지 않고 **도구 권한**과 **파일 소유권**으로 함께 제한했습니다.

| Agent | 허용 도구 | 도구 수준에서 불가능한 것 |
| --- | --- | --- |
| Planner | `Read` `Grep` `Glob` `Write` | Bash 없음 → 테스트 실행·git 조작 불가 / Edit 없음 → 기존 코드 편집 불가 |
| Developer | `Read` `Grep` `Glob` `Edit` `Write` | Bash 없음 → **테스트를 실행하거나 통과 여부를 스스로 판정할 수 없음** |
| Tester | `Read` `Grep` `Glob` `Bash` `Write` | Edit 없음 → 기존 제품 코드 편집 불가 |
| Reviewer | `Read` `Grep` `Glob` `Bash` `Write` | Edit 없음 → 코드 편집 불가 |

여기에 각 Agent 정의와 `CLAUDE.md`가 규칙 수준의 금지 사항을 추가합니다.

- **Developer는 `sample-project/tests/` 하위를 수정할 수 없습니다.** assertion 조정·예상값 변경·skip 추가도 포함됩니다. 테스트를 약화시켜 통과시키는 경로를 차단하는 것이 목적입니다.
- **Tester는 제품 코드를 수정할 수 없습니다.** 테스트를 실행하고 판정할 권한만 가집니다.
- **Planner와 Reviewer는 제품 코드를 수정할 수 없습니다.** 계획과 검토만 담당합니다.
- **Orchestrator는 제품 코드와 테스트 파일을 모두 수정하지 않습니다.** 직접 쓰는 파일은 `report.md`와 `state.json` 둘뿐입니다.

> 현재 이 금지 사항 중 일부는 도구 권한으로 완전히 차단되고(예: Developer의 테스트 실행), 일부는 Agent 규칙으로 강제됩니다(예: Tester의 제품 코드 미수정). `PreToolUse` Hook을 통한 경로 단위 쓰기 차단은 아직 구현하지 않았으며 Future Work입니다.

---

## 📄 파일 기반 Agent 통신

PatchPilot의 Agent들은 **숨겨진 대화 컨텍스트를 통신 수단으로 사용하지 않습니다.** 다음 Agent에게 전달해야 할 내용은 반드시 파일로 남깁니다.

```text
reports/<run-id>/
├── plan.md            Planner    → Developer
├── change-log-1.md    Developer  → Tester
├── test-result-1.md   Tester     → Orchestrator → Developer (재시도 근거)
├── change-log-2.md    Developer  → Tester
├── test-result-2.md   Tester     → Orchestrator
├── review.md          Reviewer   → Orchestrator
├── report.md          Orchestrator (최종 보고)
└── state.json         Orchestrator (상태 전이 기록)
```

이렇게 설계한 이유는 세 가지입니다.

1. **재현성** — 같은 입력 파일이 주어지면 같은 판단 근거가 주어집니다. 대화 히스토리에 의존하면 실행마다 Agent가 받는 정보가 달라집니다.
2. **추적 가능성** — 왜 재시도가 발생했고 무엇이 바뀌었는지 실행이 끝난 뒤에도 파일만으로 재구성할 수 있습니다.
3. **기계 판정** — Orchestrator는 `test-result-N.md`의 첫 줄 `STATUS: PASS` / `STATUS: FAIL`, `review.md`의 첫 줄 `VERDICT: APPROVED` / `VERDICT: CHANGES_REQUESTED`를 **문자열 그대로 비교**해 다음 단계를 정합니다. Agent의 설명 문장을 해석해 성공 여부를 재판단하지 않습니다.

`state.json`은 단계 전환마다 갱신되며 `current_stage`, `retry_count`, `attempts`, `final_status`, `blocked_reason`을 실제 상태와 일치시킵니다.

---

## 🧪 테스트 및 실행 환경

테스트 명령은 하나로 고정되어 있습니다.

```bash
uv run pytest sample-project/tests -q
```

명령을 고정한 이유는 Agent가 일부 테스트만 실행하고 통과를 선언하는 것을 막기 위해서입니다. Tester는 이 명령 외의 방식으로 테스트를 실행할 수 없습니다.

Python 환경은 **uv**로 관리합니다.

- **가상환경 재현** — `uv run`이 잠금 파일 기준으로 환경을 자동 동기화하므로, 사용자가 `.venv`를 수동 활성화하는 것을 전제하지 않습니다.
- **의존성 관리** — `pyproject.toml`로 선언하고 `uv add`로 추가합니다. `requirements.txt` 방식은 사용하지 않습니다.
- **버전 고정** — `uv.lock`으로 pytest를 포함한 의존성 버전을 고정해 실행마다 같은 환경을 재현합니다.

`uv` 실행 자체가 실패하거나 환경 동기화가 불가능한 경우는 제품 코드 결함이 아니라 `ENVIRONMENT_ERROR`로 분류되어, 재시도 예산을 소비하지 않고 즉시 `BLOCKED`로 종료됩니다.

### 실행 방법

```bash
# 버그 태스크 하나를 Harness로 처리
/patchpilot tasks/BUG-001.md

# 전체 테스트
uv run pytest sample-project/tests -q
```

---

## 📊 실행 결과 — BUG-001 ~ BUG-004

`sample-project/`는 정산 금액 분배를 다루는 작은 Python 패키지입니다. 실제 Harness 실행으로 검증한 버그 태스크는 다음과 같습니다.

| Task | 목적 | 최종 상태 | Developer 시도 | retry_count |
| --- | --- | --- | --- | --- |
| BUG-001 | 기본 성공 루프 · 나머지 금액 유실 | SUCCESS | 1 | 0 |
| BUG-002 | 가중치 기반 분배 | SUCCESS | 1 | 0 |
| BUG-003 | 동전 단위 정산 · 다중 결함 | SUCCESS | 1 | 0 |
| BUG-004 | 정산 대조 · 이체 잔액 | SUCCESS | 1 | 0 |

네 건 모두 `STATUS: PASS` + `VERDICT: APPROVED`로 `SUCCESS` 판정을 받았습니다.

**그런데 여기서 문제가 드러났습니다.** 네 건 모두 `retry_count = 0`입니다. 즉 **재시도 상태 머신이 한 번도 실행되지 않았습니다.** 설계한 FAIL 라우팅, 재시도 예산, 재수정 루프는 코드로만 존재할 뿐 실제로 지나간 적이 없는 경로였습니다.

---

## 🔁 핵심 시행착오 및 개선

### 초기 접근

> "Agent가 첫 시도에 실패할 정도로 어려운 버그를 만들면 재시도 루프를 검증할 수 있을 것이다."

BUG-002, BUG-003, BUG-004로 갈수록 의도적으로 난이도를 올렸습니다. 다중 결함, 다단계 계산, 모듈 간 의존이 얽힌 버그를 설계했습니다.

### 문제

전부 첫 시도에 통과했습니다. 원인은 **Planner의 정적 분석이 예상보다 강력했다는 점**입니다. Planner가 실제 코드를 읽고 원인을 정확히 특정한 뒤 수정 범위까지 좁혀주면, Developer는 그 계획을 따르기만 하면 되므로 실패할 이유가 없었습니다.

여기서 더 근본적인 문제를 인식했습니다. **"Agent가 실패하기를 기다리는 방식"은 검증 전략이 될 수 없습니다.**

- 결과가 Agent의 추론 성능에 좌우되어 **비결정적**입니다. 같은 태스크가 어떤 날은 실패하고 어떤 날은 통과합니다.
- 모델이 좋아질수록 재시도 경로는 **더 검증하기 어려워집니다.** 검증하려는 대상(Harness)이 아니라 검증 도구(Agent)의 성능에 결과가 종속됩니다.
- 재시도 경로에 버그가 있어도 **아무도 모릅니다.** 실행되지 않는 코드이기 때문입니다.

### 개선

Agent의 실수를 기다리는 대신, **Fault Injection 기반 Harness Integration Eval**을 설계했습니다.

Developer가 정상적으로 수정을 끝낸 직후 제품 코드에 결함을 **의도적으로 주입**하여, Tester가 실제로 실패하도록 만듭니다. 이렇게 하면 Agent의 추론 성능과 무관하게 `FAIL → 분류 → 재시도 → PASS` 경로를 **매번 같은 방식으로** 지나가게 됩니다.

검증 대상이 "Agent가 버그를 잘 고치는가"에서 **"Harness의 상태 머신이 설계대로 동작하는가"**로 바뀐 것이 이 프로젝트에서 가장 중요한 방향 전환이었습니다.

---

## 💉 Fault Injection Eval

### 실행 흐름

```text
Planner
  → Developer 1차          (정상 수정 완료)
  → Fault Injection        (제품 코드에 결함 주입)
  → Tester 1차 FAIL        (실제 pytest 실패)
  → PRODUCT_CODE_DEFECT
  → retry_count = 1
  → Developer 2차          (주입된 결함을 직접 진단·제거)
  → Tester 2차 PASS
  → Reviewer APPROVED
  → SUCCESS
```

### 실제 실행 결과

Run: **`RUN-20260820-1318-HARNESS-EVAL-001`**

| 항목 | 결과 |
| --- | --- |
| Tester 1차 | `STATUS: FAIL` — **8 failed, 62 passed** |
| 실패 원인 분류 | `PRODUCT_CODE_DEFECT` |
| retry_count | **1** / 3 |
| Developer 실행 횟수 | 2 |
| Tester 2차 | `STATUS: PASS` — **70 passed** |
| Reviewer | `VERDICT: APPROVED` |
| Eval 자동 검증 | **27 / 27 PASS** |
| teardown 후 기존 테스트 | **57 passed** (실행 전과 동일) |
| 재현성 | 동일 Eval **2회 실행**, 같은 상태 전이 재현 |

대표 실행 결과는 [`reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/`](reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/)에 보존되어 있습니다.

### 결함 주입 방식

이 Eval에서 가장 중요한 원칙은 **`test-result-N.md`의 `STATUS:` 문자열을 임의로 `FAIL`로 바꾸지 않는다**는 것입니다. 그렇게 하면 검증되는 것은 문자열 처리 로직뿐이고, 실제 테스트 실행 경로는 여전히 검증되지 않습니다.

대신 실제 제품 코드에 결함을 주입합니다. `evals/faults/retry_001.py`는 대상 모듈 끝에 후처리 래퍼를 덧붙여 반환값의 마지막 원소를 0으로 만듭니다.

```python
# 마지막 사람은 팁 정산 대상에서 제외한다는 요구로 추가된 후처리. (ref: patchpilot-eval:retry_001)
_split_tip_before_last_person_rule = split_tip


def split_tip(bill: int, people: int, tip_percent: int) -> list[int]:
    shares = _split_tip_before_last_person_rule(bill, people, tip_percent)
    return shares[:-1] + [0]
```

- **실제 pytest가 실패합니다.** Tester는 평소와 동일하게 `uv run pytest sample-project/tests -q`를 실행하고 그 결과를 기록합니다. 결함이 주입되었다는 사실은 어느 Agent에게도 알리지 않습니다.
- **주입이 결정론적입니다.** Developer 1차가 함수 본문을 어떻게 구현했든 모듈 최상위에 `def split_tip(` 정의만 있으면 동일하게 적용됩니다. 전제 조건이 깨지면 주입하지 않고 실패합니다.
- **결함을 제거하는 주체는 Harness가 아니라 Developer 2차입니다.** Harness가 스스로 되돌리면 재수정 주체가 Developer가 아니게 되어 `FAIL → 분석 → 재수정 → PASS` 전이의 검증 의미가 사라집니다. 제거 여부는 결함 표식의 부재와 파일 해시 변경으로 자동 판정합니다.

실제 2회 실행에서 Developer 2차는 `test-result-1.md`만 보고 스스로 원인을 특정했습니다. 두 번 모두 **`split_tip(10000, 1, 10)`이 `[11000]` 대신 `[0]`을 반환한다는 점**을 근거로 들었습니다. 인원이 1명이면 나머지 배분 계산으로는 몫이 0이 될 수 없으므로 결함이 계산부 밖에 있다는 추론입니다.

---

## 🧬 Eval Architecture

```text
evals/
├── README.md                     실행 절차 · 설계 결정 · 자동 검증 항목
├── eval_harness.py               setup / inject / assert / finish / teardown / promote
├── fixtures/
│   ├── HARNESS-EVAL-001.md       Eval 전용 고정 Task
│   ├── tip.py                    결함이 있는 제품 코드 (실행 중에만 설치)
│   └── test_tip.py               위 결함을 잡는 테스트 13개 (실행 중에만 설치)
└── faults/
    └── retry_001.py              재시도 루프 검증용 결함 정의
```

### 운영 경로와 Eval 경로의 분리

Eval은 운영 Harness를 **전혀 수정하지 않습니다.**

- `.claude/agents/*.md` 4개와 `.claude/commands/patchpilot.md`는 Eval을 위해 한 줄도 변경되지 않았습니다. Agent는 자신이 Eval 중이라는 사실을 모른 채 평소와 동일한 규칙으로 동작합니다.
- `fixtures/tip.py`와 `fixtures/test_tip.py`는 `sample-project/`에 **평소에 존재하지 않습니다.** `setup`이 설치하고 `teardown`이 제거합니다.
- Eval 실행 절차는 별도 커맨드를 만들지 않고 `evals/README.md`의 runbook으로 두었습니다. Orchestrator는 `.claude/commands/patchpilot.md`의 상태 머신을 그대로 따르되, Developer 1차와 Tester 사이에 `inject` 한 단계만 끼워 넣습니다. 운영 경로 자체를 검증 대상으로 두기 위한 선택입니다.

### 실행 명령

```bash
uv run python evals/eval_harness.py setup
#   → Planner → Developer 1차
uv run python evals/eval_harness.py inject   --run-id <run-id>
#   → Tester 1차 FAIL → Developer 2차 → Tester 2차 PASS → Reviewer → report/state
uv run python evals/eval_harness.py finish   --run-id <run-id>   # 자동 검증 + teardown
uv run python evals/eval_harness.py promote  --run-id <run-id>   # 대표 결과 보존
```

`finish`는 `try/finally` 구조로 **자동 검증이 실패하거나 검증 중 예외가 발생해도 teardown을 반드시 수행합니다.** Eval이 실패해도 `sample-project/`는 정리됩니다. 종료 코드는 검증 결과를 따릅니다(0 = PASS, 1 = FAIL).

---

## ✅ 자동 검증

Eval의 성공 여부는 눈으로 판단하지 않습니다. `eval_harness.py`가 `reports/<run-id>/` 산출물과 제품 코드 상태만 근거로 **27개 항목**을 자동 판정하며, 하나라도 실패하면 Eval은 FAIL입니다.

| 구분 | 검증 항목 |
| --- | --- |
| 상태 전이 | `test-result-1.md` 첫 줄이 `STATUS: FAIL` |
| 상태 전이 | 실패 원인 분류가 `PRODUCT_CODE_DEFECT` |
| 상태 전이 | `change-log-2.md` 존재 — Developer 2차가 실제로 실행됨 |
| 상태 전이 | `change-log-2.md`가 `test-result-1.md`를 근거로 참조 |
| 상태 전이 | `test-result-2.md` 첫 줄이 `STATUS: PASS` |
| 상태 전이 | `review.md` 첫 줄이 `VERDICT: APPROVED` |
| 상태 기록 | `state.json`의 `retry_count == 1` |
| 상태 기록 | `attempts` 2건, `[0]`이 FAIL/`PRODUCT_CODE_DEFECT`, `[1]`이 PASS |
| 상태 기록 | `final_status == SUCCESS`, `current_stage == DONE`, `blocked_reason` 없음 |
| 무결성 | 주입된 결함이 제거됨 — 표식 부재 **및** 파일 해시 변경 |
| 무결성 | 테스트 완화 없음 — 테스트 함수가 하나도 사라지지 않고 `skip` 미추가 |
| 무결성 | Tester가 고정 명령을 실제로 기록 — 문자열만 바꾼 FAIL 차단 |
| 복구 | teardown 성공 — 설치한 fixture 전부 제거 |
| 복구 | `sample-project/`가 setup 시점 스냅샷과 **완전히 동일** |

마지막 두 항목이 있기 때문에 Eval을 몇 번 돌려도 저장소가 오염되지 않습니다. 실제로 2회 연속 실행 후 `git status`가 비어 있고 기존 테스트 57개가 그대로 통과했습니다.

---

## 📁 Repository Structure

```text
patchpilot/
├── CLAUDE.md                     Harness 공통 규칙 (Agent 권한 · 라우팅 · 컨벤션)
│
├── .claude/
│   ├── agents/                   planner · developer · tester · reviewer
│   └── commands/
│       └── patchpilot.md         Orchestrator 실행 절차
│
├── sample-project/               수정 대상 제품 코드
│   ├── src/expense/              splitter · weighted_splitter · allocation
│   │                             settlement · reconciliation · formatter
│   ├── tests/                    테스트 57개
│   └── pytest.ini
│
├── tasks/                        BUG-001 ~ BUG-004 요구사항
│
├── evals/                        Harness 자체 검증
│   ├── eval_harness.py
│   ├── fixtures/
│   └── faults/
│
├── reports/                      실행 산출물 (gitignore)
│   └── examples/                 검증 통과한 대표 실행 결과 (커밋됨)
│
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## 🛠 Tech Stack

실제로 사용한 기술만 기재합니다.

| Category | Technology |
| --- | --- |
| AI Coding Agent | Claude Code |
| Agent 구성 | Claude Code Subagents |
| Harness 규칙 | `CLAUDE.md` |
| 실행 절차 | Custom Commands (`/patchpilot`) |
| Language | Python 3.12 |
| Testing | pytest |
| 환경·의존성 관리 | uv (`pyproject.toml`, `uv.lock`) |
| Version Control | Git, GitHub |

---

## 🔮 Future Work

아직 구현하지 않은 항목입니다.

**Harness 강화**

- `PreToolUse` Hook 기반 권한 강제 — 현재 규칙으로 금지하는 경로(예: Developer의 테스트 파일 쓰기)를 도구 수준에서 차단
- Docker 기반 Sandbox 실행 환경

**Eval 확장** — 현재는 `PRODUCT_CODE_DEFECT` 경로 하나만 결정론적으로 검증됩니다.

- `PLAN_DEFECT` Eval — Planner 재계획 경로
- `TEST_DEFECT` Eval — 자동 수정 없이 `BLOCKED` 처리되는지
- `ENVIRONMENT_ERROR` Eval — 재시도 예산을 소비하지 않고 즉시 종료하는지
- Retry Budget 초과 → `BLOCKED` Eval

**측정 및 연동**

- Baseline(Claude Code 단독) vs Harness 정량 비교 — 성공률, 재시도 횟수, 범위 이탈 횟수
- 실행 Dashboard — 단계별 상태, 실행 시간, Token 사용량
- GitHub Issue 연동 및 Pull Request 자동화
- MCP 기반 외부 개발 도구 연동

---

## 💡 정리

PatchPilot에서 중요하게 다룬 것은 AI가 코드를 얼마나 많이 생성하는가가 아니라, **AI의 작업을 어떻게 통제하고 검증할 것인가**입니다.

| 주제 | 이 저장소에서의 구현 |
| --- | --- |
| **Agent 역할 분리** | 계획·구현·검증·리뷰를 4개 Agent로 분리, 판정 권한을 각각 독점 |
| **최소 권한** | Agent별 도구 권한 축소. Developer는 테스트를 실행할 수 없음 |
| **상태 머신** | `PLANNING → DEVELOPING → TESTING → REVIEWING → DONE`, 종료 상태는 `SUCCESS` / `BLOCKED` 둘뿐 |
| **명시적 Artifact** | 숨겨진 대화가 아니라 `reports/<run-id>/` 파일로만 인계 |
| **자동 테스트** | 고정 명령으로 전체 테스트 실행. 부분 실행 후 통과 선언 차단 |
| **실패 원인 분류** | 5종 분류에 따라 행선지가 달라짐. 모든 실패를 같은 방식으로 재시도하지 않음 |
| **Retry Budget** | 실행 전체에서 3회 공유. 초과 시 성공으로 위장하지 않고 `BLOCKED` |
| **Fault Injection** | Agent의 실수를 기다리지 않고 결함을 주입해 실패 경로를 강제 실행 |
| **결정론적 Eval** | 27개 항목 자동 판정. 2회 실행에서 동일한 상태 전이 재현 |
| **자동 복구 검증** | teardown 후 `sample-project/`가 실행 전과 완전히 동일한지 확인 |
| **재현 가능한 환경** | uv + `uv.lock`으로 의존성 버전 고정 |

가장 오래 고민한 부분은 **"검증되지 않은 경로를 어떻게 검증할 것인가"**였습니다. 재시도 루프를 설계해 두었지만 Agent가 실패하지 않아 한 번도 실행되지 않는 상황에서, 더 어려운 버그를 만드는 대신 결함을 주입하는 방향으로 전환한 것이 이 프로젝트의 핵심 결정이었습니다.
