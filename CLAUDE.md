# PatchPilot 공통 규칙

## 1. 프로젝트 목적

PatchPilot은 Harness Engineering 기반의 AI 버그 분석 및 수정 프로젝트입니다.

사용자가 버그 또는 수정 요구사항을 입력하면 Agent들이 역할을 나누어 다음 과정을 수행합니다.

요구사항 분석 → 수정 계획 → 코드 수정 → 테스트 → 실패 분석 → 재수정 → 코드 리뷰 → 결과 보고

Agent가 수정할 실제 대상 코드는 `sample-project/` 아래에 있습니다.

---

## 2. 저장소 경계

### Harness 영역

다음 파일과 폴더는 Harness 자체를 구성합니다.

* `CLAUDE.md`
* `.claude/`
* `tasks/`
* `reports/`
* `evals/`

Agent는 명시적인 지시가 없는 한 Harness 설정 파일을 임의로 수정하지 않습니다.

### 수정 대상 영역

실제 제품 코드는 다음 경로에 있습니다.

`sample-project/`

버그 수정 작업은 원칙적으로 이 경로 안에서만 수행합니다.

---

## 3. 공통 핵심 규칙

1. 수정 대상은 원칙적으로 `sample-project/` 하위로 제한합니다.

2. 계획에 없는 파일은 임의로 수정하지 않습니다.

3. 테스트를 통과시키기 위해 테스트를 약화시키지 않습니다.

금지 예시:

* assertion 삭제
* 예상값을 잘못된 결과에 맞게 변경
* 테스트 skip 처리
* 실패 테스트 삭제
* 검증 조건 완화

4. 테스트 실행 명령어는 다음 하나로 통일합니다.

```bash
uv run pytest sample-project/tests -q
```

5. 추측하지 않습니다. 실제로 읽은 코드와 실제 명령 실행 결과를 근거로 판단합니다.

6. 각 Agent는 자신의 작업 결과를 파일로 남겨야 합니다.

7. 요구사항과 관계없는 리팩터링, 파일명 변경, 전체 포맷팅, 의존성 추가를 하지 않습니다.

8. 진행이 불가능한 경우 성공한 것처럼 처리하지 않고 `BLOCKED` 상태로 보고합니다.

9. 문제를 해결할 수 있는 가장 작고 명확한 변경을 우선합니다.

10. 요구사항에 명시되지 않은 기존 동작은 최대한 유지합니다.

---

## 4. Python 코드 컨벤션

Python 코드는 다음 규칙을 따릅니다.

* PEP 8 스타일을 기본으로 합니다.
* 들여쓰기는 공백 4칸을 사용합니다.
* 변수와 함수 이름은 `snake_case`를 사용합니다.
* 클래스 이름은 `PascalCase`를 사용합니다.
* 상수는 `UPPER_SNAKE_CASE`를 사용합니다.
* 하나의 함수는 가능한 한 하나의 책임만 담당합니다.
* 의미 없는 축약어를 사용하지 않습니다.
* 중복 로직은 필요할 경우만 정리합니다.
* 불필요한 추상화는 만들지 않습니다.
* 표준 라이브러리로 해결할 수 있으면 새로운 의존성을 추가하지 않습니다.
* 기존 프로젝트 스타일이 존재하면 기존 스타일을 우선합니다.

예시:

좋은 함수명:

```python
def calculate_total_price(items):
    ...
```

좋지 않은 함수명:

```python
def calc(x):
    ...
```

---

## 5. 주석 규칙

모든 코드에 주석을 강제로 작성하지 않습니다.

주석은 코드가 무엇을 하는지 반복하는 용도가 아니라, 코드만 보고는 알기 어려운 **이유와 의도**를 설명하는 데 사용합니다.

주석이 필요한 경우:

* 비즈니스 규칙이 코드만 보고 명확하지 않은 경우
* 예외 상황을 특별하게 처리하는 경우
* 특정 기술적 제약 때문에 우회 로직이 필요한 경우
* 알고리즘의 의도가 직관적이지 않은 경우
* 이후 개발자가 이유를 오해할 가능성이 높은 경우

좋은 예:

```python
# 나머지 금액을 앞 사람부터 1원씩 분배해 전체 합계를 보존한다.
remainder = amount % people
```

좋지 않은 예:

