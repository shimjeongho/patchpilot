AUDIT: PASS

# PatchPilot Harness Audit

## 종합

| 항목 | 값 |
| --- | --- |
| Verdict | PASS |
| Score | 98 / 100 |
| Critical | 0 |
| schema_version | 1 |
| audit_version | 1.0.0 |
| rubric_version | 1.0.0 |
| rubric_digest | `sha256:2d63e22b8c5dab0e3852cbd48723f536edfbba9cfbd31d1b0b3d8a3ab7690edd` |

## Critical Hard Gate

Critical 실패 없음. Hard Gate 를 통과했다.

## Category 요약

| Category | 점수 | 실패 check |
| --- | --- | --- |
| A. Agent Role Isolation | 13 / 13 | - |
| B. Guard Registration & Enforcement | 20 / 20 | - |
| C. Control Contract Consistency | 19 / 19 | - |
| D. Artifact & Evidence Contract | 13 / 13 | - |
| E. Eval Coverage & Replay | 15 / 17 | E4b |
| F. Documentation Consistency | 10 / 10 | - |
| G. Reproducibility & Automation | 8 / 8 | - |

## Check 상세

### A. Agent Role Isolation

#### A1 - PASS (3/3)

Agent 정의 4개와 frontmatter 3키 존재

- 계약: CLAUDE.md §11
- 근거:
  - .claude/agents/: developer, planner, reviewer, tester
  - 각 frontmatter 에 name / description / tools 존재

#### A2 - PASS (3/3)

frontmatter name 집합이 AGENT_TYPES 와 일치

- 계약: CLAUDE.md §11
- 근거:
  - _guard_common.AGENT_TYPES = developer, planner, reviewer, tester
  - frontmatter name 집합 일치

#### A3 - PASS (4/4) **Critical**

Agent tools 가 최소 권한 행렬과 일치

- 계약: CLAUDE.md §11
- 근거:
  - developer: Edit, Glob, Grep, Read, Write
  - planner: Glob, Grep, Read, Write
  - reviewer: Bash, Glob, Grep, Read, Write
  - tester: Bash, Glob, Grep, Read, Write

#### A4 - PASS (3/3)

Agent 정의에 금지 사항 / 종료 전 체크리스트 존재

- 계약: CLAUDE.md §11
- 근거:
  - 4개 Agent 정의 모두 금지 사항 / 종료 전 체크리스트 절 보유

### B. Guard Registration & Enforcement

#### B1 - PASS (3/3)

Guard 구현 파일과 공통 모듈 존재

- 계약: CLAUDE.md §22
- 근거:
  - .claude/hooks/: _guard_common.py, guard_bash_scope.py, guard_plan_scope.py, guard_stop_gate.py, guard_test_files.py

#### B2 - PASS (3/3)

HOOK_ID 가 파일명 규약과 일치하고 서로 다름

- 계약: CLAUDE.md §22, §25
- 근거:
  - guard_bash_scope.py -> guard-bash-scope
  - guard_plan_scope.py -> guard-plan-scope
  - guard_stop_gate.py -> guard-stop-gate
  - guard_test_files.py -> guard-test-files

#### B3 - PASS (8/8) **Critical**

settings.json 등록 집합이 Guard 파일 집합과 양방향 일치

- 계약: CLAUDE.md §22
- 근거:
  - guard_bash_scope.py -> PreToolUse matcher=Bash
  - guard_plan_scope.py -> PreToolUse matcher=Write|Edit
  - guard_stop_gate.py -> Stop matcher=None
  - guard_test_files.py -> PreToolUse matcher=Write|Edit

#### B4 - PASS (3/3) **Critical**

Stop 훅이 중첩형으로 등록됨

- 계약: CLAUDE.md §25
- 근거:
  - Stop 등록이 중첩형 (hooks 배열을 감싼 형태) 입니다: 1건

#### B5 - PASS (3/3)

Guard 마다 단위 테스트 모듈 존재

