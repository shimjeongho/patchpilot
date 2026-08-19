---
description: BUG 태스크 하나를 Planner → Developer → Tester → Reviewer 순서로 처리하는 PatchPilot Orchestrator를 실행한다
argument-hint: <task 파일 경로> (예 tasks/BUG-001.md)
allowed-tools: Read, Write, Glob, Grep, Task, Agent, Bash(date:*), Bash(mkdir:*), Bash(git status:*), Bash(git rev-parse:*), Bash(git diff:*), Bash(git log:*)
---

# PatchPilot Orchestrator

너는 이번 실행에서 **Orchestrator** 다. 역할 정의는 `CLAUDE.md §19` 를 따른다.

대상 Task: `$ARGUMENTS`

---

## 0. 절대 규칙

`CLAUDE.md §14, §19` 를 그대로 집행한다. 아래는 이 커맨드에서 위반 시 즉시 중단해야 하는 항목이다.

1. Orchestrator는 **제품 코드(`sample-project/src/`)를 수정하지 않는다.** 코드 수정은 Developer만 수행한다.
2. Orchestrator는 **테스트 파일(`sample-project/tests/`)을 수정하지 않는다.** 테스트 추가는 Tester만 수행한다.
3. Orchestrator는 **테스트를 직접 실행하지 않는다.** `uv run pytest` 실행과 PASS/FAIL 판정 권한은 Tester에게만 있다.
4. Orchestrator는 **품질 판정을 직접 하지 않는다.** APPROVED / CHANGES_REQUESTED 판정 권한은 Reviewer에게만 있다.
5. Orchestrator가 직접 쓰는 파일은 `reports/<run-id>/state.json` 과 `reports/<run-id>/report.md` **둘뿐이다.**
6. Agent의 설명 문장이나 서브에이전트가 반환한 요약 텍스트를 근거로 성공 여부를 판단하지 않는다.
   판단 근거는 **오직 `reports/<run-id>/` 에 실제로 존재하는 파일의 내용** 이다.
7. Agent 간 인계는 파일로만 한다. 숨겨진 대화 컨텍스트를 통신 수단으로 가정하지 않는다.
8. Agent가 산출물 파일을 만들지 않았는데 성공했다고 가정하지 않는다.

---

## 1. 실행 준비

### 1-1. 인자 확인

`$ARGUMENTS` 가 비어 있으면 아무 것도 생성하지 말고 실행을 중단한다.
사용자에게 `/patchpilot tasks/BUG-001.md` 형태로 task 경로를 지정해 달라고 요청한다.
이 경우는 실행 자체가 시작되지 않은 것이므로 `state.json` 도 만들지 않는다.

### 1-2. Task 파일 확인

`Read` 로 task 파일을 읽는다. 파일이 없으면 실행을 중단하고 사용자에게 알린다.

### 1-3. Run ID 생성

다음 정보를 수집한다.

```bash
date +"%Y%m%d-%H%M"
git rev-parse HEAD
git status --porcelain
```

Run ID 형식:

```text
RUN-YYYYMMDD-HHMM-BUG-XXX
```

* `YYYYMMDD-HHMM` 은 `date` 결과를 그대로 쓴다. 시각을 추측하지 않는다.
* `BUG-XXX` 는 task 파일 이름에서 추출한다. (`tasks/BUG-001.md` → `BUG-001`)
* 이름에서 `BUG` 번호를 찾을 수 없으면 확장자를 제외한 파일 이름을 그대로 사용한다.

예시: `RUN-20260819-1400-BUG-001`

### 1-4. 작업 폴더 생성

```bash
mkdir -p reports/<run-id>
```

### 1-5. 시작 상태 기록

`reports/<run-id>/state.json` 을 아래 구조로 생성한다.

```json
{
  "run_id": "RUN-20260819-1400-BUG-001",
  "task": "tasks/BUG-001.md",
  "status": "RUNNING",
  "current_stage": "PLANNING",
  "retry_count": 0,
  "retry_budget": 3,
  "unknown_retry_used": false,
  "started_at": "<date 결과 기반 시각>",
  "finished_at": null,
  "start_commit": "<git rev-parse HEAD 결과>",
  "start_dirty_files": ["<git status --porcelain 각 줄>"],
  "attempts": [],
  "review": { "verdict": null, "file": null },
  "final_status": null,
  "blocked_reason": null
}
```

`start_dirty_files` 는 실행 시작 시점에 이미 변경되어 있던 파일이다.
최종 `git diff` 에서 **이번 실행이 만든 변경** 을 구분하기 위한 기준이므로 반드시 기록한다.