```python
# 나머지를 계산한다.
remainder = amount % people
```

의미 없는 주석은 작성하지 않습니다.

---

## 6. Docstring 규칙

외부에서 호출되는 주요 함수나 동작이 명확하지 않은 함수에는 간결한 Docstring을 작성합니다.

예:

```python
def split_amount(amount: int, people: int) -> list[int]:
    """금액을 인원수에 맞게 나누되 전체 합계를 유지한다."""
```

단순한 내부 helper 함수에는 불필요하게 긴 Docstring을 작성하지 않습니다.

---

## 7. 타입 힌트 규칙

새로 작성하거나 의미 있게 수정하는 주요 함수에는 가능한 경우 타입 힌트를 사용합니다.

예:

```python
def split_amount(amount: int, people: int) -> list[int]:
```

단, 기존 코드 전체를 타입 힌트로 바꾸는 식의 범위 밖 수정은 하지 않습니다.

---

## 8. 예외 처리 규칙

오류를 조용히 무시하지 않습니다.

금지 예시:

```python
try:
    ...
except Exception:
    pass
```

가능한 경우 구체적인 예외를 사용합니다.

예:

```python
if people <= 0:
    raise ValueError("people은 1 이상이어야 합니다.")
```

에러 메시지는 무엇이 잘못되었는지 알 수 있도록 작성합니다.

---

## 9. 코드 품질 규칙

작업 완료 전 다음을 확인합니다.

* 변수와 함수 이름이 의미를 명확하게 표현하는가
* 불필요한 중복 코드가 생기지 않았는가
* 사용하지 않는 코드가 남아 있지 않은가
* 디버깅용 `print()`가 남아 있지 않은가
* 사용하지 않는 import가 남아 있지 않은가
* 요구사항과 관계없는 파일을 수정하지 않았는가
* 필요한 예외 상황을 처리했는가
* 변경 범위가 최소한으로 유지되었는가

---

## 10. 테스트 정책

기본 테스트 명령어:

```bash
uv run pytest sample-project/tests -q
```

테스트 규칙:

* 기존 테스트를 약화시키지 않습니다.
* 기존 정상 테스트는 계속 통과해야 합니다.
* 버그 수정 시 필요하면 회귀 테스트를 추가합니다.
* 테스트 이름만 봐도 어떤 상황을 검증하는지 알 수 있어야 합니다.
* 하나의 테스트는 가능한 한 하나의 핵심 동작을 검증합니다.

좋은 예:

```python
def test_split_preserves_total_when_amount_is_not_evenly_divisible():
```

좋지 않은 예:

```python
def test_split2():
```

특정 실패 테스트 하나만 통과했다고 작업 완료로 보지 않습니다.

전체 테스트가 통과해야 합니다.

Tester가 회귀 테스트를 추가할 때의 절차는 §21을 따릅니다.

Python 실행 환경과 의존성 관리 규칙은 §24를 따릅니다.

---

## 11. Agent별 수정 권한

### Planner

* 코드 분석 가능
* 수정 계획 작성 가능
* 제품 코드 수정 금지

### Developer

* 제품 코드 수정 가능
* 테스트 파일 수정 금지

### Tester

* 테스트 실행 가능
* 필요한 회귀 테스트 추가 가능
* 제품 코드 수정 금지
* 기존 테스트 약화 금지

### Reviewer

* 코드 수정 금지
* 실제 Git diff를 기준으로 검토
* 요구사항 충족 여부와 불필요한 변경 여부를 확인

### Orchestrator

* 메인 Claude Code 세션이 담당
* Agent 실행 순서와 현재 단계 관리
* 재시도 횟수 관리
* `report.md`, `state.json` 작성
* 최종 실행 상태 결정
* 제품 코드 수정 금지
* 테스트 파일 수정 금지

상세한 책임은 §19를 따릅니다.

---

## 12. 결과 파일 규칙

각 실행은 다음 폴더를 사용합니다.

```text
reports/<run-id>/
```

예상 결과 파일:

```text
plan.md
change-log-1.md
test-result-1.md
change-log-2.md
test-result-2.md
review.md
report.md
state.json
```

Agent끼리는 숨겨진 대화 내용을 공유한다고 가정하지 않습니다.

다음 Agent에게 전달해야 할 내용은 반드시 파일로 기록합니다.