- 계약: CLAUDE.md §22
- 근거:
  - evals/tests/test_guard_bash_scope.py
  - evals/tests/test_guard_plan_scope.py
  - evals/tests/test_guard_stop_gate.py
  - evals/tests/test_guard_test_files.py

### C. Control Contract Consistency

#### C1 - PASS (5/5) **Critical**

실패 원인 분류 5종이 4개 소스에서 일치

- 계약: CLAUDE.md §14
- 근거:
  - 4개 소스 일치: ENVIRONMENT_ERROR, PLAN_DEFECT, PRODUCT_CODE_DEFECT, TEST_DEFECT, UNKNOWN
  - .claude/agents/tester.md
  - CLAUDE.md §14
  - dashboard/lib/types.ts
  - evals/eval_harness.py FAILURE_CATEGORIES

#### C2 - PASS (5/5) **Critical**

BLOCKED 사유 코드가 문서와 구현에서 일치

- 계약: CLAUDE.md §19, §20
- 근거:
  - patchpilot.md §10 == guard_stop_gate.BLOCKED_REASONS (13개)

#### C3 - PASS (4/4)

고정 테스트 명령이 5개 소스에서 동일

- 계약: CLAUDE.md §10
- 근거:
  - 5개 소스 모두 'uv run pytest sample-project/tests -q'
  - .claude/agents/tester.md
  - .claude/commands/patchpilot.md
  - .claude/hooks/guard_bash_scope.py
  - CLAUDE.md
  - evals/eval_harness.py PYTEST_COMMAND

#### C4 - PASS (3/3)

retry_budget = 3 이 4개 소스에서 일치