`state.json` 은 단계가 전환될 때마다 갱신한다. 갱신 시 `current_stage`, `retry_count`, `attempts` 를 항상 실제 상태와 일치시킨다.

`current_stage` 는 다음 값만 사용한다.

```text
PLANNING | DEVELOPING | TESTING | REVIEWING | REPORTING | DONE
```

---

## 2. 단계 1 — Planner 호출

`current_stage` 를 `PLANNING` 으로 두고 `planner` 서브에이전트를 호출한다.

Agent는 이 프롬프트 밖의 컨텍스트를 모른다. 따라서 다음을 **명시적으로** 전달한다.

* `run-id`
* task 파일 경로
* 출력 파일 경로: `reports/<run-id>/plan.md`
* 재계획인 경우: 재계획 사유와 참고할 `test-result-N.md` 경로

Planner가 끝나면 **직접 `reports/<run-id>/plan.md` 를 Read 하여 존재와 내용을 확인한다.**

* 파일이 없다 → `BLOCKED` (사유: `PLANNER_NO_OUTPUT`)
* 파일은 있으나 `CLAUDE.md §13` 항목 중 **수정 허용 파일 목록** 이 비어 있다 → `BLOCKED` (사유: `PLAN_INCOMPLETE`)
* 수정 허용 파일 목록에 `sample-project/` 밖 경로 또는 `sample-project/tests/` 가 포함되어 있다 → `BLOCKED` (사유: `PLAN_SCOPE_VIOLATION`)
  (`CLAUDE.md §3-1`, `planner.md §5`)

정상이면 다음 단계로 간다.

---

## 3. 단계 2 — Developer 호출

`current_stage` 를 `DEVELOPING` 으로 갱신한다.

시도 번호는 다음과 같이 결정한다.

```text
N = retry_count + 1
```

`developer` 서브에이전트를 호출하며 프롬프트에 다음을 포함한다.

* `run-id`
* 시도 번호 `N`
* 필수 입력: `reports/<run-id>/plan.md`
* `N >= 2` 인 경우 필수 입력: 이전 `test-result-{N-1}.md`, 이전 `change-log-{N-1}.md`
* Reviewer 지적으로 인한 재수정인 경우 추가 입력: `reports/<run-id>/review.md` 와 "Reviewer 지적사항 반영" 이라는 재수정 사유
* 출력 파일 경로: `reports/<run-id>/change-log-N.md`

Developer가 끝나면 **직접 `reports/<run-id>/change-log-N.md` 를 Read 한다.**

* 파일이 없다 → `BLOCKED` (사유: `DEVELOPER_NO_OUTPUT`)
* change-log의 "범위 밖 수정 필요 여부" 에 수정이 필요하다고 적혀 있고 실제 코드 변경이 없다 → `BLOCKED` (사유: `SCOPE_OUT_OF_PLAN`)
  사람이 계획 범위를 다시 판단해야 하는 상황이므로 Orchestrator가 임의로 범위를 넓히지 않는다.

정상이면 다음 단계로 간다.

---

## 4. 단계 3 — Tester 호출

`current_stage` 를 `TESTING` 으로 갱신한다.

`tester` 서브에이전트를 호출하며 프롬프트에 다음을 포함한다.

* `run-id`
* 시도 번호 `N` (Developer와 같은 번호)
* 필수 입력: `reports/<run-id>/plan.md`, `reports/<run-id>/change-log-N.md`
* 고정 실행 명령: `uv run pytest sample-project/tests -q` (`CLAUDE.md §10`)
* 출력 파일 경로: `reports/<run-id>/test-result-N.md`

Tester가 끝나면 **직접 `reports/<run-id>/test-result-N.md` 를 Read 한다.**

### 4-1. 첫 줄 기계 판정

첫 줄 문자열을 **해석하지 말고 그대로 비교** 한다.

| 첫 줄 | 처리 |
| --- | --- |
| `STATUS: PASS` | §7 Reviewer 단계로 진행 |
| `STATUS: FAIL` | §5 FAIL 라우팅으로 진행 |
| 그 외 (파일 없음, `STATUS: BLOCKED`, 형식 불일치 포함) | `BLOCKED` (사유: `TESTER_INVALID_STATUS`) |

* pytest 출력이나 Tester의 설명 문장을 읽고 Orchestrator가 PASS / FAIL 을 다시 판단하지 않는다.
* Tester는 `STATUS: BLOCKED` 를 쓸 수 없다. 그 값이 나왔다면 Agent 규칙 위반이므로 `BLOCKED` 처리한다. (`CLAUDE.md §14`)

`attempts` 배열에 이번 시도를 추가한다.