---

## 13. 수정 계획 규칙

`plan.md`에는 최소한 다음 항목이 들어가야 합니다.

* 요구사항 요약
* 재현 조건
* 기대 동작
* 현재 동작
* 예상 원인
* 실제 코드에서 확인한 근거
* 수정 허용 파일 목록
* 구현 단계
* 검증 방법
* 예상 위험 요소

---

## 14. 테스트 결과 규칙

`test-result-N.md` 첫 줄은 반드시 다음 둘 중 하나여야 합니다.

```text
STATUS: PASS
```

또는

```text
STATUS: FAIL
```

실패 시 다음 내용을 기록합니다.

* 실패 테스트 이름
* pytest 실행 결과
* 주요 traceback
* assertion 차이
* 예상 실패 원인

실패 원인은 다음 중 하나로 분류합니다.

```text
PRODUCT_CODE_DEFECT
TEST_DEFECT
PLAN_DEFECT
ENVIRONMENT_ERROR
UNKNOWN
```

Tester는 `STATUS: BLOCKED`를 작성하지 않습니다.

`BLOCKED`는 Harness 전체의 최종 상태이며 Orchestrator만 결정합니다. (§19, §20)

분류된 실패 원인에 따른 다음 처리는 §20의 라우팅 규칙을 따릅니다.

---

## 15. 리뷰 규칙

Reviewer는 Developer의 설명만 믿지 않고 실제 `git diff`를 확인합니다.

검토 항목:

* 요구사항 충족 여부
* 계획에 없는 파일 수정 여부
* 테스트 무력화 여부
* 잠재적 회귀 가능성
* 불필요한 변경 여부
* 코드 컨벤션 준수 여부
* 주석 규칙 준수 여부
* 예외 처리 적절성

`review.md`의 첫 줄은 다음 둘 중 하나입니다.

```text
VERDICT: APPROVED
```

또는

```text
VERDICT: CHANGES_REQUESTED
```

테스트가 실패한 상태에서는 승인하지 않습니다.

---

## 16. 재시도 규칙

Developer와 Tester의 반복은 최대 3회까지만 허용합니다.

무한 반복은 허용하지 않습니다.

3회 이후에도 해결되지 않으면 Orchestrator가 최종 상태를 `BLOCKED`로 결정하고 종료합니다.

재시도 예산은 실행 전체에서 하나로 공유합니다.

`retry_count`는 **예산을 소비한 실패 시도 수**입니다. 남은 재시도 횟수가 아닙니다.

예산을 소비하는 실패가 발생하면 먼저 `retry_count`를 1 증가시키고, 그 값을 `retry_budget`과 비교합니다.

* `retry_count >= retry_budget` → 추가 Agent 재호출 없이 `BLOCKED`로 종료 (사유: `RETRY_BUDGET_EXCEEDED`)
* `retry_count < retry_budget` → 실패 원인 분류에 따라 다음 Agent를 재호출

따라서 `retry_budget`이 3이면 Developer → Tester 반복은 **최대 3회**이며, 세 번째 실패 시점에 종료합니다.

예산 소비 기준은 다음과 같습니다.

* `PRODUCT_CODE_DEFECT`로 인한 실패 1회 = 예산 1회 소비
* `PLAN_DEFECT`로 인한 실패 1회 = 예산 1회 소비
* `UNKNOWN`으로 인한 실패 1회 = 예산 1회 소비 (1회에 한함)
* Reviewer의 `CHANGES_REQUESTED` 1회 = 예산 1회 소비
* `ENVIRONMENT_ERROR`는 예산을 소비하지 않고 즉시 종료

같은 실패 방법을 근거 없이 반복하지 않습니다.

재시도 시 Developer는 반드시 다음을 읽고 새로운 가설 또는 수정 근거를 `change-log-N.md`에 기록해야 합니다.

* 이전 `test-result-N.md`
* 이전 `change-log-N.md`

실패 원인별 재호출 대상은 §20을 따릅니다.

---

## 17. 최소 변경 원칙

PatchPilot의 목적은 AI가 많은 코드를 생성하는 것이 아니라, 안전하고 통제된 변경을 수행하는 것입니다.

따라서 다음을 피합니다.