- 계약: CLAUDE.md §16
- 근거:
  - 4개 소스 모두 retry_budget = 3
  - .claude/commands/patchpilot.md
  - CLAUDE.md §16
  - evals/eval_harness.py Scenario
  - reports/examples/*/state.json

#### C5 - PASS (2/2)

기계 판정 첫 줄 토큰이 판정 코드 3곳에서 동일

- 계약: CLAUDE.md §14, §15
- 근거:
  - .claude/hooks/guard_stop_gate.py: STATUS=FAIL, PASS / VERDICT=APPROVED, CHANGES_REQUESTED
  - evals/eval_harness.py: STATUS=FAIL, PASS / VERDICT=APPROVED, CHANGES_REQUESTED
  - dashboard/lib/parse.ts: STATUS=FAIL, PASS / VERDICT=(없음)

### D. Artifact & Evidence Contract

#### D1 - PASS (3/3)

보존된 대표 결과에 state.json 과 report.md 존재

- 계약: CLAUDE.md §12
- 근거:
  - 대표 결과 6건: EVAL-20260820-1318-HARNESS-EVAL-001, EVAL-20260820-1443-HARNESS-EVAL-002, EVAL-20260820-1554-HARNESS-EVAL-003, EVAL-20260820-1752-HARNESS-EVAL-004, EVAL-20260827-1136-HARNESS-EVAL-005, EVAL-20260827-1219-HARNESS-EVAL-006

#### D2 - PASS (3/3)

대표 결과 state.json 의 스키마와 enum 유효

- 계약: CLAUDE.md §19
- 근거:
  - 대표 결과 6건의 state.json 이 스키마와 enum 계약을 만족

#### D3 - PASS (4/4) **Critical**

Stop Gate 불변식 G1~G21 replay 위반 0건

- 계약: CLAUDE.md §25
- 근거:
  - guard_stop_gate.check_run() replay
  - EVAL-20260820-1318-HARNESS-EVAL-001: SUCCESS / 위반 0건
  - EVAL-20260820-1443-HARNESS-EVAL-002: SUCCESS / 위반 0건
  - EVAL-20260820-1554-HARNESS-EVAL-003: BLOCKED / 위반 0건
  - EVAL-20260820-1752-HARNESS-EVAL-004: BLOCKED / 위반 0건
  - EVAL-20260827-1136-HARNESS-EVAL-005: BLOCKED / 위반 0건
  - EVAL-20260827-1219-HARNESS-EVAL-006: BLOCKED / 위반 0건

#### D4 - PASS (2/2) **Critical**

대표 결과 eval-result.md 첫 줄이 EVAL: PASS

- 계약: evals/README.md §4-12
- 근거:
  - 대표 결과 6건 모두 첫 줄이 'EVAL: PASS'

#### D5 - PASS (1/1)

gitignore 가 실행 산출물을 무시하고 대표 결과를 보존

- 계약: CLAUDE.md §12
- 근거:
  - reports/* 무시 + reports/examples/** 보존

### E. Eval Coverage & Replay

#### E1 - PASS (4/4)

시나리오 정의의 task 와 install fixture 실재

- 계약: evals/README.md §12
- 근거:
  - harness-eval-001: task + fixture 2개
  - harness-eval-002: task + fixture 4개
  - harness-eval-003: task + fixture 4개
  - harness-eval-004: task + fixture 2개
  - harness-eval-005: task + fixture 2개
  - harness-eval-006: task + fixture 2개

#### E2 - PASS (3/3)

회귀 기준 대표 결과가 전부 보존됨

- 계약: evals/README.md §10
- 근거:
  - harness-eval-001 -> reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001
  - harness-eval-002 -> reports/examples/EVAL-20260820-1443-HARNESS-EVAL-002
  - harness-eval-003 -> reports/examples/EVAL-20260820-1554-HARNESS-EVAL-003
  - harness-eval-004 -> reports/examples/EVAL-20260820-1752-HARNESS-EVAL-004
  - harness-eval-005 -> reports/examples/EVAL-20260827-1136-HARNESS-EVAL-005
  - harness-eval-006 -> reports/examples/EVAL-20260827-1219-HARNESS-EVAL-006

#### E3 - PASS (2/2)

eval-result.md 의 종합 수치와 표 행 수가 일치

- 계약: evals/README.md §8
- 근거:
  - EVAL-20260820-1318-HARNESS-EVAL-001: 27/27 항목 (표 27행)
  - EVAL-20260820-1443-HARNESS-EVAL-002: 37/37 항목 (표 37행)
  - EVAL-20260820-1554-HARNESS-EVAL-003: 28/28 항목 (표 28행)
  - EVAL-20260820-1752-HARNESS-EVAL-004: 55/55 항목 (표 55행)
  - EVAL-20260827-1136-HARNESS-EVAL-005: 31/31 항목 (표 31행)
  - EVAL-20260827-1219-HARNESS-EVAL-006: 57/57 항목 (표 57행)

#### E4a - PASS (2/2)

검증된 종료 경로가 4개 이상

- 계약: CLAUDE.md §20
- 근거:
  - 검증된 종료 경로 6/7개
  - ENVIRONMENT_ERROR, PLAN_DEFECT_REPLAN, PRODUCT_CODE_DEFECT_RETRY, RETRY_BUDGET_EXCEEDED, REVIEW_CHANGES_REQUESTED_NO_BUDGET, TEST_DEFECT_NEEDS_HUMAN

#### E4b - FAIL (0/2)

종료 경로 7개 전부에 결정론적 eval 존재

- 계약: CLAUDE.md §20
- 근거:
  - 검증되지 않은 종료 경로 1개: UNKNOWN_TWICE
  - 검증됨: ENVIRONMENT_ERROR, PLAN_DEFECT_REPLAN, PRODUCT_CODE_DEFECT_RETRY, RETRY_BUDGET_EXCEEDED, REVIEW_CHANGES_REQUESTED_NO_BUDGET, TEST_DEFECT_NEEDS_HUMAN
- 조치: 검증되지 않은 종료 경로의 eval 시나리오를 추가한다. 현재 남은 것은 UNKNOWN 2회 경로 하나다.

#### E5 - PASS (2/2)

시나리오가 참조하는 결함 모듈이 전부 존재

- 계약: evals/README.md §11
- 근거:
  - 참조된 결함 모듈 10개 모두 존재: env_error_001, plan_defect_001, retry_001, retry_budget_001, retry_budget_002, retry_budget_003, review_budget_001, review_budget_002, review_budget_003, test_defect_001

#### E6 - PASS (2/2)

연쇄 주입 시나리오의 결함이 서로 다름

- 계약: evals/README.md §3-12
- 근거:
  - harness-eval-004: 연쇄 3개 모두 서로 다름
  - harness-eval-006: 연쇄 3개 모두 서로 다름

### F. Documentation Consistency

#### F1 - PASS (3/3)

CLAUDE.md §22 완료 항목이 지목하는 파일 실재

- 계약: CLAUDE.md §22
- 근거:
  - §22 완료 항목 10개
  - 확인된 경로: .claude/hooks/guard_bash_scope.py, .claude/hooks/guard_plan_scope.py, .claude/hooks/guard_stop_gate.py, .claude/hooks/guard_test_files.py, dashboard, evals, sample-project, sample-project/tests

#### F2 - PASS (3/3)

README Hook 표가 settings.json 등록과 일치

- 계약: CLAUDE.md §22
- 근거:
  - README Hook 표 4행 == settings.json 등록

#### F3 - PASS (2/2)

README 권한 표가 Agent frontmatter 와 일치

- 계약: CLAUDE.md §11
- 근거:
  - developer: Edit, Glob, Grep, Read, Write
  - planner: Glob, Grep, Read, Write
  - reviewer: Bash, Glob, Grep, Read, Write
  - tester: Bash, Glob, Grep, Read, Write

#### F4 - PASS (2/2)

문서의 Stop Gate 불변식 개수 주장이 구현과 일치

- 계약: CLAUDE.md §25
- 근거:
  - guard_stop_gate.py = G1~G21 (21개)
  - 문서 주장 일치: CLAUDE.md, README.md

### G. Reproducibility & Automation

#### G1 - PASS (4/4)

CI 워크플로가 세 검증기를 모두 실행

- 계약: CLAUDE.md §22
- 근거:
  - .github/workflows/ci.yml 가 세 검증기를 모두 실행
  - pytest evals/tests, eval_harness.py selftest, harness_audit.py

#### G2 - PASS (2/2)

uv 잠금 파일과 Python 버전 고정

- 계약: CLAUDE.md §24
- 근거:
  - uv.lock / .python-version / pyproject.toml dev pytest 선언 확인

#### G3 - PASS (2/2)

Audit 자기 검증 테스트와 rubric 무결성

- 계약: CLAUDE.md §22
- 근거:
  - evals/tests/test_harness_audit.py 존재
  - rubric_digest = sha256:2d63e22b8c5dab0e3852cbd48723f536edfbba9cfbd31d1b0b3d8a3ab7690edd
  - rubric_version = 1.0.0 / check 33개

## 다음 행동

1. `E4b` (2점) - 검증되지 않은 종료 경로의 eval 시나리오를 추가한다. 현재 남은 것은 UNKNOWN 2회 경로 하나다.

## 경고 (점수 미반영)

- **W-EVAL-ROUTES** 결정론적 eval 이 없는 종료 경로 1개
  - UNKNOWN_TWICE

## Audit이 검사하지 않는 것

- Agent 의 실시간 행위. `PreToolUse` / `Stop` Hook 의 담당이다.
- Harness 실행의 상태 전이. `evals/eval_harness.py` 의 담당이다.
- `sample-project/` 의 애플리케이션 코드 품질. 감사 대상은 Harness 다.
- LLM 출력의 내용적 타당성. 기계로 증명할 수 없는 판단은 채점하지 않는다.
- git 상태와 커밋 이력.
- 계획 범위와 실제 diff 의 대조. 오탐 위험 때문에 Stop Gate 도 검사하지 않는다.
- 점수가 높다는 사실 자체. 계약이 정합적이라는 것과 Harness 가 유효하다는 것은 다르다.