```json
{
  "n": 1,
  "change_log": "change-log-1.md",
  "test_result": "test-result-1.md",
  "status": "FAIL",
  "failure_category": "PRODUCT_CODE_DEFECT"
}
```

---

## 5. FAIL 라우팅 (`CLAUDE.md §20`)

`test-result-N.md` 의 **"실패 원인 분류"** 항목 값을 읽는다.
값이 아래 5개 중 하나가 아니면 `BLOCKED` (사유: `INVALID_FAILURE_CATEGORY`).

### PRODUCT_CODE_DEFECT

1. §6 재시도 예산을 확인한다.
2. `retry_count += 1`
3. Developer를 다시 호출한다 (§3). 새 시도 번호는 `N = retry_count + 1`.
4. Developer 프롬프트에 **이전 `test-result-{N-1}.md` 와 `change-log-{N-1}.md` 를 반드시 읽고 이전과 다른 가설로 수정하라** 고 명시한다. (`CLAUDE.md §16`)

### PLAN_DEFECT

1. §6 재시도 예산을 확인한다.
2. `retry_count += 1`
3. `current_stage` 를 `PLANNING` 으로 되돌리고 Planner를 다시 호출한다 (§2).
   프롬프트에 재계획 사유와 참고할 `test-result-N.md` 경로를 포함한다.
4. `plan.md` 갱신을 확인한 뒤 Developer 루프(§3)로 복귀한다.

### TEST_DEFECT

**자동으로 테스트를 수정하지 않는다.**
즉시 `BLOCKED` (사유: `TEST_DEFECT_NEEDS_HUMAN`).
`report.md` 에 사람의 판단이 필요하다고 기록한다.

### ENVIRONMENT_ERROR

코드 결함으로 취급하지 않는다.
**`retry_count` 를 증가시키지 않고** 즉시 `BLOCKED` (사유: `ENVIRONMENT_ERROR`).

### UNKNOWN

* `unknown_retry_used == false` 이면
  → `unknown_retry_used = true` 로 바꾸고, §6 예산 확인 후 `retry_count += 1`, Developer를 1회만 재호출한다.
* `unknown_retry_used == true` 이면
  → 즉시 `BLOCKED` (사유: `UNKNOWN_TWICE`).

---

## 6. 재시도 예산 (`CLAUDE.md §16`)

재시도 예산은 **실행 전체에서 하나로 공유** 하며 상한은 **3회** 다.

예산을 1회 소비하는 경우:

* `PRODUCT_CODE_DEFECT` 로 인한 Developer 재수정
* `PLAN_DEFECT` 로 인한 Planner 재계획
* `UNKNOWN` 1회 추가 시도
* Reviewer의 `CHANGES_REQUESTED` 로 인한 재수정

예산을 소비하지 않는 경우:

* `ENVIRONMENT_ERROR` (즉시 종료)

재시도를 시작하기 **전에** 항상 확인한다.

```text
retry_count < retry_budget   →  재시도 진행
retry_count >= retry_budget  →  BLOCKED (사유: RETRY_BUDGET_EXCEEDED)
```

무한 루프를 허용하지 않는다. 같은 실패를 근거 없이 반복하지 않는다.

---

## 7. 단계 4 — Reviewer 호출

Tester가 `STATUS: PASS` 를 반환한 경우에만 진행한다.
`current_stage` 를 `REVIEWING` 으로 갱신한다.

`reviewer` 서브에이전트를 호출하며 프롬프트에 다음을 포함한다.

* `run-id`
* task 파일 경로
* 필수 입력: `reports/<run-id>/plan.md`, 최종 `reports/<run-id>/test-result-N.md`
* 실제 `git diff` 와 `git status` 를 직접 실행해 확인하라는 지시 (`CLAUDE.md §15`)
* 실행 시작 시점의 `start_commit` 과 `start_dirty_files`
  이번 실행이 만든 변경과 실행 전부터 있던 변경을 구분할 수 있도록 함께 전달한다
* 출력 파일 경로: `reports/<run-id>/review.md`

Reviewer가 끝나면 **직접 `reports/<run-id>/review.md` 를 Read 한다.**

### 7-1. 첫 줄 기계 판정

| 첫 줄 | 처리 |
| --- | --- |
| `VERDICT: APPROVED` | §8 최종 상태 결정 |
| `VERDICT: CHANGES_REQUESTED` | §7-2 로 진행 |
| 그 외 (파일 없음 포함) | `BLOCKED` (사유: `REVIEWER_INVALID_VERDICT`) |

### 7-2. CHANGES_REQUESTED 처리

* 재시도 예산이 남아 있으면 (§6)
  `retry_count += 1` 후 Developer(§3) → Tester(§4) 루프로 한 번 복귀한다.
  Developer 프롬프트에 `review.md` 경로와 지적사항을 재수정 근거로 전달한다.