* 불필요한 전체 구조 변경
* 관련 없는 함수명 변경
* 전체 파일 자동 포맷팅
* 필요 없는 디자인 패턴 적용
* 필요 없는 라이브러리 추가
* 요구사항 밖 기능 추가

가장 좋은 수정은:

**작고, 정확하고, 테스트 가능하고, 리뷰하기 쉬운 변경입니다.**

---

## 18. 포트폴리오 품질 기준

생성되는 코드는 외부 개발자가 GitHub에서 확인할 수 있는 수준을 목표로 합니다.

작업 완료 전에 다음을 확인합니다.

* 다른 개발자가 코드를 쉽게 이해할 수 있는가
* 변수와 함수 이름이 명확한가
* 중요한 설계 의도가 주석으로 남아 있는가
* Git diff가 리뷰하기 쉬운가
* 버그가 실제로 재현되고 수정되었다는 증거가 있는가
* 면접에서 왜 이렇게 수정했는지 설명할 수 있는가

PatchPilot은 단순 코드 생성 속도보다 다음을 우선합니다.

**재현 가능성 / 추적 가능성 / 유지보수성 / 검증 가능성**

---

## 19. Orchestrator 역할

Agent 외에 메인 Claude Code 세션이 Orchestrator 역할을 담당합니다.

Orchestrator의 책임:

* Agent 실행 순서 관리
* 현재 실행 단계 관리
* 재시도 횟수 관리
* Agent 결과 파일의 `STATUS`, `VERDICT` 확인
* `report.md` 작성
* `state.json` 작성
* 최종 실행 상태 결정

Orchestrator는 직접 제품 코드를 수정하지 않습니다.

테스트 파일도 수정하지 않습니다.

Orchestrator는 Agent가 남긴 파일의 첫 줄(`STATUS:`, `VERDICT:`)을 기준으로 다음 단계를 결정합니다.

Agent의 설명 문장이나 대화 내용을 근거로 성공 여부를 판단하지 않습니다.

Orchestrator가 결정하는 최종 실행 상태는 다음 중 하나입니다.

```text
SUCCESS
BLOCKED
```

`SUCCESS`는 다음 조건을 모두 만족할 때만 사용합니다.

* 최종 `test-result-N.md`가 `STATUS: PASS`
* `review.md`가 `VERDICT: APPROVED`

---

## 20. 실패 원인별 라우팅 규칙

Tester가 `STATUS: FAIL`을 반환하면 §14에서 분류한 실패 원인에 따라 Orchestrator가 다음과 같이 처리합니다.

### PRODUCT_CODE_DEFECT

Developer를 다시 호출합니다.

Developer는 이전 `test-result-N.md`와 `change-log-N.md`를 반드시 읽고 이전 시도와 다른 근거를 기반으로 수정합니다.

재시도 예산 1회를 사용합니다.

### PLAN_DEFECT

Planner를 다시 호출하여 `plan.md`를 갱신합니다.

계획 재수립도 전체 재시도 예산 1회를 사용합니다.

### TEST_DEFECT

자동으로 테스트를 수정하지 않습니다.

Orchestrator가 최종 상태를 `BLOCKED`로 처리하고 사람의 판단이 필요하다고 보고합니다.

### ENVIRONMENT_ERROR

코드 문제로 간주하지 않습니다.

재시도 횟수를 소비하지 않고 즉시 `BLOCKED`로 종료합니다.

### UNKNOWN

Developer에게 1회만 추가 수정 기회를 제공합니다.

다시 `UNKNOWN`이 발생하면 `BLOCKED`로 종료합니다.

---

## 21. 회귀 테스트 절차

Tester는 다음 순서로 검증합니다.

1. 기존 전체 테스트를 실행합니다.
2. 현재 버그를 검증하는 회귀 테스트가 존재하는지 확인합니다.
3. 필요한 회귀 테스트가 없다면 새로운 테스트를 추가할 수 있습니다.
4. 새 테스트를 추가했다면 전체 테스트를 다시 실행합니다.
5. 최종 결과를 `PASS` 또는 `FAIL`로 기록합니다.

Tester는 기존 테스트를 다음과 같이 다룰 수 없습니다.

* 삭제
* 완화
* skip 처리
* assertion 제거
* 예상값 임의 변경

