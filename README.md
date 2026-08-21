# 🔧 PatchPilot

> **AI Coding Agent가 버그 수정 작업을 통제된 절차로 수행하도록 만드는 Harness Engineering 프로젝트**

PatchPilot은 Claude Code 위에 **Harness**를 설계한 프로젝트입니다. 버그 요구사항 하나를 입력하면 역할이 분리된 Agent들이 **계획 → 수정 → 테스트 → 실패 분석 → 재수정 → 리뷰 → 결과 보고** 과정을 정해진 상태 머신에 따라 수행합니다.

이 저장소의 결과물은 "Claude Code로 개발한 애플리케이션"이 아니라 **"Claude Code Agent가 안정적으로 개발 작업을 수행하도록 만든 통제 구조"** 그 자체입니다. Agent가 무엇을 할 수 있고, 무엇을 판정할 권한이 있으며, 실패했을 때 어디로 가는지를 규칙·도구 권한·파일 소유권으로 정의했습니다.

**🔗 Dashboard Live Demo — https://patchpilot-five.vercel.app**

실제 Harness 실행 결과(Fault Injection Eval 4종)의 상태 전이와 Agent 산출물을 브라우저에서 바로 확인할 수 있습니다.

[![PatchPilot Dashboard Overview](docs/images/dashboard-overview.png)](https://patchpilot-five.vercel.app)

<sub>Eval 4종의 최종 상태 · 소비한 재시도 예산 · 자동 검증 통과 수를 한 화면에서 보여줍니다. 모든 수치는 `reports/examples/` 의 `state.json` 과 `eval-result.md` 에서 빌드 타임에 읽은 값입니다. 이미지를 클릭하면 Live Demo로 이동합니다.</sub>

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

<sub>이 네 건의 운영 실행 산출물은 `reports/` gitignore 정책에 따라 저장소에 포함되지 않습니다. 저장소에 공개된 검증 증거는 `reports/examples/` 에 보존된 EVAL-001~004 대표 결과입니다.</sub>

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

### 발견 1 — 재시도 예산의 off-by-one

`RETRY_BUDGET_EXCEEDED` Eval(HARNESS-EVAL-004)을 설계하다가 **운영 상태 머신의 실제 결함**을 찾았습니다.

기존 라우팅은 이 순서였습니다.

```text
예산 확인 (retry_count < retry_budget)  →  retry_count += 1  →  다음 Agent 재호출
```

`retry_budget = 3`인데 FAIL이 세 번 나도 매번 "확인 → 증가" 순서라 **네 번째 Developer가 호출**됩니다. `CLAUDE.md`가 명시한 "Developer와 Tester의 반복은 최대 3회"와 한 번 어긋나 있었습니다. 실제 운영 실행(BUG-001~004)은 모두 재시도 0회로 끝났기 때문에 이 결함은 드러난 적이 없었습니다.

```text
retry_count += 1  →  budget 비교  →  도달 시 재호출 없이 BLOCKED
```

로 정정했습니다. `retry_count`의 의미도 "남은 재시도 횟수"가 아니라 **"예산을 소비한 실패 시도 수"**로 통일했습니다. 예산을 소비하는 네 경로(`PRODUCT_CODE_DEFECT` · `PLAN_DEFECT` · `UNKNOWN` · `CHANGES_REQUESTED`)에 동일하게 적용되며, 특정 Eval을 위한 예외 분기는 넣지 않았습니다.

**검증 도구를 만들다가 검증 대상의 버그를 찾은 사례**입니다. Eval이 없었다면 재시도가 세 번 연속 실패하는 실행이 나오기 전까지 발견되지 않았을 결함입니다.

### 발견 2 — Eval 검증 자체가 비결정적이었다

Eval은 결정론적이어야 하는데, **판정 코드가 Agent의 문장 표현에 의존**하고 있었습니다. 두 가지가 실제로 문제를 일으켰습니다.

**(1) 실패 테스트 판정이 문서 전체 substring 검색이었다.** Tester가 `## 추가한 회귀 테스트` 절에 "이미 존재하는 회귀 테스트" 목록을 적었는데, 거기 이름이 들어 있다는 이유로 **통과한 테스트가 실패로 집계**되어 Eval이 FAIL 판정됐습니다. → pytest 원문의 `FAILED <path>::<test_name>` 라인만 파싱하도록 바꿨습니다. 설명 문장에 등장하는 이름은 실패 증거로 보지 않습니다.

**(2) 근거 참조 검사가 파일 이름 문자열만 인정했다.** Developer 3차가 이전 실패의 관측값(`(9000, 3)`이 `[3001, 3000, 2999]`가 된다는 사실)을 근거로 정확히 재진단했지만, 본문에서 "2차 실패"라고만 쓰고 `test-result-2.md`라는 이름을 적지 않아 주입 게이트가 실행을 거부했습니다. 같은 시나리오가 어떤 실행에서는 통과하고 어떤 실행에서는 막히는 상태였습니다. → 두 방향으로 고쳤습니다.

- **운영 규칙:** Orchestrator의 재수정 프롬프트에 "이전 산출물을 읽고, 근거로 사용한 **파일 이름과 실제 관측값**을 change-log에 함께 남긴다"는 파일 기반 인계 요건을 명시했습니다. 모든 Developer 재시도에 적용되는 일반 규칙입니다.
- **Eval 판정:** 이전 시도 참조 표현(`test-result-2` · `2차 실패` · `이전 실패` …)과 **이전 실행에서 실제 관측된 값의 인용**(실패 테스트 이름 · pytest 집계 · assertion 리터럴)을 **함께** 요구하는 semantic evidence check로 교체했습니다. 참조 표현만 있으면 "이전 실패를 확인했다"는 형식 문구로 통과하고, 인용만 있으면 우연히 같은 값을 적은 경우와 구분되지 않기 때문입니다.

두 개선 모두 회귀 항목으로 `selftest`에 고정해, 판정 코드가 다시 느슨해지거나 표현에 취약해지면 즉시 드러나도록 했습니다.

---

## 💉 Fault Injection Eval

### 검증한 상태 전이 4종

FAIL 라우팅 5종 중 **4종의 종료 경로**를 실제 Agent 실행으로 검증했습니다. 아래 수치는 모두 `reports/examples/` 에 보존된 대표 결과에서 읽은 값입니다.

| Eval | 검증 대상 전이 | 최종 상태 | retry_count | 자동 검증 |
| --- | --- | --- | --- | --- |
| HARNESS-EVAL-001 | `PRODUCT_CODE_DEFECT` → 재시도 → 성공 | SUCCESS | 1 / 3 | **27 / 27** |
| HARNESS-EVAL-002 | `PLAN_DEFECT` → 재계획 → 성공 | SUCCESS | 1 / 3 | **37 / 37** |
| HARNESS-EVAL-003 | `ENVIRONMENT_ERROR` → 즉시 종료 | BLOCKED | 0 / 3 | **28 / 28** |
| HARNESS-EVAL-004 | 재시도 예산 소진 → 종료 | BLOCKED | 3 / 3 | **55 / 55** |

네 Eval 모두 teardown 후 `sample-project/`가 실행 전 상태로 복구되었고 기존 테스트 57개가 그대로 통과했습니다.

---

#### 1. `PRODUCT_CODE_DEFECT` — HARNESS-EVAL-001

```text
Planner → Developer 1차 → Fault Injection → Tester 1차 FAIL
  → PRODUCT_CODE_DEFECT → retry_count = 1
  → Developer 2차(주입된 결함을 직접 진단·제거) → Tester 2차 PASS
  → Reviewer APPROVED → SUCCESS
```

| 항목 | 결과 |
| --- | --- |
| Tester 1차 | `STATUS: FAIL` — **8 failed, 62 passed** / `PRODUCT_CODE_DEFECT` |
| retry_count | **1** / 3 |
| Developer 실행 횟수 | 2 |
| Tester 2차 | `STATUS: PASS` — **70 passed** |
| Reviewer | `VERDICT: APPROVED` |
| `state.json` | `final_status = SUCCESS`, `attempts` 2건 (`[0]` FAIL/`PRODUCT_CODE_DEFECT`, `[1]` PASS) |
| 자동 검증 | **27 / 27 PASS** |
| 재현성 | 동일 Eval 2회 실행, 같은 상태 전이 재현 |

대표 결과: [`reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/`](reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/)

#### 2. `PLAN_DEFECT` — HARNESS-EVAL-002

계획 범위 **밖**의 협력 모듈에 결함을 주입합니다. Developer가 계획 범위 안에서 무엇을 해도 통과시킬 수 없으므로, Planner를 다시 불러 수정 범위를 넓혀야만 해결됩니다.

```text
Planner 1차 → Developer 1차 → Fault Injection(계획 범위 밖) → Tester 1차 FAIL
  → PLAN_DEFECT → retry_count = 1
  → Planner 2차(수정 허용 범위 확대) → Developer 2차 → Tester 2차 PASS
  → Reviewer APPROVED → SUCCESS
```

| 항목 | 결과 |
| --- | --- |
| Tester 1차 | `STATUS: FAIL` — **6 failed, 76 passed** / `PLAN_DEFECT` |
| retry_count | **1** / 3 |
| plan 1차 수정 허용 파일 | `service_charge.py` 1개 — 주입 전 시점에는 이것이 옳은 계획 |
| plan 2차 수정 허용 파일 | `service_charge.py` + `charge_rounding.py` 2개 — 1차 목록 유지 + 주입 대상 추가 |
| plan 1차/2차 차이 | 파일 해시 상이, "예상 원인" 본문 상이, `test-result-1.md` 를 재계획 근거로 참조 |
| Tester 2차 | `STATUS: PASS` — **82 passed** |
| Reviewer | `VERDICT: APPROVED` |
| 자동 검증 | **37 / 37 PASS** (001 공통 항목 + 재계획 전용 10항목) |

대표 결과: [`reports/examples/EVAL-20260820-1443-HARNESS-EVAL-002/`](reports/examples/EVAL-20260820-1443-HARNESS-EVAL-002/)

#### 3. `ENVIRONMENT_ERROR` — HARNESS-EVAL-003

제품 코드는 한 글자도 건드리지 않고, 테스트 실행에 필요한 런타임 리소스를 삭제합니다. 제품 코드를 깨뜨리면 `PRODUCT_CODE_DEFECT` 로 분류하는 것이 옳은 판정이 되어 검증하려는 경로를 지나가지 못하기 때문입니다.

```text
Planner → Developer 1차 → Fault Injection(런타임 리소스 삭제) → Tester 1차 FAIL
  → ENVIRONMENT_ERROR → retry_count 미소비(0)
  → Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출
  → BLOCKED (blocked_reason = ENVIRONMENT_ERROR)
```

| 항목 | 결과 |
| --- | --- |
| Tester 1차 | `STATUS: FAIL` / `ENVIRONMENT_ERROR` |
| pytest 실행 결과 | `conftest.py` 로딩 중 `RuntimeError` → **테스트 0건 수집**, 종료 코드 4 |
| retry_count | **0** / 3 — 예산 미소비 |
| `state.json` | `final_status = BLOCKED`, `blocked_reason = ENVIRONMENT_ERROR`, `attempts` 1건, `review.verdict` 없음 |
| 미호출 증거 | `change-log-2.md` / `test-result-2.md` / `review.md` 부재 + `plan.md` 해시가 주입 시점 스냅샷과 동일 |
| 자동 검증 | **28 / 28 PASS** |
| 복구 | teardown 후 `sample-project/` 가 setup 시점 상태와 동일 |

대표 결과: [`reports/examples/EVAL-20260820-1554-HARNESS-EVAL-003/`](reports/examples/EVAL-20260820-1554-HARNESS-EVAL-003/)

**확인된 한계.** 이 실행에서 Planner는 계획을 세우면서 `tests/conftest.py` 를 읽고 "런타임 리소스가 없으면 수집 단계에서 중단되므로 `ENVIRONMENT_ERROR` 로 분류해야 한다"는 취지를 `plan.md` 위험 요소에 먼저 적었습니다. Tester는 `plan.md` 를 필수 입력으로 받으므로, 이 분류가 **완전히 blind한 조건에서 나온 것은 아닙니다.** Eval fixture와 fault를 별도 sandbox나 git worktree로 격리하는 개선이 필요합니다. (Future Work)

#### 4. 재시도 예산 소진 — HARNESS-EVAL-004

같은 결함을 반복 주입하지 않습니다. Developer가 직전 결함을 **실제로 제거했는지 확인한 뒤에만** 다음 결함을 주입하므로, "Developer가 아무것도 고치지 못하는 구조"나 "Harness가 수정을 몰래 되돌리는 구조"가 성립할 수 없습니다.

```text
Developer 1차 → 결함 B 주입 → Tester 1차 FAIL / PRODUCT_CODE_DEFECT → retry_count = 1
Developer 2차(B 제거) → 결함 C 주입 → Tester 2차 FAIL / PRODUCT_CODE_DEFECT → retry_count = 2
Developer 3차(C 제거) → 결함 D 주입 → Tester 3차 FAIL / PRODUCT_CODE_DEFECT → retry_count = 3
  → retry_count >= retry_budget
  → Developer 4차 / Tester 4차 / Reviewer 미호출
  → BLOCKED (blocked_reason = RETRY_BUDGET_EXCEEDED)
```

[![HARNESS-EVAL-004 — 재시도 예산 소진 후 BLOCKED 종료](docs/images/eval-004-blocked.png)](https://patchpilot-five.vercel.app)

<sub>EVAL-004 Timeline의 종료 구간입니다. Tester 3차 `STATUS: FAIL` 직후 Orchestrator가 `retry_count(3) >= retry_budget(3)` 로 판단해 **추가 Agent 재호출 없이** `RETRY_BUDGET_EXCEEDED` 로 종료합니다. 호출되지 않은 Planner 2차 · Developer 4차 · Tester 4차 · Reviewer는 빈칸이 아니라 **"미호출 (자동 검증됨)"** 으로 표시됩니다. Planner부터 이어지는 전체 Timeline은 [Live Demo](https://patchpilot-five.vercel.app)에서 확인할 수 있습니다.</sub>

| 항목 | 결과 |
| --- | --- |
| Planner / Developer / Tester / Reviewer 실행 | **1 / 3 / 3 / 0** |
| Tester 1차 | `STATUS: FAIL` — **1 failed, 67 passed** / `PRODUCT_CODE_DEFECT` |
| Tester 2차 | `STATUS: FAIL` — **3 failed, 65 passed** / `PRODUCT_CODE_DEFECT` |
| Tester 3차 | `STATUS: FAIL` — **6 failed, 62 passed** / `PRODUCT_CODE_DEFECT` |
| retry_count / retry_budget | **3 / 3** |
| `state.json` | `final_status = BLOCKED`, `blocked_reason = RETRY_BUDGET_EXCEEDED`, `attempts` **3건 모두** FAIL/`PRODUCT_CODE_DEFECT`, `review.verdict` 없음 |
| 미호출 증거 | `change-log-4.md` / `test-result-4.md` / `fault-injection-4.md` / `review.md` 부재 |
| 마지막 결함 | 종료 시점까지 제품 코드에 잔존 — 표식 존재 + 주입 직후 sha256과 동일 |
| 자동 검증 | **55 / 55 PASS** |
| 복구 | teardown 후 기존 테스트 **57 passed** (setup 시점 기준선과 동일) |

세 라운드의 실패 증상은 서로 달랐습니다. 매 라운드 "이전 시도의 pytest 실패 목록에 없던 테스트"가 새로 실패했는지까지 자동 판정합니다.

대표 결과: [`reports/examples/EVAL-20260820-1752-HARNESS-EVAL-004/`](reports/examples/EVAL-20260820-1752-HARNESS-EVAL-004/)

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
├── eval_harness.py               setup / inject / assert / finish / teardown / promote / selftest
├── fixtures/                     Eval 전용 고정 Task 4개 + 제품 모듈·테스트
│   ├── HARNESS-EVAL-001.md       PRODUCT_CODE_DEFECT      tip.py / test_tip.py
│   ├── HARNESS-EVAL-002.md       PLAN_DEFECT              service_charge.py / charge_rounding.py + 테스트 2개
│   ├── HARNESS-EVAL-003.md       ENVIRONMENT_ERROR        conftest + settlement_runtime.json
│   └── HARNESS-EVAL-004.md       RETRY_BUDGET_EXCEEDED    installment.py / test_installment.py
└── faults/
    ├── retry_001.py              계획 범위 안 결함 (코드 주입)
    ├── plan_defect_001.py        계획 범위 밖 결함 (코드 주입)
    ├── env_error_001.py          런타임 리소스 삭제
    └── retry_budget_001~003.py   서로 다른 요구사항을 깨는 결함 3종 (연쇄 주입)
```

fixture는 `sample-project/`에 **평소에 존재하지 않습니다.** `setup`이 설치하고 `teardown`이 제거합니다.

### 운영 경로와 Eval 경로의 분리

Eval에는 **Eval 전용 예외 분기가 없습니다.**

- `.claude/agents/*.md` 4개는 Eval을 위해 한 줄도 변경되지 않았습니다. Agent는 자신이 Eval 중이라는 사실을 모른 채 평소와 동일한 규칙으로 동작합니다.
- `.claude/commands/patchpilot.md`도 "특정 Eval을 통과시키기 위한" 수정은 하지 않았습니다. 다만 Eval이 **운영 상태 머신의 실제 결함**을 두 건 드러냈고, 그 수정은 모든 실행에 적용되는 일반 규칙으로 반영했습니다. (아래 시행착오 참조)
- Eval 실행 절차는 별도 커맨드를 만들지 않고 `evals/README.md`의 runbook으로 두었습니다. Orchestrator는 `.claude/commands/patchpilot.md`의 상태 머신을 그대로 따르되, Developer와 Tester 사이에 `inject` 단계만 끼워 넣습니다. 운영 경로 자체를 검증 대상으로 두기 위한 선택입니다.

### 실행 명령

```bash
uv run python evals/eval_harness.py setup --scenario harness-eval-004
#   → Planner → Developer 1차
uv run python evals/eval_harness.py inject --run-id <run-id> --attempt 1
#   → Tester 1차 → (재시도 시) Developer N차 → inject --attempt N → Tester N차 → report/state
uv run python evals/eval_harness.py finish   --run-id <run-id>   # 자동 검증 + teardown
uv run python evals/eval_harness.py promote  --run-id <run-id>   # 대표 결과 보존
uv run python evals/eval_harness.py selftest                     # Agent 실행 없이 판정 코드 회귀 확인
```

`--scenario` 를 생략하면 `harness-eval-001`이 실행됩니다. `--attempt` 는 결함을 여러 번 주입하는 시나리오에서 필수이며, 2차 이후 주입은 **직전 결함이 실제로 제거되었는지 확인한 뒤에만** 수행됩니다.

`finish`는 `try/finally` 구조로 **자동 검증이 실패하거나 검증 중 예외가 발생해도 teardown을 반드시 수행합니다.** Eval이 실패해도 `sample-project/`는 정리됩니다. 종료 코드는 검증 결과를 따릅니다(0 = PASS, 1 = FAIL).

---

## ✅ 자동 검증

Eval의 성공 여부는 눈으로 판단하지 않습니다. `eval_harness.py`가 `reports/<run-id>/` 산출물과 제품 코드 상태만 근거로 판정하며, **하나라도 실패하면 Eval은 FAIL**입니다. 항목 수는 시나리오마다 다릅니다 (001 = 27, 002 = 37, 003 = 28, 004 = 55).

| 구분 | 검증 항목 | 적용 |
| --- | --- | --- |
| 상태 전이 | `test-result-N.md` 첫 줄이 `STATUS: FAIL` / `PASS` | 전체 |
| 상태 전이 | 실패 원인 분류가 시나리오의 기대 분류와 일치 | 전체 |
| 상태 전이 | Tester가 고정 명령을 실제로 기록 — 문자열만 바꾼 FAIL 차단 | 전체 |
| 상태 전이 | 실패 테스트가 pytest `FAILED <path>::<name>` 라인에 실제로 존재 | 001 · 002 · 004 |
| 상태 전이 | N차 실패가 **이전 시도에 없던** 새 증상인지 | 004 |
| 상태 전이 | `review.md` 첫 줄이 `VERDICT: APPROVED` | 001 · 002 |
| 재계획 | `plan-1.md` / `plan-2.md` 해시·허용 목록·예상 원인이 실제로 달라짐 | 002 |
| 근거 인계 | `change-log-N.md`가 이전 실패를 근거로 사용 — 참조 표현 + 실제 관측값 인용 | 001 · 002 · 004 |
| 미호출 | 호출되지 않아야 할 Agent의 산출물이 **하나도 없음** | 003 · 004 |
| 상태 기록 | `retry_count`, `retry_budget`, `attempts`, `final_status`, `blocked_reason`, `review.verdict` | 전체 |
| 무결성 | 주입된 결함이 제거됨 — 표식 부재 **및** 파일 해시 변경 | 001 · 002 · 004 |
| 무결성 | 마지막 결함이 **제거되지 않고 남아 있음** (예산 소진 이후 아무도 손대지 않았다는 증거) | 004 |
| 무결성 | 테스트 완화 없음 — 테스트 함수가 하나도 사라지지 않고 `skip` 미추가 | 전체 |
| 복구 | teardown 성공 — 설치한 fixture 전부 제거 | 전체 |
| 복구 | `sample-project/`가 setup 시점 스냅샷과 **완전히 동일** | 전체 |
| 복구 | teardown 후 전체 테스트 결과가 setup 시점 기준선과 동일 | 004 |

복구 항목이 있기 때문에 Eval을 몇 번 돌려도 저장소가 오염되지 않습니다. 실제로 여러 번 연속 실행한 뒤에도 `git status`가 비어 있고 기존 테스트 57개가 그대로 통과했습니다.

### 판정 코드 자체의 회귀 확인

시나리오가 늘어나면 판정 코드가 공유되므로, **기존 시나리오의 판정이 조용히 달라지는 것**이 가장 큰 위험입니다. `selftest`는 Agent를 실행하지 않고 보존된 대표 결과 4건을 현재 판정 코드로 다시 읽어 항목 이름·순서·판정을 대조합니다.

```bash
uv run python evals/eval_harness.py selftest   # EVAL: PASS (40/40)
```

실행 환경에 의존하는 항목(결함 제거 여부, git 상태 등)은 replay 대상이 아니며, 항목 이름과 순서만 유지하고 판정은 건너뜁니다.

---

## 📊 Dashboard

`reports/examples/`에 보존된 대표 결과를 읽어 Harness의 상태 전이를 보여주는 정적 대시보드입니다. Next.js App Router의 Server Component에서 Markdown/JSON을 **빌드 타임에 직접 읽고** 정적 HTML로 내보냅니다. 서버도 DB도 API도 없습니다.

배포된 대시보드는 여기서 바로 볼 수 있습니다. **[Dashboard Live Demo](https://patchpilot-five.vercel.app)**

로컬에서 실행하려면:

```bash
cd dashboard
npm install
npm run dev      # http://localhost:3000
npm run build    # out/ 에 정적 HTML 생성
```

보여주는 것:

| 화면 | 내용 |
| --- | --- |
| Overview | Total / SUCCESS / BLOCKED / 총 Attempts / 총 Retry + Eval 목록 |
| Eval Detail | 상태 전이 Timeline · Agent 실행 여부 · Attempt별 STATUS와 retry_count 변화 · 자동 검증 항목 |
| Artifact Viewer | `plan-N.md` · `change-log-N.md` · `test-result-N.md` · `fault-injection-N.md` · `review.md` · `report.md` · `state.json` · `eval-result.md` |

Timeline이 핵심입니다. `state.json`만으로는 전이를 그릴 수 없기 때문입니다. **EVAL-002의 Planner 재호출은 `state.json` 어디에도 기록되지 않고 `plan-2.md`라는 산출물의 존재로만 드러납니다.** 그래서 `state.json` + 산출물 존재 여부 + 결함 주입 기록을 합성해 전이를 만들고, 재시도 예산 누적은 `CLAUDE.md §16`을 그대로 따라 계산한 뒤 **`state.json`의 `retry_count`와 대조합니다.** 어긋나면 표시값을 덮어쓰지 않고 화면에 경고로 드러냅니다.

호출되지 않은 Agent는 빈칸으로 두지 않습니다. EVAL-003의 Reviewer 미호출은 Harness가 멈춘 것이 아니라 `ENVIRONMENT_ERROR` 라우팅 규칙대로 부르지 않은 것이고, `eval-result.md`가 그 부재를 자동 검증 항목으로 판정해 두었습니다. 대시보드는 그 판정을 읽어 **"미호출 (자동 검증됨)"**으로 표시합니다.

`dashboard/`는 Harness 영역도 수정 대상 영역도 아닌 **읽기 전용 소비자**입니다. `reports/examples/`를 읽기만 하고, `evals/eval_harness.py`를 import하지 않으며(같은 파일 계약을 독립 구현), Python 의존성을 추가하지 않습니다. 자세한 내용은 [`dashboard/README.md`](dashboard/README.md)에 있습니다.

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
│   ├── eval_harness.py           setup / inject / assert / finish / teardown / promote / selftest
│   ├── fixtures/                 Eval 전용 Task 4종 + 제품 모듈·테스트
│   └── faults/                   결함 정의 6종
│
├── reports/                      실행 산출물 (gitignore)
│   └── examples/                 검증 통과한 대표 실행 결과 (커밋됨)
│
├── dashboard/                    Eval 결과 대시보드 (읽기 전용 소비자)
│   ├── app/                      Overview · Eval Detail · Artifact Viewer
│   ├── components/               Ui · Timeline · Markdown
│   └── lib/                      types · parse · evals · timeline
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
| Dashboard | Next.js 15 (App Router, `output: 'export'`), TypeScript, React 19 |
| Version Control | Git, GitHub |

---

## 🔮 Future Work

아직 구현하지 않은 항목입니다.

**Eval 확장** — 현재 `PRODUCT_CODE_DEFECT` · `PLAN_DEFECT` · `ENVIRONMENT_ERROR` · `RETRY_BUDGET_EXCEEDED` 네 경로가 결정론적으로 검증되어 있습니다. 남은 경로는 다음과 같습니다.

- `TEST_DEFECT` Eval — 테스트를 자동 수정하지 않고 즉시 `BLOCKED` 처리되는지
- `UNKNOWN` Eval — 1회만 추가 시도하고 두 번째 `UNKNOWN`에서 종료되는지
- Reviewer `CHANGES_REQUESTED` Eval — 테스트가 PASS인 상태에서 리뷰 지적으로 재수정 루프가 도는지

**Eval 격리** — HARNESS-EVAL-003에서 드러난 한계입니다.

- Eval fixture와 fault 정의를 별도 sandbox 또는 git worktree로 격리 — 현재는 Agent가 저장소를 탐색하다 `evals/faults/` 나 `conftest.py` 를 읽고 결함 주입 가능성을 먼저 인지할 수 있어, Tester의 분류가 완전히 blind한 조건이 아닙니다

**Harness 강화**

- `PreToolUse` Hook 기반 권한 강제 — 현재 규칙으로 금지하는 경로(예: Developer의 테스트 파일 쓰기)를 도구 수준에서 차단
- Docker 기반 Sandbox 실행 환경

**측정 및 연동**

- Baseline(Claude Code 단독) vs Harness 정량 비교 — 성공률, 재시도 횟수, 범위 이탈 횟수
- 실시간 실행 Dashboard — 실행 중 단계 상태, 실행 시간, Token 사용량. 현재 Dashboard는 실행이 끝난 뒤 보존된 대표 결과를 읽는 정적 사이트이므로 목적이 다릅니다
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
| **Retry Budget** | 실행 전체에서 3회 공유. 예산을 다 쓰면 성공으로 위장하지 않고 `BLOCKED` — 실제 실행으로 검증 |
| **Fault Injection** | Agent의 실수를 기다리지 않고 결함을 주입해 실패 경로를 강제 실행. 재주입 전 이전 결함 제거 여부를 확인 |
| **결정론적 Eval** | 4개 종료 경로를 결함 주입으로 강제 실행. 시나리오별 27~55개 항목 자동 판정 |
| **자동 복구 검증** | teardown 후 `sample-project/`가 실행 전과 완전히 동일한지 확인 |
| **재현 가능한 환경** | uv + `uv.lock`으로 의존성 버전 고정 |

가장 오래 고민한 부분은 **"검증되지 않은 경로를 어떻게 검증할 것인가"**였습니다. 재시도 루프를 설계해 두었지만 Agent가 실패하지 않아 한 번도 실행되지 않는 상황에서, 더 어려운 버그를 만드는 대신 결함을 주입하는 방향으로 전환한 것이 이 프로젝트의 핵심 결정이었습니다.