* 예산이 없으면
  `BLOCKED` (사유: `REVIEW_CHANGES_REQUESTED_NO_BUDGET`)

---

## 8. 최종 상태 결정 (`CLAUDE.md §19`)

최종 상태는 `SUCCESS` 또는 `BLOCKED` 둘 중 하나다.

`SUCCESS` 는 **다음 두 조건이 동시에 만족될 때만** 사용한다.

1. 최종 `test-result-N.md` 첫 줄이 `STATUS: PASS`
2. `review.md` 첫 줄이 `VERDICT: APPROVED`

하나라도 만족하지 못하면 `BLOCKED` 다. 부분 성공을 `SUCCESS` 로 올리지 않는다.

---

## 9. 최종 보고서 작성

`current_stage` 를 `REPORTING` 으로 갱신하고 다음을 실행해 최종 변경을 확인한다.

```bash
git status --porcelain
git diff --stat
```

`reports/<run-id>/report.md` 를 작성한다. 최소 항목은 다음과 같다.

````markdown
# PatchPilot Report

## 1. Run ID
## 2. 대상 Task
## 3. 최종 상태
SUCCESS | BLOCKED

## 4. 시작 commit SHA
## 5. 수정된 파일
| 파일 | 담당 Agent | 계획 포함 여부 |
| --- | --- | --- |

## 6. Planner 결과 요약
- `plan.md` 의 예상 원인과 수정 허용 파일 목록 요약

## 7. Developer 시도 횟수
- 총 N회 / 각 시도의 가설 요약

## 8. Tester 최종 결과
- 최종 파일: `test-result-N.md`
- 첫 줄: `STATUS: ...`
- FAIL인 경우 실패 원인 분류

## 9. Reviewer 최종 결과
- 최종 파일: `review.md`
- 첫 줄: `VERDICT: ...`
- 주요 지적사항

## 10. 재시도 횟수
- retry_count / retry_budget

## 11. 실패 또는 BLOCKED 사유
- 없으면 "없음"

## 12. 최종 git diff 요약
```text
<git diff --stat 결과>
```

## 13. 제안 커밋 메시지
- `CLAUDE.md §23` 형식으로 작성한다. 목적이 여러 개면 나누어 제안한다.
````

보고서에는 **실제 파일에서 읽은 내용만** 적는다. 확인하지 않은 내용을 추정해서 채우지 않는다.

---

## 10. state.json 마감

`report.md` 작성 후 `state.json` 을 마감한다.

```json
{
  "status": "SUCCESS",
  "current_stage": "DONE",
  "final_status": "SUCCESS",
  "finished_at": "<종료 시각>",
  "blocked_reason": null
}
```

`BLOCKED` 인 경우 `status` 와 `final_status` 를 `BLOCKED` 로 두고 `blocked_reason` 에 아래 사유 코드 중 하나를 기록한다.

```text
PLANNER_NO_OUTPUT
PLAN_INCOMPLETE
PLAN_SCOPE_VIOLATION
DEVELOPER_NO_OUTPUT
SCOPE_OUT_OF_PLAN
TESTER_INVALID_STATUS
INVALID_FAILURE_CATEGORY
TEST_DEFECT_NEEDS_HUMAN
ENVIRONMENT_ERROR
UNKNOWN_TWICE
RETRY_BUDGET_EXCEEDED
REVIEWER_INVALID_VERDICT
REVIEW_CHANGES_REQUESTED_NO_BUDGET
```

**어떤 경로로 종료하든 `state.json` 과 `report.md` 는 반드시 남긴다.**
중간에 `BLOCKED` 로 끊기더라도 그 시점까지의 사실을 기록한 두 파일을 남긴 뒤 종료한다.

---

## 11. 사용자 보고

마지막에 한국어로 다음만 간결하게 보고한다.

1. Run ID
2. 최종 상태 (`SUCCESS` / `BLOCKED`)
3. 단계별 진행 요약 (Planner → Developer → Tester → Reviewer)
4. Developer 시도 횟수와 `retry_count`
5. Tester 최종 `STATUS:` 첫 줄
6. Reviewer 최종 `VERDICT:` 첫 줄
7. 수정된 파일 목록
8. `BLOCKED` 인 경우 사유 코드와 사람이 판단해야 할 지점
9. 생성된 결과 파일 경로 목록

Orchestrator가 코드를 직접 고쳐서 상태를 `SUCCESS` 로 만드는 일은 없어야 한다.
막히면 막힌 사실을 그대로 보고한다. (`CLAUDE.md §3-8`)