Tester가 새롭게 추가한 테스트 역시 Reviewer의 `git diff` 검토 대상입니다.

새로 추가한 테스트는 `test-result-N.md`에 파일 경로와 추가 이유를 기록합니다.

---

## 22. 향후 Harness 보강 (TODO)

다음은 Harness 보강 항목이며, 구현이 끝난 항목은 `[x]` 로 표시합니다.

* [x] `PreToolUse` Hook — Tester/Reviewer의 Bash를 역할별 화이트리스트로 제한 (`guard_bash_scope.py`)
* [x] `PreToolUse` Hook — `sample-project/tests/` 하위 파일에 대한 Developer의 쓰기 차단 (`guard_test_files.py`)
* [x] `PreToolUse` Hook — `plan.md`의 수정 허용 파일 목록 밖 쓰기 차단 (`guard_plan_scope.py`)
* [x] `Stop` Hook — 종료 선언과 산출물의 모순 대조 (`guard_stop_gate.py`, §25)
* [x] `/patchpilot` 커맨드 — Orchestrator 실행 절차의 고정
* [x] `sample-project/` 및 `tasks/BUG-XXX.md` 구성
* [x] Harness Audit — 저장소 정지 상태 구조 계약의 결정론적 채점 (`evals/`, §26)
* [x] `/patchpilot-audit` 커맨드 — Audit 실행 wrapper (재채점하지 않음, §26)
* [x] Dashboard 구조 검증 표시 — Audit 결과와 Eval 결과를 분리해 시각화 (`dashboard/`)
* [ ] `PreToolUse` Hook — `reports/<run-id>/` 쓰기 주체 제한 (state.json / report.md는 Orchestrator만)
* [ ] CI 워크플로 — 단위 테스트 / selftest / audit 세 검증기를 모두 실행 (Audit check G1)
* [ ] 종료 경로 7개 전부에 대한 결정론적 Eval (Audit check E4b)

Hook이 담당하지 않는 제약은 도구 권한(`tools:`)과 각 Agent의 금지 사항으로 통제합니다.
Hook 판정 로직은 `evals/tests/` 에서 단위 검증되며, 판정을 건너뛰어야 할 때는
`PATCHPILOT_DISABLED_HOOKS` 환경변수에 Hook ID를 넣습니다.

---

## 23. Git 커밋 컨벤션

커밋 메시지는 다음 형식을 사용한다.

```text
<타입>: <한국어 작업 요약>
```

### 타입

- feat: 새로운 기능 추가
- fix: 버그 수정
- refactor: 기능 변경 없는 코드 구조 개선
- test: 테스트 추가 또는 수정
- docs: 문서 수정
- chore: 설정, 환경 구성, 기타 작업
- style: 코드 동작과 무관한 스타일 수정
- perf: 성능 개선

### 작성 규칙

- 타입은 영문 Conventional Commit 형식을 유지한다.
- 타입 뒤 설명은 한국어로 작성한다.
- 한 커밋에는 하나의 목적만 담는다.
- "수정", "작업"처럼 모호한 표현만 사용하지 않는다.
- 무엇을 왜 변경했는지 알 수 있게 작성한다.
- 마침표는 붙이지 않는다.

### 좋은 예

feat: Planner Agent 작업 계획 기능 추가

feat: PatchPilot Agent 기본 구조 구성

fix: 정산 금액 분배 시 나머지 금액 유실 문제 수정

test: 정산 금액 합계 보존 회귀 테스트 추가

docs: Harness 실행 구조 README에 추가

refactor: Agent 결과 파일 생성 로직 분리

chore: pytest 실행 환경 설정

### 좋지 않은 예

수정

작업함

feat: 기능 추가

fix: 버그 수정

update files

### 커밋 메시지 제안 규칙

Orchestrator와 모든 Agent는 커밋 메시지를 제안하거나 작성할 때 항상 이 규칙을 따라 한국어로 작성합니다.

`report.md`에 작업 결과를 요약하면서 커밋 메시지를 제안하는 경우에도 동일한 규칙을 적용합니다.

여러 목적이 섞인 변경이라면 하나의 메시지로 합치지 말고 목적별로 나누어 제안합니다.

---

## 24. Python 실행 환경

PatchPilot의 Python 환경은 `uv`로 관리합니다.

### 의존성 관리

* 패키지와 개발 의존성은 `pyproject.toml`과 `uv.lock`으로 관리합니다.
* `requirements.txt` 방식은 사용하지 않습니다.
* `.venv`는 uv가 관리하는 로컬 가상환경이며 Git에 커밋하지 않습니다.
* 의존성을 추가해야 하는 경우 다음 명령을 사용합니다.

```bash
uv add <패키지>
uv add --dev <패키지>
```

단, 의존성 추가는 §3-7에 따라 명시적으로 필요한 경우에만 수행합니다.

### 실행 규칙

* 테스트와 스크립트는 항상 `uv run`을 통해 실행합니다.
* 사용자가 수동으로 `.venv`를 활성화하는 것을 전제로 하지 않습니다.
* `uv run`은 필요한 경우 잠금 파일 기준으로 환경을 자동 동기화하므로 별도의 설치 단계를 가정하지 않습니다.

다음 방식은 사용하지 않습니다.

```text
python -m pytest ...
pip install ...
source .venv/bin/activate
.venv\Scripts\activate
```

### Agent별 주의사항

* Developer는 의존성을 임의로 추가하지 않습니다. 필요하다고 판단되면 `change-log-N.md`에 사유만 기록하고 중단합니다. (§3-7)
* Tester는 §10의 고정 명령어 외의 방식으로 테스트를 실행하지 않습니다.
* `uv` 실행 자체가 실패하거나 환경 동기화가 불가능한 경우, 제품 코드 결함이 아니라 `ENVIRONMENT_ERROR`로 분류합니다. (§14, §20)

---

## 25. Stop Gate

`Stop` Hook(`.claude/hooks/guard_stop_gate.py`)은 Orchestrator가 종료 상태를 선언한 시점에
`state.json`과 `reports/<run-id>/` 실제 산출물의 **결정론적 모순**만 대조합니다.

### 역할

Stop Gate는 종료를 강제하는 장치가 아니라 **Final Consistency Guard**입니다.
모순이 확인되면 해당 user prompt에서 정확히 한 번 종료를 막고 위반 목록을 전달합니다.
결론(`SUCCESS` / `BLOCKED`)을 대신 내리지 않습니다. 판정 권한은 §19대로 Orchestrator에게 있습니다.

### 실행 귀속

`state.json`의 `session_id`와 Stop payload의 `session_id`가 문자열 완전 일치하는 실행
하나만 검사합니다. 이 값은 Orchestrator가 `patchpilot.md §1-3`에서
`printenv CLAUDE_CODE_SESSION_ID`로 읽어 `§1-5`에서 한 번만 기록하며, 이후 덮어쓰지 않습니다.
서브에이전트는 자기 세션 식별자를 가지므로 이 값을 기록해서는 안 됩니다.

### prompt당 최대 1회 차단

Stop Hook은 차단 이후 이어진 턴이 끝날 때 `stop_hook_active = true`로 다시 호출됩니다.
Gate는 그 재진입 호출을 무조건 통과시킵니다. 이 분기가 무한 루프를 막는 필수 제어 흐름이며,
제거하면 `Stop → block → Stop` 이 반복됩니다.

따라서 교정 기회는 **차단 직후 한 턴뿐**입니다. 그 턴에서 다음을 지킵니다.

1. 사실과 다른 값을 맞추려고 `state.json` / `report.md`를 고치지 않습니다.
2. 누락된 단계가 있으면 그 단계를 수행합니다.
3. 교정이 불가능하면 §19 규칙으로 최종 상태를 다시 판정합니다.
4. 사용자 보고에 Stop Gate가 발견한 불일치를 포함합니다.

### 검사하지 않는 것

산출물만으로 정확히 판정할 수 없어 오탐 위험이 있는 항목은 검사하지 않습니다.
`attempts` 길이와 파일 개수 비교, `failure_category` 재파싱, `attempts` 기반 `retry_count`
재계산, git 상태, 계획 범위와 실제 diff 대조가 여기에 해당합니다.
이 중 일부는 `evals/eval_harness.py`가 이미 검증합니다.

### UI 표시

Claude Code는 정책적 차단도 `"Stop hook error occurred · ctrl+o to see"`로 표시합니다.
Hook 실행 오류와 같은 문구이므로, 이 메시지만으로 Hook 고장을 판단하지 않습니다.

### 비활성화

다른 Hook과 같은 스위치를 씁니다.

```bash
PATCHPILOT_DISABLED_HOOKS=guard-stop-gate
```

---

## 26. Harness Audit

`evals/harness_audit.py` 는 저장소가 선언한 통제 계약이 **실제로 갖춰져 있고 서로 모순되지 않는지** 결정론적으로 채점합니다.

### 검사 대상 — 정지 상태 구조 계약

Audit은 Agent의 실시간 행위를 검사하지 않습니다. 저장소 파일만 읽어 채점하며, `uv run pytest` 도 `eval_harness.py selftest` 도 실행하지 않습니다.

세 검증 층의 분업은 다음과 같습니다.

| 층 | 검사 대상 | 담당 |
| --- | --- | --- |
| `PreToolUse` / `Stop` Hook | Agent의 **실시간 행위** | `.claude/hooks/` |
| Harness Eval | Harness의 **실행 결과 상태 전이** | `evals/eval_harness.py` |
| Harness Audit | 저장소의 **정지 상태 구조 계약** | `evals/harness_audit.py` |

따라서 **Audit이 PASS라는 것은 Harness가 실제로 동작한다는 증명이 아닙니다.** 계약이 정합적이라는 증거이며, 실제 동작 검증은 Eval의 담당입니다. 두 결과의 수치는 검사 대상이 다르므로 합산하지 않습니다.

### 채점 구조

7개 Category · 33개 check · 100점입니다.

| Category | 배점 | 검사하는 것 |
| --- | --- | --- |
| A. Agent Role Isolation | 13 | Agent 정의와 최소 권한 행렬의 일치 (§11) |
| B. Guard Registration & Enforcement | 20 | Guard 파일과 `settings.json` 등록의 양방향 일치 (§22) |
| C. Control Contract Consistency | 19 | 분류·사유 코드·고정 명령·예산이 여러 소스에서 동일한가 (§10, §14, §16, §19, §20) |
| D. Artifact & Evidence Contract | 13 | 보존된 대표 결과의 스키마와 Stop Gate 불변식 replay (§12, §25) |
| E. Eval Coverage & Replay | 17 | 시나리오·fixture·결함 모듈·종료 경로 커버리지 |
| F. Documentation Consistency | 10 | 문서의 주장이 구현과 일치하는가 |
| G. Reproducibility & Automation | 8 | CI · 환경 고정 · Audit 자기 무결성 |

모든 check는 **이진 판정**입니다. PASS면 만점, FAIL이면 0점이며 부분 점수를 두지 않습니다. 부분 점수를 허용하는 순간 "기계적으로 증명 가능한 사실 하나"라는 기준이 무너집니다.

### Critical Hard Gate

기준선은 하나입니다.

> **거짓말이면 Critical, 미완성이면 감점.**

Guard가 등록되지 않았는데 문서가 등록됐다고 말하면 그것은 거짓말입니다. 종료 경로 eval이 7개 중 4개뿐인 것은 미완성입니다. 앞은 게이트, 뒤는 감점입니다.

Critical check는 7개이며 5개 게이트 이름으로 묶입니다.

| Gate | check |
| --- | --- |
| `ROLE_PRIVILEGE_DRIFT` | A3 |
| `GUARD_NOT_ENFORCED` | B3 |
| `STOP_GATE_SHAPE_INVALID` | B4 |
| `CONTRACT_DIVERGENCE` | C1 · C2 |
| `EVIDENCE_INVALID` | D3 · D4 |

### score와 verdict는 별개

`verdict` 는 **Critical 실패의 존재 여부만으로** 결정됩니다. 점수는 verdict를 바꾸지 않습니다.

* Critical 0건 → `PASS` (점수가 낮아도 PASS)
* Critical 1건 이상 → `FAIL` (점수가 높아도 FAIL)

CLI의 `--min-score N` 은 호출자가 별도로 거는 임계값입니다. 미달이면 `verdict` 를 `FAIL` 로 내리고 종료 코드 1을 반환하지만, **`critical_failures` 배열은 건드리지 않습니다.** 임계값 미달을 게이트 위반으로 위장하면 위 기준선이 오염됩니다.

### 버전 계약

세 값은 바뀌는 이유와 소비자가 다르므로 따로 둡니다.

| 값 | 현재 | 의미 | 소비자 |
| --- | --- | --- | --- |
| `schema_version` | 1 | JSON 봉투 구조 | Dashboard / CI 파서 |
| `rubric_version` | 1.0.0 | 채점 계약 (check id · 배점 · Critical 여부) | 점수 비교 |
| `audit_version` | 1.0.0 | 구현 | 재현 추적 |

**점수는 같은 `rubric_version` 안에서만 비교할 수 있습니다.** 배점이나 Critical 목록이 달라진 두 점수를 나란히 놓는 것은 의미가 없습니다.

`rubric_digest` 는 `sorted((check_id, max_score, is_critical))` 의 sha256입니다. 선언 순서를 바꿔도 값이 변하지 않고, 배점이나 Critical 여부를 바꾸면 변합니다. 이 값이 코드에 핀으로 박힌 값과 다르면 G3가 Audit 자기 자신을 FAIL시킵니다. rubric을 고쳤다면 `RUBRIC_VERSION` 과 `RUBRIC_DIGEST` 를 함께 갱신합니다.

### 판단 불가 시의 기본값 — Guard와 정반대

`_guard_common.py` 는 "판단할 수 없으면 통과시킨다"를 명시합니다. Audit은 반대입니다.

|  | Guard | Audit |
| --- | --- | --- |
| 실행 위치 | 실시간 도구 호출 경로 | 오프라인 |
| 오탐 비용 | 정상 실행이 죽는다 | 없다 |
| 미탐 비용 | 위반 1회 누락 | **감사 도구 자체의 신뢰 상실** |

단, 두 가지를 구분합니다.

* 기대한 파일이 **없다** → 그 check만 FAIL. 근거를 evidence에 남깁니다.
* 파일이 있는데 **읽거나 파싱할 수 없다** → `AuditError`. 검사 결과가 아니라 검사 자체를 수행하지 못한 것입니다.

"검사 결과 FAIL"과 "검사를 못 했음"을 섞으면 CI가 Audit 고장을 통과로 오독합니다.

### 종료 코드 계약

```text
0  Audit PASS
1  Audit FAIL (Critical 존재, 또는 --min-score 미달)
2  Audit 을 수행하지 못함 (AuditError / 인자 오류 / 쓰기 실패)
```

`1` 과 `2` 를 섞지 않습니다. 예상하지 못한 예외까지 `2` 로 처리하는 이유는, 예외가 그대로 새어 나가면 Python 기본 종료 코드가 `1` 이 되어 **도구 고장이 정상적인 FAIL로 보이기** 때문입니다.

### 대표 결과 보존 정책

```bash
uv run python evals/harness_audit.py --write
```

이 명령만 `reports/audit/latest.json` 과 `reports/audit/latest.md` 를 갱신합니다. `--write` 없이 실행하면 파일을 하나도 만들지 않습니다.

* 보존하는 것은 `latest` 두 파일**뿐**입니다. 날짜별 파일이나 `history/` · `archive/` 를 만들지 않습니다. 이력은 git이 이미 가지고 있고, 파일을 쌓으면 "어느 것이 현재인가"라는 질문이 새로 생깁니다.
* 두 파일은 `.gitignore` 의 `reports/*` 규칙에서 예외로 추적됩니다. `reports/<run-id>/` 실행 산출물은 그대로 무시됩니다.
* 한 파일만 쓰이고 다른 파일이 실패한 상태로 성공 처리하지 않습니다. 쓰기 실패는 종료 코드 `2` 입니다.

### `/patchpilot-audit`

결정론 Python Audit의 **얇은 wrapper**입니다. Claude가 점수를 다시 계산하지 않습니다.

1. `evals/harness_audit.py` 를 실행하고 출력을 그대로 보고합니다.
2. 재채점·보정·등급 부여를 하지 않습니다.
3. FAIL한 check를 자동으로 수정하지 않습니다. `next_actions` 는 사람에게 보고할 제안이지 실행할 작업 목록이 아닙니다.
4. Critical을 항상 먼저 표시합니다.
5. 기본은 읽기 전용입니다. `--write` 는 사람이 명시적으로 지정할 때만 실행됩니다.
6. 점수가 낮다고 rubric을 조정하지 않습니다.
