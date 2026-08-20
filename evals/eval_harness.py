"""PatchPilot Harness 재시도 루프를 결정론적으로 검증하는 eval 실행 도구.

이 도구는 Agent를 대신 실행하지 않는다. Agent 실행은 Orchestrator(메인 Claude Code 세션)가
`evals/README.md` 의 절차대로 수행하고, 이 도구는 그 앞뒤에서 다음 네 가지만 담당한다.

1. setup    - eval 전용 결함 모듈과 테스트를 `sample-project/` 에 설치하고 원상태를 스냅샷한다.
2. inject   - Developer 1차 수정 직후 제품 코드에 결함을 주입하고 근거를 파일로 남긴다.
3. assert   - `reports/<run-id>/` 산출물만 근거로 상태 전이를 자동 판정한다.
4. teardown - 설치한 파일을 제거하고 `sample-project/` 가 원상태로 복구됐는지 확인한다.

검증 대상 전이는 시나리오(`--scenario`)마다 다르다.

`harness-eval-001` (PRODUCT_CODE_DEFECT 재시도 루프, 기본값):

    Planner -> Developer 1차 -> Fault Injection -> Tester FAIL
    -> PRODUCT_CODE_DEFECT -> retry_count = 1 -> Developer 2차
    -> Tester PASS -> Reviewer APPROVED -> SUCCESS

`harness-eval-002` (PLAN_DEFECT 재계획 라우팅):

    Planner 1차 -> Developer 1차 -> Fault Injection(계획 범위 밖) -> Tester FAIL
    -> PLAN_DEFECT -> retry_count = 1 -> Planner 2차(plan.md 갱신) -> Developer 2차
    -> Tester PASS -> Reviewer APPROVED -> SUCCESS

`harness-eval-003` (ENVIRONMENT_ERROR 즉시 종료 라우팅):

    Planner -> Developer 1차 -> Fault Injection(런타임 리소스 삭제) -> Tester FAIL
    -> ENVIRONMENT_ERROR -> 재시도 예산 미소비(retry_count = 0)
    -> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출 -> BLOCKED

`harness-eval-004` (RETRY_BUDGET_EXCEEDED 예산 소진 종료):

    Planner -> Developer 1차 -> Fault Injection(결함 B) -> Tester FAIL
    -> PRODUCT_CODE_DEFECT -> retry_count = 1 -> Developer 2차(B 제거)
    -> Fault Injection(결함 C) -> Tester FAIL -> PRODUCT_CODE_DEFECT -> retry_count = 2
    -> Developer 3차(C 제거) -> Fault Injection(결함 D) -> Tester FAIL
    -> PRODUCT_CODE_DEFECT -> retry_count = 3 = retry_budget
    -> Developer 4차 / Tester 4차 / Reviewer 미호출 -> BLOCKED

네 시나리오는 setup/inject/assert/teardown 골격을 공유하고, 달라지는 값만 `Scenario` 에 모은다.

사용법은 `evals/README.md` 를 따른다.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
FIXTURES_DIR = EVALS_DIR / "fixtures"
FAULTS_DIR = EVALS_DIR / "faults"
STATE_DIR = EVALS_DIR / ".eval-run"
STATE_FILE = STATE_DIR / "state.json"
REPORTS_DIR = ROOT / "reports"
EXAMPLES_DIR = REPORTS_DIR / "examples"

FAILURE_CATEGORIES = {
    "PRODUCT_CODE_DEFECT",
    "TEST_DEFECT",
    "PLAN_DEFECT",
    "ENVIRONMENT_ERROR",
    "UNKNOWN",
}

# 대표 결과로 승격할 때 반드시 존재해야 하는 산출물.
PROMOTED_FILES = [
    "fault-injection.md",
    "change-log-1.md",
    "test-result-1.md",
    "change-log-2.md",
    "test-result-2.md",
    "review.md",
    "report.md",
    "state.json",
]

# 재시도 없이 즉시 종료되는 시나리오의 승격 대상.
# Developer 2차 이후 산출물은 존재하지 않는 것이 정상이므로 필수 목록에서 뺀다.
BLOCKED_PROMOTED_FILES = (
    "fault-injection.md",
    "change-log-1.md",
    "test-result-1.md",
    "report.md",
    "state.json",
)

# 재시도 예산을 모두 소비하고 종료되는 시나리오의 승격 대상.
# 시도 3회분 산출물은 모두 있어야 하고, Reviewer 산출물은 없는 것이 정상이다.
RETRY_EXHAUSTED_PROMOTED_FILES = (
    "fault-injection-1.md",
    "change-log-1.md",
    "test-result-1.md",
    "fault-injection-2.md",
    "change-log-2.md",
    "test-result-2.md",
    "fault-injection-3.md",
    "change-log-3.md",
    "test-result-3.md",
    "report.md",
    "state.json",
)

# 대표 결과에 함께 복사하면 좋지만 없어도 승격을 막지는 않는 산출물.
OPTIONAL_PROMOTED_FILES = ["plan.md", "eval-result.md"]

PYTEST_COMMAND = "uv run pytest sample-project/tests -q"

# 시나리오가 검증하는 종료 형태.
OUTCOME_SUCCESS_AFTER_RETRY = "SUCCESS_AFTER_RETRY"  # 재시도 후 SUCCESS 로 끝난다.
OUTCOME_BLOCKED = "BLOCKED"  # 재시도하지 않고 즉시 BLOCKED 로 끝난다.
OUTCOME_RETRY_EXHAUSTED = "BLOCKED_AFTER_RETRIES"  # 재시도 예산을 모두 쓰고 BLOCKED 로 끝난다.

# 결함 유형. 제품 코드에 문자열을 주입하는 방식과 설치된 리소스를 삭제하는 방식을 구분한다.
FAULT_KIND_CODE_INJECTION = "code_injection"
FAULT_KIND_RESOURCE_REMOVAL = "resource_removal"

# 결함 주입이 파일을 삭제할 수 있는 유일한 최상위 경로.
REMOVABLE_ROOT = "sample-project/"


@dataclass
class Check:
    """자동 검증 항목 하나의 판정 결과."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Scenario:
    """eval 시나리오 하나의 고정 정의.

    setup / inject / assert / teardown 골격은 모든 시나리오가 공유하고, 시나리오마다
    달라지는 값만 여기에 모은다. 새 시나리오를 추가할 때 `eval_harness.py` 의 절차 코드를
    고치지 않고 이 구조체 하나만 늘리는 것이 목적이다.
    """

    scenario_id: str
    # 이 시나리오가 사용하는 eval 전용 고정 Task.
    task: str
    # 기본 주입 결함. `inject --fault` 로 덮어쓸 수 있다.
    fault: str
    # eval 실행 중에만 sample-project에 설치되는 파일. (fixture 파일명, 설치 경로)
    installs: tuple[tuple[str, str], ...]
    # Tester 1차가 기록해야 하는 실패 원인 분류. (`CLAUDE.md §14`)
    expected_category: str
    # Tester 1차 결과에 반드시 남아 있어야 하는 실패 테스트 식별 문자열.
    expected_failing_token: str
    # `eval-result.md` 에 기록할 검증 대상 전이.
    transition: str
    # 검증 대상 종료 형태. 재시도 후 성공하거나, 즉시 종료하거나, 예산을 모두 쓰고 종료한다.
    outcome: str = OUTCOME_SUCCESS_AFTER_RETRY
    # Orchestrator가 `state.json` 에 기록해야 하는 재시도 횟수와 시도 기록 개수.
    expected_retry_count: int = 1
    expected_attempts: int = 2
    # 시도마다 순서대로 주입할 결함 목록. 비어 있으면 `fault` 하나만 1회 주입한다.
    # 같은 결함을 반복 주입하지 않으므로 항목은 서로 달라야 한다. (`evals/README.md §3-12`)
    fault_sequence: tuple[str, ...] = field(default_factory=tuple)
    # 시도마다 `test-result-N.md` 에 새로 나타나야 하는 실패 테스트 이름.
    # N번째 값은 N번째 시도에만 있어야 하고 그 이전 시도에는 없어야 한다.
    expected_failing_tokens: tuple[str, ...] = field(default_factory=tuple)
    # 예산 소진 시나리오에서 `state.json` 에 기록되어야 하는 재시도 예산. (`CLAUDE.md §16`)
    expected_retry_budget: int = 3
    # 즉시 종료 시나리오에서 기록되어야 하는 사유 코드. (`patchpilot.md §10`)
    expected_blocked_reason: str = ""
    # 즉시 종료 시나리오에서 존재하면 안 되는 산출물. (파일명, 호출되지 않아야 하는 주체)
    forbidden_artifacts: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # 실패 증상 기록 항목의 이름. 실패가 개별 테스트 실패가 아닌 시나리오에서 바꾼다.
    failing_token_check_name: str = "test-result-1.md 가 주입된 결함의 실패 테스트를 기록"
    # Planner 1차가 확정해야 하는 수정 허용 파일 목록. 비어 있으면 검사하지 않는다.
    expected_plan1_allowed: tuple[str, ...] = field(default_factory=tuple)
    # inject 시점에 `plan.md` 를 `plan-1.md` 로 복사해 Planner 1차 산출물을 고정할지 여부.
    snapshot_plan: bool = False
    # Planner 재호출(재계획) 전이를 검증할지 여부. `snapshot_plan` 을 전제로 한다.
    replan_checks: bool = False
    # 승격 시 반드시 있어야 하는 산출물. 비어 있으면 `PROMOTED_FILES` 를 쓴다.
    promoted_files: tuple[str, ...] = field(default_factory=tuple)
    # 이 시나리오에서 추가로 승격 대상이 되는 산출물.
    extra_promoted_files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def expected_final_status(self) -> str:
        """`state.json` 의 `final_status` 기대값. (`CLAUDE.md §19`)"""
        return "SUCCESS" if self.outcome == OUTCOME_SUCCESS_AFTER_RETRY else "BLOCKED"

    @property
    def fault_ids(self) -> tuple[str, ...]:
        """이 시나리오가 시도 순서대로 주입하는 결함 목록."""
        return self.fault_sequence or (self.fault,)

    @property
    def is_chained(self) -> bool:
        """시도마다 다른 결함을 연쇄로 주입하는 시나리오인지 여부."""
        return len(self.fault_ids) > 1

    def fault_report_name(self, attempt: int) -> str:
        """N번째 주입 기록 파일 이름.

        단일 주입 시나리오는 기존 이름(`fault-injection.md`)을 그대로 쓴다.
        """
        return f"fault-injection-{attempt}.md" if self.is_chained else "fault-injection.md"


SCENARIOS: dict[str, Scenario] = {
    "harness-eval-001": Scenario(
        scenario_id="harness-eval-001",
        task="evals/fixtures/HARNESS-EVAL-001.md",
        fault="retry_001",
        installs=(
            ("tip.py", "sample-project/src/expense/tip.py"),
            ("test_tip.py", "sample-project/tests/test_tip.py"),
        ),
        expected_category="PRODUCT_CODE_DEFECT",
        expected_failing_token="test_tip",
        transition=(
            "Planner -> Developer 1차 -> Fault Injection -> Tester FAIL -> PRODUCT_CODE_DEFECT\n"
            "-> retry_count = 1 -> Developer 2차 -> Tester PASS -> Reviewer APPROVED -> SUCCESS"
        ),
    ),
    "harness-eval-002": Scenario(
        scenario_id="harness-eval-002",
        task="evals/fixtures/HARNESS-EVAL-002.md",
        fault="plan_defect_001",
        installs=(
            ("charge_rounding.py", "sample-project/src/expense/charge_rounding.py"),
            ("service_charge.py", "sample-project/src/expense/service_charge.py"),
            ("test_charge_rounding.py", "sample-project/tests/test_charge_rounding.py"),
            ("test_service_charge.py", "sample-project/tests/test_service_charge.py"),
        ),
        expected_category="PLAN_DEFECT",
        expected_failing_token="test_charge_rounding",
        transition=(
            "Planner 1차 -> Developer 1차 -> Fault Injection(계획 범위 밖) -> Tester FAIL\n"
            "-> PLAN_DEFECT -> retry_count = 1 -> Planner 2차(plan.md 갱신) -> Developer 2차\n"
            "-> Tester PASS -> Reviewer APPROVED -> SUCCESS"
        ),
        expected_plan1_allowed=("sample-project/src/expense/service_charge.py",),
        snapshot_plan=True,
        replan_checks=True,
        extra_promoted_files=("plan-1.md", "plan-2.md"),
    ),
    "harness-eval-003": Scenario(
        scenario_id="harness-eval-003",
        task="evals/fixtures/HARNESS-EVAL-003.md",
        fault="env_error_001",
        # 제품 버그는 harness-eval-001 과 같은 것을 재사용한다. 이 시나리오가 바꾸는 변수는
        # 제품 버그가 아니라 결함의 종류(실행 환경 오류) 하나뿐이다.
        # 시나리오는 동시에 실행되지 않고, setup은 설치 대상이 이미 있으면 거부하므로
        # 설치 경로를 harness-eval-001 과 공유해도 서로 간섭하지 않는다.
        installs=(
            ("tip.py", "sample-project/src/expense/tip.py"),
            ("test_tip.py", "sample-project/tests/test_tip.py"),
            ("conftest_settlement_runtime.py", "sample-project/tests/conftest.py"),
            ("settlement_runtime.json", "sample-project/config/settlement_runtime.json"),
        ),
        expected_category="ENVIRONMENT_ERROR",
        expected_failing_token="settlement_runtime.json",
        transition=(
            "Planner -> Developer 1차 -> Fault Injection(런타임 리소스 삭제) -> Tester FAIL\n"
            "-> ENVIRONMENT_ERROR -> 재시도 예산 미소비(retry_count = 0)\n"
            "-> Planner 2차 / Developer 2차 / Tester 2차 / Reviewer 미호출 -> BLOCKED"
        ),
        outcome=OUTCOME_BLOCKED,
        expected_retry_count=0,
        expected_attempts=1,
        expected_blocked_reason="ENVIRONMENT_ERROR",
        forbidden_artifacts=(
            ("change-log-2.md", "Developer 2차"),
            ("test-result-2.md", "Tester 2차"),
            ("review.md", "Reviewer"),
        ),
        failing_token_check_name="test-result-1.md 가 주입된 실행 환경 오류 증상을 기록",
        # Planner 2차가 호출되지 않았다는 것을 plan.md 해시 비교로 판정하기 위해 스냅샷만 남긴다.
        snapshot_plan=True,
        promoted_files=BLOCKED_PROMOTED_FILES,
        extra_promoted_files=("plan-1.md",),
    ),
    "harness-eval-004": Scenario(
        scenario_id="harness-eval-004",
        task="evals/fixtures/HARNESS-EVAL-004.md",
        # 시도마다 다른 결함을 주입한다. `fault` 는 1차 결함이고 나머지는 `fault_sequence` 에 있다.
        fault="retry_budget_001",
        installs=(
            ("installment.py", "sample-project/src/expense/installment.py"),
            ("test_installment.py", "sample-project/tests/test_installment.py"),
        ),
        expected_category="PRODUCT_CODE_DEFECT",
        expected_failing_token="test_installment",
        transition=(
            "Planner -> Developer 1차 -> Fault Injection(결함 B) -> Tester FAIL\n"
            "-> PRODUCT_CODE_DEFECT -> retry_count = 1 -> Developer 2차(B 제거)\n"
            "-> Fault Injection(결함 C) -> Tester FAIL -> PRODUCT_CODE_DEFECT -> retry_count = 2\n"
            "-> Developer 3차(C 제거) -> Fault Injection(결함 D) -> Tester FAIL\n"
            "-> PRODUCT_CODE_DEFECT -> retry_count = 3 = retry_budget\n"
            "-> Developer 4차 / Tester 4차 / Reviewer 미호출 -> BLOCKED"
        ),
        outcome=OUTCOME_RETRY_EXHAUSTED,
        expected_retry_count=3,
        expected_attempts=3,
        fault_sequence=("retry_budget_001", "retry_budget_002", "retry_budget_003"),
        expected_failing_tokens=(
            "test_split_installments_distributes_remainder_to_earlier_months_first",
            "test_split_installments_difference_between_installments_is_at_most_one_won",
            "test_split_installments_preserves_total_when_total_is_not_evenly_divisible",
        ),
        expected_retry_budget=3,
        expected_blocked_reason="RETRY_BUDGET_EXCEEDED",
        forbidden_artifacts=(
            ("change-log-4.md", "Developer 4차"),
            ("test-result-4.md", "Tester 4차"),
            ("fault-injection-4.md", "4차 결함 주입"),
            ("review.md", "Reviewer"),
        ),
        # Planner 재호출 판정용 기준선. `PRODUCT_CODE_DEFECT` 경로는 Planner를 부르지 않는다.
        snapshot_plan=True,
        promoted_files=RETRY_EXHAUSTED_PROMOTED_FILES,
        extra_promoted_files=("plan-1.md",),
    ),
}

DEFAULT_SCENARIO = "harness-eval-001"

# Planner 1차 / 2차 산출물 스냅샷 파일 이름.
# Planner는 운영과 동일하게 `plan.md` 하나만 쓰고, 스냅샷 복사는 Harness가 한다.
PLAN_SNAPSHOT_1 = "plan-1.md"
PLAN_SNAPSHOT_2 = "plan-2.md"

# 보존된 대표 결과를 다시 읽는 `selftest` 에서는 실행 환경 의존 항목을 판정할 수 없다.
OFFLINE_SKIP_DETAIL = "오프라인 replay 제외 (실행 환경 의존 항목)"

# plan / change-log 파서 검증에 쓰는 보존된 대표 결과.
PARSER_EXAMPLE = "EVAL-20260820-1318-HARNESS-EVAL-001"

# 리팩터링 이후에도 `harness-eval-001` 이 그대로 만들어 내야 하는 검증 항목 이름과 순서.
# 근거는 `reports/examples/EVAL-20260820-1318-HARNESS-EVAL-001/eval-result.md` 다.
GOLDEN_001_CHECK_NAMES = (
    "plan.md 존재",
    "change-log-1.md 존재",
    "fault-injection.md 존재",
    "결함 주입이 Developer 1차 이후에 이루어짐",
    "test-result-1.md 첫 줄이 STATUS: FAIL",
    "test-result-1.md 에 고정 실행 명령 기록",
    "test-result-1.md 가 주입된 결함의 실패 테스트를 기록",
    "실패 원인 분류가 PRODUCT_CODE_DEFECT",
    "change-log-2.md 존재",
    "change-log-2.md 가 test-result-1.md 를 근거로 참조",
    "test-result-2.md 첫 줄이 STATUS: PASS",
    "test-result-2.md 에 고정 실행 명령 기록",
    "review.md 첫 줄이 VERDICT: APPROVED",
    "state.json 존재",
    "state.json retry_count == 1",
    "state.json final_status == SUCCESS",
    "state.json current_stage == DONE",
    "state.json blocked_reason 없음",
    "state.json attempts 가 2회 기록",
    "attempts[0] 이 FAIL / PRODUCT_CODE_DEFECT",
    "attempts[1] 이 PASS",
    "주입된 결함이 Developer 2차에 의해 제거됨",
    "eval 테스트가 약화되지 않음",
    "기존 추적 파일이 변경되지 않음",
    "report.md 존재",
)

# 리팩터링 이후에도 `harness-eval-002` 가 그대로 만들어 내야 하는 검증 항목 이름과 순서.
# 근거는 `reports/examples/EVAL-20260820-1443-HARNESS-EVAL-002/eval-result.md` 다.
GOLDEN_002_CHECK_NAMES = (
    "plan.md 존재",
    "plan-1.md 스냅샷 존재",
    "change-log-1.md 존재",
    "fault-injection.md 존재",
    "결함 주입이 Developer 1차 이후에 이루어짐",
    "주입 대상이 plan 1차 수정 허용 파일 목록 밖",
    "plan 1차 수정 허용 파일 목록이 계획대로 한정됨",
    "test-result-1.md 첫 줄이 STATUS: FAIL",
    "test-result-1.md 에 고정 실행 명령 기록",
    "test-result-1.md 가 주입된 결함의 실패 테스트를 기록",
    "실패 원인 분류가 PLAN_DEFECT",
    "plan-2.md 스냅샷 존재",
    "plan 1차와 2차의 내용이 실제로 다름",
    "plan 2차가 1차 허용 목록을 유지하며 주입 대상 파일을 추가",
    "plan 2차가 test-result-1.md 를 재계획 근거로 참조",
    "plan 1차와 2차의 예상 원인이 다름",
    "change-log-2.md 존재",
    "change-log-2.md 가 test-result-1.md 를 근거로 참조",
    "change-log-2.md 의 변경 파일에 주입 대상 파일 포함",
    "test-result-2.md 첫 줄이 STATUS: PASS",
    "test-result-2.md 에 고정 실행 명령 기록",
    "review.md 첫 줄이 VERDICT: APPROVED",
    "state.json 존재",
    "state.json retry_count == 1",
    "state.json final_status == SUCCESS",
    "state.json current_stage == DONE",
    "state.json blocked_reason 없음",
    "state.json attempts 가 2회 기록",
    "attempts[0] 이 FAIL / PLAN_DEFECT",
    "attempts[1] 이 PASS",
    "주입된 결함이 Developer 2차에 의해 제거됨",
    "Developer 변경 파일이 plan 2차 수정 허용 목록 안에 있음",
    "eval 테스트가 약화되지 않음",
    "기존 추적 파일이 변경되지 않음",
    "report.md 존재",
)

# `selftest` 가 회귀 기준으로 삼는 (시나리오, 보존된 대표 결과, 골든 목록).
# 새 시나리오는 대표 결과를 승격한 뒤에 여기에 추가한다.
REGRESSION_EXAMPLES = (
    ("harness-eval-001", "EVAL-20260820-1318-HARNESS-EVAL-001", GOLDEN_001_CHECK_NAMES),
    ("harness-eval-002", "EVAL-20260820-1443-HARNESS-EVAL-002", GOLDEN_002_CHECK_NAMES),
)


class EvalError(Exception):
    """eval 진행을 계속할 수 없는 상황."""


# ---------------------------------------------------------------------------
# 공용 helper
# ---------------------------------------------------------------------------


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise EvalError(f"git {' '.join(args)} 실패: {completed.stderr.strip()}")
    return completed.stdout


def sample_project_status() -> list[str]:
    """sample-project 하위의 git 변경 상태를 정렬된 줄 목록으로 반환한다."""
    output = run_git("status", "--porcelain", "--", "sample-project")
    return sorted(line for line in output.splitlines() if line.strip())


def pytest_baseline() -> dict:
    """고정 명령으로 전체 테스트를 실행하고 요약 줄과 종료 코드를 반환한다.

    eval fixture를 설치하기 전과 teardown 이후를 비교해, 실행이 끝난 뒤 `sample-project` 가
    코드 상태뿐 아니라 **테스트 결과까지** 원래대로 돌아왔는지 확인하기 위한 기준선이다.
    PASS/FAIL 판정 권한을 가진 Tester의 실행(`CLAUDE.md §10`)과는 목적이 다르다.
    """
    completed = subprocess.run(
        PYTEST_COMMAND.split(),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "summary": _pytest_summary_line(completed.stdout),
        "returncode": completed.returncode,
    }


def _pytest_summary_line(output: str) -> str:
    """pytest 출력의 마지막 요약 줄에서 실행 시간을 뺀 부분을 반환한다.

    실행 시간은 실행할 때마다 달라지므로 비교 대상에서 제외한다. (`57 passed in 0.06s` -> `57 passed`)
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    return re.sub(r"\s+in\s+[\d.]+s.*$", "", lines[-1])


def is_tracked(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        raise EvalError(
            "eval 실행 상태 파일이 없습니다: evals/.eval-run/state.json\n"
            "먼저 `uv run python evals/eval_harness.py setup` 을 실행하세요."
        )
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_fault(fault_id: str):
    fault_path = FAULTS_DIR / f"{fault_id}.py"
    if not fault_path.exists():
        raise EvalError(f"결함 정의 파일이 없습니다: evals/faults/{fault_id}.py")

    spec = importlib.util.spec_from_file_location(f"patchpilot_eval_fault_{fault_id}", fault_path)
    if spec is None or spec.loader is None:
        raise EvalError(f"결함 정의를 불러오지 못했습니다: evals/faults/{fault_id}.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fault_kind_of(fault) -> str:
    """결함 정의의 유형을 해석한다.

    유형을 명시하지 않은 기존 결함 정의는 제품 코드 주입으로 본다.
    """
    return getattr(fault, "FAULT_KIND", FAULT_KIND_CODE_INJECTION)


def resolve_scenario(scenario_id: str | None) -> Scenario:
    """시나리오 식별자를 `Scenario` 로 해석한다. 생략 시 기본 시나리오를 쓴다."""
    resolved = scenario_id or DEFAULT_SCENARIO
    if resolved not in SCENARIOS:
        raise EvalError(
            f"정의되지 않은 시나리오입니다: {resolved} (사용 가능: {sorted(SCENARIOS)})"
        )
    return SCENARIOS[resolved]


def scenario_of_state(state: dict) -> Scenario:
    """실행 상태 파일에 기록된 시나리오를 해석한다.

    시나리오 개념이 없던 시절의 상태 파일에도 대응하기 위해 값이 없으면 기본 시나리오로 본다.
    """
    return resolve_scenario(state.get("scenario"))


def run_dir_of(run_id: str) -> Path:
    path = REPORTS_DIR / run_id
    if not path.is_dir():
        raise EvalError(f"실행 폴더가 없습니다: reports/{run_id}")
    return path


def read_run_file(run_dir: Path, name: str) -> str | None:
    path = run_dir / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def section_value(text: str, heading: str) -> str:
    """`## <heading>` 다음의 첫 비어 있지 않은 줄을 반환한다."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            for following in lines[index + 1 :]:
                if following.strip():
                    return following.strip()
            return ""
    return ""


def test_function_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("def test_") and "(" in stripped:
            names.add(stripped[len("def ") : stripped.index("(")])
    return names


def section_body(text: str, heading_keyword: str) -> str:
    """`heading_keyword` 를 포함하는 `##` 제목 아래 본문을 다음 제목 직전까지 반환한다.

    Agent가 쓰는 제목은 번호가 붙어 형태가 조금씩 달라지므로(`## 7. 수정 허용 파일 목록`)
    제목 전체 일치가 아니라 키워드 포함으로 찾는다.
    """
    lines = text.splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = heading_keyword in line
            continue
        if inside:
            collected.append(line)
    return "\n".join(collected)


def bullet_paths(body: str) -> list[str]:
    """본문의 목록 항목에서 백틱으로 감싼 `sample-project/` 경로를 순서대로 뽑는다.

    목록 항목만 본다. 같은 절의 산문에는 범위 밖 파일 이름이 근거로 함께 언급되는 경우가
    있어서(`plan.md` 의 "이 외의 파일은 수정하지 않는다") 산문까지 읽으면 허용 목록이
    실제보다 넓게 잡힌다.
    """
    paths: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        for match in re.findall(r"`([^`]+)`", stripped):
            candidate = match.strip()
            if candidate.startswith("sample-project/") and candidate not in paths:
                paths.append(candidate)
    return paths


def plan_allowed_files(plan_text: str) -> list[str]:
    """`plan.md` 의 수정 허용 파일 목록을 반환한다. (`CLAUDE.md §13`)"""
    return bullet_paths(section_body(plan_text, "수정 허용 파일 목록"))


def change_log_files(change_log_text: str) -> list[str]:
    """`change-log-N.md` 의 변경 파일 목록을 반환한다."""
    return bullet_paths(section_body(change_log_text, "변경 파일"))


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def _create_missing_parents(target: Path) -> list[str]:
    """설치 대상의 상위 디렉터리 중 이번 setup이 새로 만든 것만 생성하고 그 목록을 반환한다.

    teardown이 setup 이전 상태로 정확히 되돌리려면 새로 만든 디렉터리도 지워야 한다.
    `mkdir(parents=True, exist_ok=True)` 만 쓰면 원래 있던 디렉터리와 구분할 수 없다.
    """
    missing: list[Path] = []
    parent = target.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent

    created: list[str] = []
    for path in reversed(missing):
        path.mkdir()
        created.append(path.relative_to(ROOT).as_posix())
    return created


def cmd_setup(scenario_id: str | None, task: str | None) -> int:
    if STATE_FILE.exists():
        raise EvalError(
            "이전 eval 실행이 정리되지 않았습니다. "
            "`uv run python evals/eval_harness.py teardown` 을 먼저 실행하세요."
        )

    scenario = resolve_scenario(scenario_id)
    task = task or scenario.task

    if not (ROOT / task).is_file():
        raise EvalError(f"eval task 파일이 없습니다: {task}")

    snapshot = sample_project_status()
    # fixture를 설치하기 전에 기준선을 잡는다. teardown 이후 이 결과로 돌아와야 한다.
    baseline = pytest_baseline()

    installed: list[str] = []
    created_dirs: list[str] = []
    for fixture_name, install_target in scenario.installs:
        source = FIXTURES_DIR / fixture_name
        target = ROOT / install_target
        if not source.is_file():
            raise EvalError(f"fixture 파일이 없습니다: evals/fixtures/{fixture_name}")
        if target.exists():
            raise EvalError(
                f"설치 대상이 이미 존재합니다: {install_target}\n"
                "이전 실행이 정리되지 않았을 수 있습니다. 파일을 확인한 뒤 다시 실행하세요."
            )
        created_dirs.extend(_create_missing_parents(target))
        shutil.copyfile(source, target)
        installed.append(install_target)

    save_state(
        {
            "scenario": scenario.scenario_id,
            "task": task,
            "fault": None,
            "injections": [],
            "installed": installed,
            "created_dirs": created_dirs,
            "snapshot": snapshot,
            "pytest_baseline": baseline,
            "setup_at": now_text(),
        }
    )

    print("eval setup 완료")
    print(f"  시나리오: {scenario.scenario_id}")
    print(f"  task   : {task}")
    for install_target in installed:
        print(f"  설치   : {install_target}")
    for created in created_dirs:
        print(f"  생성   : {created}/ (teardown에서 제거)")
    print(f"  스냅샷 : sample-project 변경 {len(snapshot)}건")
    print(f"  기준선 : {baseline['summary']} (teardown 후 이 결과로 복귀해야 한다)")
    print()
    print("다음 단계는 evals/README.md 의 실행 절차를 따르세요.")
    return 0


# ---------------------------------------------------------------------------
# inject
# ---------------------------------------------------------------------------


def cmd_inject(run_id: str, fault_id: str | None, attempt: int | None) -> int:
    state = load_state()
    scenario = scenario_of_state(state)
    run_dir = run_dir_of(run_id)

    injections = list(state.get("injections") or [])
    attempt = _resolve_attempt(scenario, state, injections, attempt)
    fault = load_fault(fault_id or scenario.fault_ids[attempt - 1])

    plan_snapshot_note = ""
    if scenario.snapshot_plan and attempt == 1:
        # Planner 1차 산출물을 여기서 고정한다. 지금이 plan v1이 확정된 마지막 시점이다.
        # (Developer 1차는 끝났고 Planner 2차는 아직 호출되지 않았다.)
        plan_text = read_run_file(run_dir, "plan.md")
        if plan_text is None:
            raise EvalError(f"plan.md 가 없습니다: reports/{run_id}/plan.md")
        (run_dir / PLAN_SNAPSHOT_1).write_text(plan_text, encoding="utf-8")
        plan_snapshot_note = f"reports/{run_id}/{PLAN_SNAPSHOT_1}"

    previous = injections[-1] if injections else None
    evidence: dict = {}
    if scenario.is_chained:
        evidence = _guard_chained_injection(scenario, fault, run_dir, run_id, attempt, previous)

    if fault_kind_of(fault) == FAULT_KIND_RESOURCE_REMOVAL:
        record = _inject_resource_removal(fault, state, run_id)
        report = _resource_removal_report(fault, record)
    else:
        record = _inject_code_fault(fault, run_dir, run_id, attempt=attempt, evidence=evidence)
        report = _fault_injection_report(fault, record, scenario)

    injections.append(record)
    state["injections"] = injections
    # 단일 주입 시나리오의 기존 판정 경로가 그대로 읽을 수 있도록 최신 기록을 함께 둔다.
    state["fault"] = record
    save_state(state)
    report_name = scenario.fault_report_name(attempt)
    (run_dir / report_name).write_text(report, encoding="utf-8")

    print(f"결함 주입 완료: {fault.FAULT_ID} -> {fault.TARGET_PATH} (시도 {attempt})")
    print(f"기록 파일: reports/{run_id}/{report_name}")
    if evidence.get("previous_fault_id"):
        print(f"직전 결함 제거 확인: {evidence['previous_fault_id']} 표식 없음 / 파일 내용 변경됨")
    if plan_snapshot_note:
        print(f"Planner 1차 스냅샷: {plan_snapshot_note}")
    return 0


def _resolve_attempt(
    scenario: Scenario, state: dict, injections: list[dict], attempt: int | None
) -> int:
    """이번 주입이 몇 번째 시도인지 확정한다.

    연쇄 주입 시나리오에서는 `--attempt` 를 필수로 요구한다. 순서가 어긋난 실행이 조용히
    다른 결함을 주입해 검증 대상 전이가 바뀌는 것을 막기 위해서다.
    """
    next_attempt = len(injections) + 1

    if not scenario.is_chained:
        already = state.get("fault")
        if already or injections:
            record = already or injections[-1]
            raise EvalError(
                f"이미 결함이 주입되어 있습니다: {record['fault_id']} ({record['injected_at']})"
            )
        if attempt not in (None, 1):
            raise EvalError(
                f"{scenario.scenario_id} 는 결함을 1회만 주입합니다. (요청: --attempt {attempt})"
            )
        return 1

    if attempt is None:
        raise EvalError(
            f"{scenario.scenario_id} 는 시도마다 다른 결함을 주입합니다. "
            f"`--attempt {next_attempt}` 를 지정하세요."
        )
    if attempt != next_attempt:
        raise EvalError(
            f"주입 순서가 맞지 않습니다. 다음 차례는 {next_attempt}차인데 {attempt}차가 "
            f"요청되었습니다. (지금까지 주입: {[item['fault_id'] for item in injections]})"
        )
    if attempt > len(scenario.fault_ids):
        raise EvalError(
            f"{scenario.scenario_id} 에 정의된 결함은 {len(scenario.fault_ids)}개입니다. "
            f"{attempt}차 주입은 정의되어 있지 않습니다."
        )
    return attempt


def _guard_chained_injection(
    scenario: Scenario,
    fault,
    run_dir: Path,
    run_id: str,
    attempt: int,
    previous: dict | None,
) -> dict:
    """다음 결함을 주입해도 되는지 확인하고, 확인 결과를 주입 기록용 dict로 반환한다.

    핵심은 **직전 결함이 Developer의 손으로 실제 제거되었는지** 다. 제거되지 않았는데 다음
    결함을 얹으면 Developer가 아무것도 고치지 못해도 매번 FAIL이 나므로, eval이 조용히
    통과한다. 전제가 깨지면 주입하지 않고 즉시 실패시킨다. (`evals/README.md §3-13`)
    """
    change_log = read_run_file(run_dir, f"change-log-{attempt}.md")
    if change_log is None:
        raise EvalError(
            f"{fault.FAULT_ID} 주입 전제 조건 위반: reports/{run_id}/change-log-{attempt}.md 가 "
            f"없습니다. Developer {attempt}차가 끝난 뒤에 주입해야 합니다."
        )
    if attempt >= 2 and f"test-result-{attempt - 1}" not in change_log:
        raise EvalError(
            f"{fault.FAULT_ID} 주입 전제 조건 위반: change-log-{attempt}.md 가 "
            f"test-result-{attempt - 1}.md 를 근거로 참조하지 않았습니다. (`CLAUDE.md §16`)"
        )

    if previous is None:
        return {"attempt_change_log": f"change-log-{attempt}.md"}

    expected_previous = getattr(fault, "PREVIOUS_FAULT_ID", None)
    if expected_previous != previous["fault_id"]:
        raise EvalError(
            f"{fault.FAULT_ID} 결함 정의의 PREVIOUS_FAULT_ID({expected_previous!r}) 가 실제 직전 "
            f"주입 결함({previous['fault_id']!r})과 다릅니다."
        )

    previous_fault = load_fault(previous["fault_id"])
    target = ROOT / previous["target"]
    if not target.is_file():
        raise EvalError(f"결함 주입 대상 파일이 없습니다: {previous['target']}")

    source = target.read_text(encoding="utf-8")
    if previous_fault.is_applied(source):
        raise EvalError(
            f"{fault.FAULT_ID} 주입 전제 조건 위반: Developer {attempt}차가 직전 결함 "
            f"{previous['fault_id']} 을(를) 제거하지 않았습니다. "
            f"({previous['target']} 에 '{previous['marker']}' 표식이 남아 있습니다)"
        )

    current_sha = sha256_of(source)
    if current_sha == previous["after_sha256"]:
        raise EvalError(
            f"{fault.FAULT_ID} 주입 전제 조건 위반: {previous['target']} 의 내용이 직전 결함 주입 "
            f"직후와 동일합니다. Developer {attempt}차가 제품 코드를 바꾸지 않았습니다."
        )

    return {
        "attempt_change_log": f"change-log-{attempt}.md",
        "previous_fault_id": previous["fault_id"],
        "previous_marker": previous["marker"],
        "previous_after_sha256": previous["after_sha256"],
        "previous_marker_removed": True,
        "previous_removed_sha256": current_sha,
        "previous_removed_confirmed_at": now_text(),
    }


def _inject_code_fault(
    fault, run_dir: Path, run_id: str, *, attempt: int = 1, evidence: dict | None = None
) -> dict:
    """제품 코드에 결함 코드를 덧붙이고 주입 기록을 반환한다."""
    target = ROOT / fault.TARGET_PATH
    if not target.is_file():
        raise EvalError(f"결함 주입 대상 파일이 없습니다: {fault.TARGET_PATH}")

    # 결함 정의가 계획 범위에 대한 전제 조건을 갖고 있으면 주입 전에 검사한다.
    # 전제가 깨지면 주입하지 않고 실패시켜 eval이 조용히 통과하는 일을 막는다.
    precheck = getattr(fault, "precheck", None)
    if precheck is not None:
        plan_text = read_run_file(run_dir, PLAN_SNAPSHOT_1) or read_run_file(run_dir, "plan.md")
        if plan_text is None:
            raise EvalError(f"plan.md 가 없습니다: reports/{run_id}/plan.md")
        try:
            precheck(plan_allowed_files(plan_text))
        except ValueError as error:
            raise EvalError(str(error)) from error

    before = target.read_text(encoding="utf-8")
    try:
        after = fault.apply(before)
    except ValueError as error:
        raise EvalError(str(error)) from error
    target.write_text(after, encoding="utf-8")

    return {
        "fault_id": fault.FAULT_ID,
        "run_id": run_id,
        "kind": FAULT_KIND_CODE_INJECTION,
        "attempt": attempt,
        "target": fault.TARGET_PATH,
        "marker": fault.MARKER,
        "before_sha256": sha256_of(before),
        "after_sha256": sha256_of(after),
        "injected_at": now_text(),
        **(evidence or {}),
    }


def _inject_resource_removal(fault, state: dict, run_id: str) -> dict:
    """이번 eval이 설치한 런타임 리소스를 삭제하고 주입 기록을 반환한다.

    삭제는 되돌릴 수 없으므로 결함 정의의 `precheck_fs` 와 Harness의
    `_guard_resource_removal` 이 같은 조건을 각각 검사한 뒤에만 수행한다. 결함 정의가 잘못
    작성되더라도 사용자의 실제 파일이 지워지지 않도록 두 곳에서 함께 막는 것이 목적이다.
    """
    target_path = fault.TARGET_PATH
    target = _resolve_removable_target(target_path)
    content = target.read_text(encoding="utf-8") if target.is_file() else None

    context = {
        "target": target_path,
        "installed": tuple(state.get("installed") or ()),
        "tracked": is_tracked(target) if target.exists() else False,
        "exists": target.is_file(),
        "content": content,
    }
    _guard_resource_removal(context)

    precheck_fs = getattr(fault, "precheck_fs", None)
    if not callable(precheck_fs):
        raise EvalError(
            f"{fault.FAULT_ID}: {FAULT_KIND_RESOURCE_REMOVAL} 결함에는 precheck_fs 가 필요합니다."
        )
    try:
        precheck_fs(context)
    except ValueError as error:
        raise EvalError(str(error)) from error

    target.unlink()

    return {
        "fault_id": fault.FAULT_ID,
        "run_id": run_id,
        "kind": FAULT_KIND_RESOURCE_REMOVAL,
        "attempt": 1,
        "target": target_path,
        "marker": fault.MARKER,
        "before_sha256": sha256_of(content or ""),
        "after_sha256": None,
        "removed": True,
        "injected_at": now_text(),
    }


def _resolve_removable_target(target_path: str) -> Path:
    """삭제 대상 경로를 저장소 안의 안전한 경로로만 해석한다.

    결함 정의도 저장소 안의 텍스트 파일이므로 경로 자체를 신뢰하지 않는다.
    `sample-project/` 밖, 절대 경로, 상위 경로 참조, 심볼릭 링크는 모두 거부한다.
    """
    candidate = Path(target_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise EvalError(f"삭제 대상 경로가 안전하지 않습니다: {target_path}")
    if not candidate.as_posix().startswith(REMOVABLE_ROOT):
        raise EvalError(f"{REMOVABLE_ROOT} 밖의 파일은 삭제할 수 없습니다: {target_path}")

    target = ROOT / candidate
    if target.is_symlink():
        raise EvalError(f"심볼릭 링크는 삭제하지 않습니다: {target_path}")

    allowed_root = (ROOT / REMOVABLE_ROOT).resolve()
    if allowed_root not in target.resolve().parents:
        raise EvalError(f"{REMOVABLE_ROOT} 밖의 파일은 삭제할 수 없습니다: {target_path}")
    return target


def _guard_resource_removal(context: dict) -> None:
    """결함 정의와 별개로 Harness가 직접 확인하는 삭제 안전 조건.

    이번 eval의 setup이 설치한 untracked 파일만 삭제할 수 있다.
    """
    target = context["target"]
    if not context["exists"]:
        raise EvalError(f"삭제 대상 파일이 없습니다: {target}")
    if context["tracked"]:
        raise EvalError(f"Git 추적 파일은 삭제하지 않습니다: {target}")
    if target not in context["installed"]:
        raise EvalError(
            f"이번 eval이 설치한 파일만 삭제할 수 있습니다: {target} "
            f"(설치 목록={list(context['installed'])})"
        )


def _fault_injection_report(fault, record: dict, scenario: Scenario) -> str:
    attempt = record.get("attempt", 1)
    return f"""# Fault Injection

## Fault ID
{record["fault_id"]}

## 시도 번호
{attempt}

## 주입 시각
{record["injected_at"]}

## 대상 파일
`{record["target"]}`

## 주입 시점
Developer {attempt}차 수정 완료 직후, Tester {attempt}차 실행 직전
{_previous_removal_section(record)}
## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
{fault.DESCRIPTION}

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer {attempt}차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `{fault.ANCHOR}` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
{fault.FAULT_CODE.strip()}
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `{record["before_sha256"]}` |
| 주입 후 | `{record["after_sha256"]}` |

{_removal_owner_section(record, scenario)}"""


def _previous_removal_section(record: dict) -> str:
    """직전 결함이 Developer의 손으로 제거되었는지 확인한 결과를 남긴다.

    연쇄 주입 시나리오에서만 내용이 생긴다. 이 확인을 통과하지 못하면 결함이 주입되지 않으므로,
    이 절이 존재한다는 것 자체가 직전 시도의 수정이 실재했다는 기록이다.
    """
    if not record.get("previous_fault_id"):
        return ""

    return f"""
## 직전 결함 제거 확인
| 항목 | 값 |
| --- | --- |
| 직전 결함 | `{record["previous_fault_id"]}` |
| 표식 제거 | `{record["previous_marker"]}` 없음 |
| 주입 직후 해시 | `{record["previous_after_sha256"]}` |
| 제거 후 해시 | `{record["previous_removed_sha256"]}` |
| 확인 시각 | {record["previous_removed_confirmed_at"]} |
| 근거 산출물 | `{record["attempt_change_log"]}` |

이 확인을 통과하지 못하면 이번 결함은 주입되지 않는다. Developer가 직전 결함을 그대로 둔 채
다음 결함으로 실패가 이어지면, 재시도 루프가 실제로 동작했는지 판정할 수 없기 때문이다.
"""


def _removal_owner_section(record: dict, scenario: Scenario) -> str:
    """이 결함을 누가 제거해야 하는지(또는 아무도 제거하지 않는지)를 남긴다."""
    attempt = record.get("attempt", 1)
    if scenario.is_chained and attempt >= len(scenario.fault_ids):
        return f"""
## 제거 주체
없음.

이 결함이 실패로 이어지는 순간 재시도 예산이 모두 소비되어 Developer {attempt + 1}차가 호출되지
않는다. 따라서 이 결함은 종료 시점까지 제품 코드에 남아 있는 것이 정상이다. 남아 있다는 사실
자체가 "예산 소진 이후 아무도 제품 코드를 건드리지 않았다" 는 증거가 된다.
결함은 eval teardown이 fixture 파일과 함께 통째로 제거한다.

## 잔존 확인 방법
`{record["target"]}` 에 `{record["marker"]}` 표식이 남아 있고 파일 해시가 주입 직후
(`{record["after_sha256"]}`)와 같은지 확인한다. `eval_harness.py assert` 가 이 항목을 자동으로
판정한다.
"""

    return f"""
## 제거 주체
Developer {attempt + 1}차.

Harness는 이 결함을 스스로 되돌리지 않는다. Harness가 자동으로 제거하면 재수정 주체가
Developer가 아니게 되어 `FAIL -> 분석 -> 재수정` 전이의 검증 의미가 사라진다.
Developer {attempt + 1}차는 `test-result-{attempt}.md` 를 근거로 이 결함을 제품 코드 결함으로
진단하고 제거해야 한다.

## 제거 확인 방법
`{record["target"]}` 에서 `{record["marker"]}` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
"""


def _resource_removal_report(fault, record: dict) -> str:
    symptom = getattr(fault, "SYMPTOM", "테스트를 실행할 수 없게 된다.")
    fault_id = record["fault_id"]
    return f"""# Fault Injection

## Fault ID
{fault_id}

## 주입 시각
{record["injected_at"]}

## 대상 파일
`{record["target"]}`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 실행 환경 오류 라우팅을 실제 pytest 실행으로 검증하기 위해, 테스트 실행에 필요한
런타임 리소스를 제거한다. `test-result-N.md` 의 `STATUS:` 나 실패 원인 분류 문자열을 임의로
바꾸지 않고, Tester가 실제 실행 결과만 보고 판정하도록 만드는 것이 목적이다.

## 결함 내용
{fault.DESCRIPTION}

## 주입 방식
이번 eval의 setup이 설치한 런타임 리소스 파일 하나를 삭제한다. 제품 코드는 한 글자도 바꾸지
않는다. 제품 코드를 깨뜨리면 `PRODUCT_CODE_DEFECT` 로 분류하는 것이 옳은 판정이 되어
검증하려는 경로를 지나가지 못한다.

## 주입 후 증상
{symptom}

## 삭제 안전장치
| 조건 | 확인 주체 |
| --- | --- |
| `sample-project/` 안의 상대 경로이며 심볼릭 링크가 아님 | `eval_harness.py` |
| Git 추적 파일이 아님 | `eval_harness.py` / `{fault_id}.precheck_fs` |
| 이번 eval의 setup이 설치한 파일임 | `eval_harness.py` / `{fault_id}.precheck_fs` |
| 파일 내용에 `{record["marker"]}` 표식이 있음 | `{fault_id}.precheck_fs` |

하나라도 어긋나면 파일을 지우지 않고 즉시 실패한다.

## 삭제 전 파일 해시 (sha256)
`{record["before_sha256"]}`

## 복구 주체
없음. eval teardown이 나머지 fixture와 함께 정리한다.

`ENVIRONMENT_ERROR` 는 재시도 예산을 소비하지 않고 즉시 종료하는 경로이므로
(`CLAUDE.md §20`), Developer 2차가 이 리소스를 되살리는 일 자체가 일어나지 않아야 한다.

## 복구되지 않았는지 확인하는 방법
`{record["target"]}` 이 여전히 존재하지 않는지 확인한다.
`eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
"""


# ---------------------------------------------------------------------------
# assert
# ---------------------------------------------------------------------------


def assert_run(run_id: str) -> list[Check]:
    """reports/<run-id>/ 산출물과 제품 코드 상태만 근거로 전이를 판정한다."""
    state = load_state()
    scenario = scenario_of_state(state)
    return build_checks(run_dir_of(run_id), scenario, state, offline=False)


def build_checks(
    run_dir: Path, scenario: Scenario, state: dict | None, *, offline: bool
) -> list[Check]:
    """산출물과 제품 코드 상태를 근거로 시나리오의 상태 전이를 판정한다.

    시나리오의 `outcome` 에 따라 가운데 판정만 갈라진다. 재시도 후 성공하는 시나리오는
    Developer 2차 / Tester 2차 / Reviewer 산출물이 있어야 하고, 즉시 종료하는 시나리오는
    같은 산출물이 하나도 없어야 한다. 앞뒤(산출물 존재, Tester 1차, 결함 상태, 복구)는 공유한다.

    `offline=True` 는 보존된 대표 결과를 다시 읽어 회귀를 확인하는 `selftest` 전용 모드다.
    이때 실행 환경에 의존하는 항목(결함 제거 여부, 테스트 약화 여부, git 상태)은 판정할 수
    없으므로 항목 이름과 순서만 유지하고 판정은 건너뛴다.
    """
    state = state or {}

    # 예산 소진 시나리오는 시도가 3회 반복되므로 판정 골격 자체가 다르다.
    # 기존 시나리오의 항목 이름과 순서를 건드리지 않기 위해 별도 경로로 분기한다.
    if scenario.outcome == OUTCOME_RETRY_EXHAUSTED:
        return _retry_exhausted_checks(run_dir, scenario, state, offline=offline)

    checks: list[Check] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, passed, detail))

    # 1. Planner 산출물
    plan = read_run_file(run_dir, "plan.md")
    check(
        "plan.md 존재",
        bool(plan and plan.strip()),
        "Planner 실행됨" if plan else "plan.md 없음",
    )

    plan_1 = read_run_file(run_dir, PLAN_SNAPSHOT_1) if scenario.snapshot_plan else None
    if scenario.snapshot_plan:
        check(
            "plan-1.md 스냅샷 존재",
            bool(plan_1 and plan_1.strip()),
            "Planner 1차 산출물 보존됨" if plan_1 else f"{PLAN_SNAPSHOT_1} 없음",
        )

    # 2. Developer 1차 산출물
    change_log_1 = read_run_file(run_dir, "change-log-1.md")
    check(
        "change-log-1.md 존재",
        bool(change_log_1 and change_log_1.strip()),
        "Developer 1차 실행됨" if change_log_1 else "change-log-1.md 없음",
    )

    # 3. Fault Injection 기록
    fault_record = state.get("fault")
    fault_report = read_run_file(run_dir, "fault-injection.md")
    check(
        "fault-injection.md 존재",
        bool(fault_report and (fault_record or offline)),
        f"fault_id={fault_record['fault_id']}"
        if fault_record
        else ("fault-injection.md 존재" if offline and fault_report else "결함 주입 기록 없음"),
    )
    check(
        "결함 주입이 Developer 1차 이후에 이루어짐",
        bool((fault_record or (offline and fault_report)) and change_log_1),
        "change-log-1.md 와 결함 주입 기록이 모두 존재",
    )

    # 3-1. 계획 범위 밖 결함이라는 전제 (재계획 시나리오 전용)
    if scenario.replan_checks:
        allowed_1 = plan_allowed_files(plan_1) if plan_1 else []
        target = _fault_target_path(scenario, fault_record)
        check(
            "주입 대상이 plan 1차 수정 허용 파일 목록 밖",
            bool(allowed_1) and target not in allowed_1,
            f"주입 대상={target} / plan 1차 허용 목록={allowed_1}",
        )
        expected_1 = list(scenario.expected_plan1_allowed)
        check(
            "plan 1차 수정 허용 파일 목록이 계획대로 한정됨",
            sorted(allowed_1) == sorted(expected_1) if expected_1 else bool(allowed_1),
            f"기대={expected_1} / 실제={allowed_1}",
        )

    # 4. Tester 1차 = FAIL
    test_result_1 = read_run_file(run_dir, "test-result-1.md")
    status_line_1 = first_line(test_result_1) if test_result_1 else ""
    check(
        "test-result-1.md 첫 줄이 STATUS: FAIL",
        status_line_1 == "STATUS: FAIL",
        f"첫 줄: {status_line_1!r}" if test_result_1 else "test-result-1.md 없음",
    )

    # 5. Tester가 실제 pytest를 실행했는지 확인 (문자열만 바꿔치기한 FAIL 방지)
    has_command = bool(test_result_1 and PYTEST_COMMAND in test_result_1)
    check(
        "test-result-1.md 에 고정 실행 명령 기록",
        has_command,
        f"`{PYTEST_COMMAND}` 기록됨" if has_command else "고정 실행 명령이 기록되지 않음",
    )
    token = scenario.expected_failing_token
    mentions_failed_test = bool(test_result_1 and token in test_result_1)
    check(
        scenario.failing_token_check_name,
        mentions_failed_test,
        f"{token} 관련 실패가 기록됨" if mentions_failed_test else f"{token} 실패 기록 없음",
    )

    # 6. 실패 원인 분류
    category = section_value(test_result_1, "실패 원인 분류") if test_result_1 else ""
    check(
        f"실패 원인 분류가 {scenario.expected_category}",
        category == scenario.expected_category,
        f"분류: {category!r}"
        + ("" if not category or category in FAILURE_CATEGORIES else " (정의되지 않은 값)"),
    )

    # 7. 종료 형태별 상태 전이 판정
    change_log_2 = read_run_file(run_dir, "change-log-2.md")
    if scenario.outcome == OUTCOME_BLOCKED:
        checks.extend(_blocked_outcome_checks(run_dir, scenario, plan, plan_1))
    else:
        checks.extend(
            _retry_outcome_checks(
                run_dir, scenario, plan_1, change_log_2, fault_record, offline=offline
            )
        )

    # 8. 주입된 결함의 현재 상태 (teardown 이전에만 판정 가능)
    checks.append(_fault_state_check(scenario, fault_record, offline=offline))

    # 8-1. Developer가 갱신된 계획 범위를 벗어나지 않았는지 확인
    if scenario.replan_checks:
        plan_2 = read_run_file(run_dir, PLAN_SNAPSHOT_2)
        allowed_2 = plan_allowed_files(plan_2) if plan_2 else []
        changed = change_log_files(change_log_1 or "") + change_log_files(change_log_2 or "")
        outside = sorted({path for path in changed if path not in allowed_2})
        check(
            "Developer 변경 파일이 plan 2차 수정 허용 목록 안에 있음",
            bool(changed) and not outside,
            f"변경 파일={sorted(set(changed))} / 허용 목록 밖={outside}",
        )

    # 9. 테스트 약화 여부
    checks.append(_test_not_weakened_check(scenario, offline=offline))

    # 10. 기존 제품 코드 보존 여부
    checks.append(_tracked_files_untouched_check(state, offline=offline))

    # 11. 최종 보고서
    report = read_run_file(run_dir, "report.md")
    check(
        "report.md 존재",
        bool(report and report.strip()),
        "최종 보고서 존재" if report else "report.md 없음",
    )
    if scenario.outcome == OUTCOME_BLOCKED:
        checks.append(_blocked_report_check(report, scenario))

    return checks


def _retry_exhausted_checks(
    run_dir: Path, scenario: Scenario, state: dict, *, offline: bool
) -> list[Check]:
    """재시도 예산을 모두 소비하고 BLOCKED 로 끝나는 시나리오의 전이를 판정한다.

    앞의 세 시나리오와 달리 시도가 여러 번 반복되므로, 시도마다 같은 항목 묶음을 반복해서
    판정한다. 각 시도에서 확인하는 것은 세 가지다.

    1. Developer가 직전 결함을 실제로 제거했는가 (주입 시점에 남긴 해시·표식 기록)
    2. 그 뒤 새로 주입된 결함으로 Tester가 실제 실행 결과 FAIL을 기록했는가
    3. 그 실패가 이전 시도와 **다른 증상** 인가 (같은 실패의 반복이 아님)

    마지막에는 반대로 **일어나지 않아야 하는 일** 을 확인한다. 예산이 소진된 뒤에는
    Developer 4차 / Tester 4차 / 4차 결함 주입 / Reviewer가 모두 없어야 한다.
    """
    checks: list[Check] = []
    injections = list(state.get("injections") or [])
    total_attempts = scenario.expected_attempts

    plan = read_run_file(run_dir, "plan.md")
    checks.append(
        Check("plan.md 존재", bool(plan and plan.strip()), "Planner 실행됨" if plan else "plan.md 없음")
    )
    plan_1 = read_run_file(run_dir, PLAN_SNAPSHOT_1)
    checks.append(
        Check(
            "plan-1.md 스냅샷 존재",
            bool(plan_1 and plan_1.strip()),
            "Planner 1차 산출물 보존됨" if plan_1 else f"{PLAN_SNAPSHOT_1} 없음",
        )
    )

    previous_results: list[str] = []
    for attempt in range(1, total_attempts + 1):
        change_log = read_run_file(run_dir, f"change-log-{attempt}.md")
        checks.append(
            Check(
                f"change-log-{attempt}.md 존재",
                bool(change_log and change_log.strip()),
                f"Developer {attempt}차 실행됨" if change_log else f"change-log-{attempt}.md 없음",
            )
        )

        if attempt >= 2:
            references = bool(change_log and f"test-result-{attempt - 1}" in change_log)
            checks.append(
                Check(
                    f"change-log-{attempt}.md 가 test-result-{attempt - 1}.md 를 근거로 참조",
                    references,
                    "이전 실패 결과 참조 확인" if references else f"test-result-{attempt - 1} 참조 없음",
                )
            )
            checks.append(_new_hypothesis_check(run_dir, attempt))
            checks.append(
                _previous_fault_removed_check(injections, attempt, offline=offline)
            )

        report_name = scenario.fault_report_name(attempt)
        fault_report = read_run_file(run_dir, report_name)
        record = injections[attempt - 1] if len(injections) >= attempt else None
        checks.append(
            Check(
                f"{report_name} 존재",
                bool(fault_report and (record or offline)),
                f"fault_id={record['fault_id']}"
                if record
                else (f"{report_name} 존재" if offline and fault_report else "결함 주입 기록 없음"),
            )
        )
        checks.append(
            Check(
                f"{attempt}차 결함 주입이 Developer {attempt}차 이후에 이루어짐",
                bool((record or (offline and fault_report)) and change_log),
                f"change-log-{attempt}.md 와 {report_name} 이(가) 모두 존재",
            )
        )

        test_result = read_run_file(run_dir, f"test-result-{attempt}.md")
        status_line = first_line(test_result) if test_result else ""
        checks.append(
            Check(
                f"test-result-{attempt}.md 첫 줄이 STATUS: FAIL",
                status_line == "STATUS: FAIL",
                f"첫 줄: {status_line!r}" if test_result else f"test-result-{attempt}.md 없음",
            )
        )
        has_command = bool(test_result and PYTEST_COMMAND in test_result)
        checks.append(
            Check(
                f"test-result-{attempt}.md 에 고정 실행 명령 기록",
                has_command,
                f"`{PYTEST_COMMAND}` 기록됨" if has_command else "고정 실행 명령이 기록되지 않음",
            )
        )

        token = (
            scenario.expected_failing_tokens[attempt - 1]
            if len(scenario.expected_failing_tokens) >= attempt
            else scenario.expected_failing_token
        )
        mentions = bool(test_result and token in test_result)
        checks.append(
            Check(
                f"test-result-{attempt}.md 가 {attempt}차 주입 결함의 실패 테스트를 기록",
                mentions,
                f"{token} 실패가 기록됨" if mentions else f"{token} 실패 기록 없음",
            )
        )
        if attempt >= 2:
            # 같은 실패가 반복된 것이 아니라 새 결함으로 인한 새 실패인지 확인한다.
            repeated = [
                index + 1 for index, earlier in enumerate(previous_results) if token in earlier
            ]
            checks.append(
                Check(
                    f"{attempt}차 실패 증상이 이전 시도와 다름",
                    mentions and not repeated,
                    f"{token} 이(가) 이전 시도에도 기록됨: {repeated}차"
                    if repeated
                    else f"{token} 은(는) {attempt}차에서 처음 실패",
                )
            )
        previous_results.append(test_result or "")

        category = section_value(test_result, "실패 원인 분류") if test_result else ""
        checks.append(
            Check(
                f"{attempt}차 실패 원인 분류가 {scenario.expected_category}",
                category == scenario.expected_category,
                f"분류: {category!r}"
                + ("" if not category or category in FAILURE_CATEGORIES else " (정의되지 않은 값)"),
            )
        )

    # 여기서부터는 **일어나지 않아야 하는 일** 을 판정한다.
    unchanged = bool(plan and plan_1 and sha256_of(plan) == sha256_of(plan_1))
    checks.append(
        Check(
            "Planner 2차가 호출되지 않음",
            unchanged,
            "plan.md 가 1차 주입 시점 스냅샷과 동일"
            if unchanged
            else f"plan-1 sha={sha256_of(plan_1)[:12] if plan_1 else None} / "
            f"plan sha={sha256_of(plan)[:12] if plan else None}",
        )
    )
    for artifact, actor in scenario.forbidden_artifacts:
        content = read_run_file(run_dir, artifact)
        # 결함 주입은 Agent 호출이 아니므로 항목 이름을 구분해 쓴다.
        name = (
            f"{actor}이 이루어지지 않음"
            if artifact.startswith("fault-injection")
            else f"{actor}가 호출되지 않음"
        )
        extra_ok = offline or len(injections) == total_attempts
        checks.append(
            Check(
                name,
                content is None and extra_ok,
                f"{artifact} 없음 / 주입 기록 {len(injections)}건"
                if content is None
                else f"{artifact} 존재 ({len(content)}자)",
            )
        )

    checks.extend(_state_json_checks(run_dir, scenario))
    checks.append(_last_fault_intact_check(injections, offline=offline))
    checks.append(_test_not_weakened_check(scenario, offline=offline))
    checks.append(_tracked_files_untouched_check(state, offline=offline))

    report = read_run_file(run_dir, "report.md")
    checks.append(
        Check("report.md 존재", bool(report and report.strip()), "최종 보고서 존재" if report else "report.md 없음")
    )
    checks.append(_blocked_report_check(report, scenario))
    return checks


def _new_hypothesis_check(run_dir: Path, attempt: int) -> Check:
    """재시도한 Developer가 이전과 다른 가설을 세웠는지 판정한다. (`CLAUDE.md §16`)"""
    name = f"change-log-{attempt}.md 가 이전 시도와 다른 가설을 기록"
    current = read_run_file(run_dir, f"change-log-{attempt}.md")
    previous = read_run_file(run_dir, f"change-log-{attempt - 1}.md")
    if not current or not previous:
        return Check(name, False, "비교할 change-log 가 없습니다")

    current_hypothesis = section_body(current, "수정 가설").strip()
    previous_hypothesis = section_body(previous, "수정 가설").strip()
    difference = section_body(current, "이전 시도와의 차이").strip()
    changed = bool(current_hypothesis) and current_hypothesis != previous_hypothesis
    described = bool(difference) and "최초 시도" not in difference
    return Check(
        name,
        changed and described,
        f"가설 변경={changed} / 이전 시도와의 차이 기록={described}",
    )


def _previous_fault_removed_check(
    injections: list[dict], attempt: int, *, offline: bool = False
) -> Check:
    """직전 결함이 Developer의 손으로 제거되었는지 주입 시점 기록으로 판정한다.

    이 판정의 근거는 `inject` 가 다음 결함을 주입하기 **직전에** 확인해 남긴 기록이다.
    (표식 부재 + 파일 해시 변경) 확인을 통과하지 못하면 결함이 주입되지 않으므로, 기록이
    존재한다는 것 자체가 제거가 실재했다는 뜻이다.
    """
    name = f"Developer {attempt}차가 {attempt - 1}차 주입 결함을 제거함"
    if offline:
        return Check(name, True, OFFLINE_SKIP_DETAIL)
    if len(injections) < attempt:
        return Check(name, False, f"{attempt}차 결함 주입 기록이 없어 판정 불가")

    record = injections[attempt - 1]
    previous = injections[attempt - 2]
    marker_removed = bool(record.get("previous_marker_removed"))
    linked = record.get("previous_after_sha256") == previous.get("after_sha256")
    changed = record.get("previous_removed_sha256") not in (None, previous.get("after_sha256"))
    return Check(
        name,
        marker_removed and linked and changed,
        f"{previous.get('fault_id')} 표식 제거={marker_removed} / 직전 주입 해시 일치={linked} / "
        f"파일 내용 변경={changed}",
    )


def _last_fault_intact_check(injections: list[dict], *, offline: bool = False) -> Check:
    """마지막으로 주입된 결함이 그대로 남아 있는지 판정한다.

    예산이 소진된 뒤에는 Developer가 호출되지 않으므로 이 결함을 제거할 주체가 없다.
    결함이 사라졌다면 예산 소진 이후에도 누군가 제품 코드를 고쳤다는 뜻이다.
    """
    name = "마지막 주입 결함이 제거되지 않고 남아 있음"
    if offline:
        return Check(name, True, OFFLINE_SKIP_DETAIL)
    if not injections:
        return Check(name, False, "결함 주입 기록이 없어 판정 불가")

    record = injections[-1]
    target = ROOT / record["target"]
    if not target.is_file():
        return Check(name, False, f"대상 파일이 없습니다: {record['target']}")

    source = target.read_text(encoding="utf-8")
    marker_present = record["marker"] in source
    same_hash = sha256_of(source) == record["after_sha256"]
    return Check(
        name,
        marker_present and same_hash,
        f"{record['fault_id']} 표식 유지={marker_present} / 주입 직후와 동일={same_hash}",
    )


def _fault_target_path(scenario: Scenario, fault_record: dict | None) -> str:
    """주입 대상 경로를 실제 주입 기록에서, 없으면 시나리오 정의에서 가져온다."""
    if fault_record and fault_record.get("target"):
        return fault_record["target"]
    try:
        return load_fault(scenario.fault).TARGET_PATH
    except EvalError:
        return ""


def _planner_second_call_checks(
    run_dir: Path,
    scenario: Scenario,
    plan_1: str | None,
    fault_record: dict | None,
    *,
    offline: bool,
) -> list[Check]:
    """Planner가 실제로 두 번 호출되어 계획을 갱신했는지 산출물로 판정한다.

    Planner는 운영과 동일하게 `plan.md` 하나만 쓴다. 재호출 증거는 1차 스냅샷과 현재
    `plan.md` 를 비교해 만든다. 두 번째 스냅샷은 여기서 남긴다.
    """
    plan_now = read_run_file(run_dir, "plan.md")
    if not offline and plan_now is not None:
        (run_dir / PLAN_SNAPSHOT_2).write_text(plan_now, encoding="utf-8")
    plan_2 = read_run_file(run_dir, PLAN_SNAPSHOT_2)

    checks = [
        Check(
            "plan-2.md 스냅샷 존재",
            bool(plan_2 and plan_2.strip()),
            "Planner 2차 산출물 보존됨" if plan_2 else f"{PLAN_SNAPSHOT_2} 없음",
        )
    ]

    both = bool(plan_1 and plan_2)
    checks.append(
        Check(
            "plan 1차와 2차의 내용이 실제로 다름",
            both and sha256_of(plan_1) != sha256_of(plan_2),
            f"plan-1 sha={sha256_of(plan_1)[:12] if plan_1 else None} / "
            f"plan-2 sha={sha256_of(plan_2)[:12] if plan_2 else None}",
        )
    )

    allowed_1 = plan_allowed_files(plan_1) if plan_1 else []
    allowed_2 = plan_allowed_files(plan_2) if plan_2 else []
    target = _fault_target_path(scenario, fault_record)
    checks.append(
        Check(
            "plan 2차가 1차 허용 목록을 유지하며 주입 대상 파일을 추가",
            target in allowed_2 and set(allowed_1).issubset(set(allowed_2)),
            f"plan 1차={allowed_1} / plan 2차={allowed_2} / 추가되어야 할 파일={target}",
        )
    )

    references = bool(plan_2 and "test-result-1" in plan_2)
    checks.append(
        Check(
            "plan 2차가 test-result-1.md 를 재계획 근거로 참조",
            references,
            "재계획 근거 참조 확인" if references else "test-result-1 참조 없음",
        )
    )

    cause_1 = section_body(plan_1, "예상 원인").strip() if plan_1 else ""
    cause_2 = section_body(plan_2, "예상 원인").strip() if plan_2 else ""
    checks.append(
        Check(
            "plan 1차와 2차의 예상 원인이 다름",
            bool(cause_1) and bool(cause_2) and cause_1 != cause_2,
            f"1차 {len(cause_1)}자 / 2차 {len(cause_2)}자 / 동일 여부={cause_1 == cause_2}",
        )
    )
    return checks


def _retry_outcome_checks(
    run_dir: Path,
    scenario: Scenario,
    plan_1: str | None,
    change_log_2: str | None,
    fault_record: dict | None,
    *,
    offline: bool,
) -> list[Check]:
    """재시도 후 SUCCESS 로 끝나는 시나리오의 전이를 판정한다."""
    checks: list[Check] = []

    # Planner 2차 (재계획 시나리오 전용)
    if scenario.replan_checks:
        checks.extend(
            _planner_second_call_checks(run_dir, scenario, plan_1, fault_record, offline=offline)
        )

    # Developer 2차가 실행되었고 1차 실패 결과를 근거로 삼았는지 확인
    checks.append(
        Check(
            "change-log-2.md 존재",
            bool(change_log_2 and change_log_2.strip()),
            "Developer 2차 실행됨" if change_log_2 else "change-log-2.md 없음",
        )
    )
    references_previous = bool(change_log_2 and "test-result-1" in change_log_2)
    checks.append(
        Check(
            "change-log-2.md 가 test-result-1.md 를 근거로 참조",
            references_previous,
            "이전 실패 결과 참조 확인" if references_previous else "test-result-1 참조 없음",
        )
    )
    if scenario.replan_checks:
        target = _fault_target_path(scenario, fault_record)
        changed_2 = change_log_files(change_log_2) if change_log_2 else []
        checks.append(
            Check(
                "change-log-2.md 의 변경 파일에 주입 대상 파일 포함",
                target in changed_2,
                f"주입 대상={target} / 2차 변경 파일={changed_2}",
            )
        )

    # Tester 2차 = PASS
    test_result_2 = read_run_file(run_dir, "test-result-2.md")
    status_line_2 = first_line(test_result_2) if test_result_2 else ""
    checks.append(
        Check(
            "test-result-2.md 첫 줄이 STATUS: PASS",
            status_line_2 == "STATUS: PASS",
            f"첫 줄: {status_line_2!r}" if test_result_2 else "test-result-2.md 없음",
        )
    )
    has_command_2 = bool(test_result_2 and PYTEST_COMMAND in test_result_2)
    checks.append(
        Check(
            "test-result-2.md 에 고정 실행 명령 기록",
            has_command_2,
            f"`{PYTEST_COMMAND}` 기록됨" if has_command_2 else "고정 실행 명령이 기록되지 않음",
        )
    )

    # Reviewer = APPROVED
    review = read_run_file(run_dir, "review.md")
    verdict_line = first_line(review) if review else ""
    checks.append(
        Check(
            "review.md 첫 줄이 VERDICT: APPROVED",
            verdict_line == "VERDICT: APPROVED",
            f"첫 줄: {verdict_line!r}" if review else "review.md 없음",
        )
    )

    # Orchestrator가 기록한 상태 전이
    checks.extend(_state_json_checks(run_dir, scenario))
    return checks


def _blocked_outcome_checks(
    run_dir: Path, scenario: Scenario, plan: str | None, plan_1: str | None
) -> list[Check]:
    """재시도 없이 즉시 BLOCKED 로 끝나는 시나리오의 전이를 판정한다.

    여기서 중요한 것은 무엇이 일어났는지가 아니라 **무엇이 일어나지 않았는지** 다.
    `ENVIRONMENT_ERROR` 는 재시도 예산을 소비하지 않고 즉시 종료하는 경로이므로
    (`CLAUDE.md §20`, `patchpilot.md §5`), 그 뒤 단계의 산출물이 하나도 없어야 한다.
    """
    checks: list[Check] = []

    # Planner는 운영과 동일하게 `plan.md` 하나만 쓴다. 재호출이 없었다는 증거는 결함 주입
    # 시점에 남긴 스냅샷과 현재 `plan.md` 가 같다는 사실로 만든다.
    unchanged = bool(plan and plan_1 and sha256_of(plan) == sha256_of(plan_1))
    checks.append(
        Check(
            "Planner 2차가 호출되지 않음",
            unchanged,
            "plan.md 가 결함 주입 시점 스냅샷과 동일"
            if unchanged
            else f"plan-1 sha={sha256_of(plan_1)[:12] if plan_1 else None} / "
            f"plan sha={sha256_of(plan)[:12] if plan else None}",
        )
    )

    for artifact, actor in scenario.forbidden_artifacts:
        content = read_run_file(run_dir, artifact)
        checks.append(
            Check(
                f"{actor}가 호출되지 않음",
                content is None,
                f"{artifact} 없음" if content is None else f"{artifact} 존재 ({len(content)}자)",
            )
        )

    checks.extend(_state_json_checks(run_dir, scenario))
    return checks


def _blocked_report_check(report: str | None, scenario: Scenario) -> Check:
    """최종 보고서에 BLOCKED 종료와 사유가 남았는지 판정한다. (`patchpilot.md §9`)"""
    name = "report.md 에 BLOCKED 종료와 사유가 기록됨"
    if not report:
        return Check(name, False, "report.md 없음")

    has_status = "BLOCKED" in report
    has_reason = scenario.expected_blocked_reason in report
    return Check(
        name,
        has_status and has_reason,
        f"BLOCKED 기록={has_status} / {scenario.expected_blocked_reason} 기록={has_reason}",
    )


def _state_json_checks(run_dir: Path, scenario: Scenario) -> list[Check]:
    raw = read_run_file(run_dir, "state.json")
    if raw is None:
        return [Check("state.json 존재", False, "state.json 없음")]

    try:
        state_json = json.loads(raw)
    except json.JSONDecodeError as error:
        return [Check("state.json 파싱", False, f"JSON 파싱 실패: {error}")]

    checks = [Check("state.json 존재", True, "state.json 파싱 성공")]

    retry_count = state_json.get("retry_count")
    expected_retry = scenario.expected_retry_count
    checks.append(
        Check(
            f"state.json retry_count == {expected_retry}",
            retry_count == expected_retry,
            f"retry_count={retry_count!r}",
        )
    )

    if scenario.outcome == OUTCOME_RETRY_EXHAUSTED:
        # 예산 소진 시나리오에서는 예산 자체가 판정 대상이다. retry_count 가 예산에 도달했다는
        # 사실이 종료 사유(`RETRY_BUDGET_EXCEEDED`)의 근거이기 때문이다. (`CLAUDE.md §16`)
        retry_budget = state_json.get("retry_budget")
        checks.append(
            Check(
                f"state.json retry_budget == {scenario.expected_retry_budget}",
                retry_budget == scenario.expected_retry_budget,
                f"retry_budget={retry_budget!r}",
            )
        )

    final_status = state_json.get("final_status")
    checks.append(
        Check(
            f"state.json final_status == {scenario.expected_final_status}",
            final_status == scenario.expected_final_status,
            f"final_status={final_status!r}",
        )
    )

    current_stage = state_json.get("current_stage")
    checks.append(
        Check(
            "state.json current_stage == DONE",
            current_stage == "DONE",
            f"current_stage={current_stage!r}",
        )
    )

    blocked_reason = state_json.get("blocked_reason")
    if scenario.outcome in (OUTCOME_BLOCKED, OUTCOME_RETRY_EXHAUSTED):
        checks.append(
            Check(
                f"state.json blocked_reason == {scenario.expected_blocked_reason}",
                blocked_reason == scenario.expected_blocked_reason,
                f"blocked_reason={blocked_reason!r}",
            )
        )
    else:
        checks.append(
            Check(
                "state.json blocked_reason 없음",
                blocked_reason in (None, ""),
                f"blocked_reason={blocked_reason!r}",
            )
        )

    attempts = state_json.get("attempts")
    expected_attempts = scenario.expected_attempts
    attempts_name = f"state.json attempts 가 {expected_attempts}회 기록"
    if not isinstance(attempts, list) or len(attempts) != expected_attempts:
        checks.append(Check(attempts_name, False, f"attempts={attempts!r}"))
        return checks

    checks.append(Check(attempts_name, True, f"시도 {expected_attempts}회 기록됨"))

    if scenario.outcome == OUTCOME_RETRY_EXHAUSTED:
        # 예산 소진은 시도 전부가 같은 사유로 실패했을 때만 성립한다. 하나라도 다르면
        # 다른 라우팅을 지나간 것이므로 검증 대상 전이가 아니다.
        for index, attempt in enumerate(attempts):
            checks.append(
                Check(
                    f"attempts[{index}] 이 FAIL / {scenario.expected_category}",
                    attempt.get("status") == "FAIL"
                    and attempt.get("failure_category") == scenario.expected_category,
                    f"status={attempt.get('status')!r}, "
                    f"failure_category={attempt.get('failure_category')!r}",
                )
            )
        review = state_json.get("review")
        verdict = review.get("verdict") if isinstance(review, dict) else review
        checks.append(
            Check("state.json review.verdict 없음", verdict in (None, ""), f"review={review!r}")
        )
        return checks

    first_attempt = attempts[0]
    checks.append(
        Check(
            f"attempts[0] 이 FAIL / {scenario.expected_category}",
            first_attempt.get("status") == "FAIL"
            and first_attempt.get("failure_category") == scenario.expected_category,
            f"status={first_attempt.get('status')!r}, "
            f"failure_category={first_attempt.get('failure_category')!r}",
        )
    )

    if scenario.outcome == OUTCOME_BLOCKED:
        # Reviewer가 호출되지 않았으므로 판정 기록도 비어 있어야 한다. (`patchpilot.md §7`)
        review = state_json.get("review")
        verdict = review.get("verdict") if isinstance(review, dict) else review
        checks.append(
            Check("state.json review.verdict 없음", verdict in (None, ""), f"review={review!r}")
        )
        return checks

    second_attempt = attempts[1]
    checks.append(
        Check(
            "attempts[1] 이 PASS",
            second_attempt.get("status") == "PASS",
            f"status={second_attempt.get('status')!r}",
        )
    )
    return checks


def _fault_state_check(scenario: Scenario, fault_record: dict | None, *, offline: bool) -> Check:
    """주입된 결함이 시나리오가 기대하는 상태로 남아 있는지 판정한다.

    재시도 시나리오에서는 Developer 2차가 결함을 제거해야 하고, 즉시 종료 시나리오에서는
    아무도 되돌리지 않아야 한다.
    """
    if scenario.outcome == OUTCOME_BLOCKED:
        return _resource_still_removed_check(fault_record, offline=offline)
    return _fault_removed_check(fault_record, offline=offline)


def _resource_still_removed_check(fault_record: dict | None, *, offline: bool = False) -> Check:
    """삭제된 런타임 리소스가 복구되지 않았는지 판정한다.

    `ENVIRONMENT_ERROR` 경로에는 Developer 2차가 없다. 리소스가 되살아나 있다면 Agent가
    실행 환경을 임의로 손댔거나 Harness가 결함을 스스로 되돌린 것이고, 그렇다면 이 전이는
    실행 환경 오류 상태에서 판정된 것이 아니게 된다.
    """
    name = "삭제된 런타임 리소스가 복구되지 않음"
    if offline:
        return Check(name, True, OFFLINE_SKIP_DETAIL)
    if not fault_record:
        return Check(name, False, "결함 주입 기록이 없어 판정 불가")

    target = ROOT / fault_record["target"]
    return Check(
        name,
        not target.exists(),
        f"{fault_record['target']} 없음"
        if not target.exists()
        else f"{fault_record['target']} 가 다시 존재합니다",
    )


def _fault_removed_check(fault_record: dict | None, *, offline: bool = False) -> Check:
    name = "주입된 결함이 Developer 2차에 의해 제거됨"
    if offline:
        return Check(name, True, OFFLINE_SKIP_DETAIL)
    if not fault_record:
        return Check(name, False, "결함 주입 기록이 없어 판정 불가")

    target = ROOT / fault_record["target"]
    if not target.is_file():
        return Check(name, False, f"대상 파일이 없습니다: {fault_record['target']}")

    source = target.read_text(encoding="utf-8")
    marker_removed = fault_record["marker"] not in source
    file_changed = sha256_of(source) != fault_record["after_sha256"]
    return Check(
        name,
        marker_removed and file_changed,
        "결함 표식이 제거되고 파일 내용이 실제로 변경됨"
        if marker_removed and file_changed
        else f"marker_removed={marker_removed}, file_changed={file_changed}",
    )


def _test_not_weakened_check(scenario: Scenario, *, offline: bool = False) -> Check:
    name = "eval 테스트가 약화되지 않음"
    if offline:
        return Check(name, True, OFFLINE_SKIP_DETAIL)

    missing: list[str] = []
    skipped: list[str] = []
    for fixture_name, install_target in scenario.installs:
        if "/tests/" not in install_target:
            continue
        installed = ROOT / install_target
        if not installed.is_file():
            return Check(name, False, f"설치된 {install_target} 가 없습니다")

        installed_source = installed.read_text(encoding="utf-8")
        expected = test_function_names((FIXTURES_DIR / fixture_name).read_text(encoding="utf-8"))
        missing.extend(sorted(expected - test_function_names(installed_source)))
        if "skip" in installed_source:
            skipped.append(install_target)

    return Check(
        name,
        not missing and not skipped,
        "원래 테스트 함수가 모두 유지되고 skip 처리가 없음"
        if not missing and not skipped
        else f"사라진 테스트={missing}, skip 포함={skipped}",
    )


def _tracked_files_untouched_check(state: dict, *, offline: bool = False) -> Check:
    """eval 실행이 기존 추적 파일을 건드리지 않았는지 확인한다."""
    if offline:
        return Check("기존 추적 파일이 변경되지 않음", True, OFFLINE_SKIP_DETAIL)
    baseline = set(state.get("snapshot", []))
    added = [line for line in sample_project_status() if line not in baseline]
    modified_tracked = [line for line in added if not line.startswith("??")]
    return Check(
        "기존 추적 파일이 변경되지 않음",
        not modified_tracked,
        "새로 생긴 변경은 eval fixture(untracked)뿐"
        if not modified_tracked
        else f"추적 파일 변경 발견: {modified_tracked}",
    )


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------


def teardown() -> list[Check]:
    """설치한 fixture를 제거하고 sample-project 복구 여부를 판정한다."""
    if not STATE_FILE.exists():
        return [Check("teardown", False, "eval 실행 상태 파일이 없어 teardown 대상이 없습니다")]

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    installed_targets = state.get("installed", [])

    removed = []
    kept = []
    for install_target in installed_targets:
        path = ROOT / install_target
        if not path.exists():
            continue
        if is_tracked(path):
            # 추적 중인 파일을 지우면 사용자의 실제 코드가 사라질 수 있으므로 건드리지 않는다.
            kept.append(install_target)
            continue
        path.unlink()
        removed.append(install_target)

    _remove_pycache_entries(installed_targets)
    leftover_dirs = _remove_created_dirs(state.get("created_dirs", []))

    checks = [
        Check(
            "eval fixture 제거",
            not kept,
            f"제거={removed}" if not kept else f"제거={removed}, 추적 파일이라 보존={kept}",
        )
    ]

    baseline = state.get("snapshot", [])
    current = sample_project_status()
    # 빈 디렉터리는 `git status` 에 나타나지 않으므로 상태 비교와 별개로 확인한다.
    restored = current == baseline and not leftover_dirs
    checks.append(
        Check(
            "sample-project 원상 복구",
            restored,
            "setup 시점 상태와 동일"
            if restored
            else f"복구 실패 / setup 시점={baseline} / 현재={current} / "
            f"남은 디렉터리={leftover_dirs}",
        )
    )

    checks.append(_pytest_baseline_check(state))

    STATE_FILE.unlink()
    if STATE_DIR.is_dir() and not any(STATE_DIR.iterdir()):
        STATE_DIR.rmdir()

    return checks


def _pytest_baseline_check(state: dict) -> Check:
    """복구 후 전체 테스트 결과가 setup 시점 기준선으로 돌아왔는지 판정한다.

    `git status` 비교만으로는 "파일은 원래대로인데 테스트가 깨진" 상태를 잡지 못한다.
    (예: eval이 설치한 모듈의 바이트코드 캐시가 남아 import 결과가 달라지는 경우)
    """
    name = "복구 후 기존 테스트 결과가 setup 시점과 동일"
    baseline = state.get("pytest_baseline")
    if not baseline:
        return Check(name, False, "setup 시점 기준선 기록이 없습니다")

    current = pytest_baseline()
    return Check(
        name,
        current == baseline,
        f"setup 시점={baseline.get('summary')!r} / 현재={current['summary']!r}",
    )


def _remove_created_dirs(created_dirs: list[str]) -> list[str]:
    """setup이 새로 만든 디렉터리를 비어 있을 때만 지우고, 남은 디렉터리 목록을 반환한다.

    안이 비어 있지 않으면 eval과 무관한 파일이 들어온 것이므로 지우지 않고 남긴다.
    """
    leftover: list[str] = []
    for relative in sorted(created_dirs, key=len, reverse=True):
        path = ROOT / relative
        if not path.is_dir():
            continue
        if any(path.iterdir()):
            leftover.append(relative)
            continue
        path.rmdir()
    return leftover


def _remove_pycache_entries(installed_targets: list[str]) -> None:
    """설치했던 모듈의 바이트코드 캐시만 제거한다.

    설치한 파일에 대응하는 캐시만 지운다. 캐시 디렉터리 전체를 지우면 eval과 무관한
    기존 제품 코드의 캐시까지 함께 사라진다.
    """
    for install_target in installed_targets:
        path = Path(install_target)
        cache_dir = ROOT / path.parent / "__pycache__"
        if not cache_dir.is_dir():
            continue
        for cached in cache_dir.glob(f"{path.stem}.*.pyc"):
            cached.unlink()


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------


def _scenario_for_run() -> Scenario:
    """진행 중인 eval의 시나리오를 해석한다. 상태 파일이 없으면 기본 시나리오로 본다."""
    try:
        return scenario_of_state(load_state())
    except EvalError:
        return resolve_scenario(None)


def cmd_finish(run_id: str) -> int:
    """자동 검증을 수행하고, 검증이 실패하거나 예외가 나도 teardown을 반드시 실행한다."""
    # teardown이 상태 파일을 지우므로 시나리오를 먼저 확정해 둔다.
    scenario = _scenario_for_run()
    checks: list[Check] = []
    try:
        checks.extend(assert_run(run_id))
    except Exception as error:
        checks.append(Check("eval 검증 실행", False, f"검증 중 예외 발생: {error}"))
    finally:
        try:
            checks.extend(teardown())
        except Exception as error:
            checks.append(Check("teardown 실행", False, f"teardown 중 예외 발생: {error}"))

    return _report(run_id, scenario, checks)


def cmd_assert(run_id: str) -> int:
    return _report(run_id, _scenario_for_run(), assert_run(run_id))


def cmd_teardown() -> int:
    checks = teardown()
    _print_checks(checks)
    return 0 if all(item.passed for item in checks) else 1


def _report(run_id: str, scenario: Scenario, checks: list[Check]) -> int:
    passed = all(item.passed for item in checks)
    _write_eval_result(run_id, scenario, checks, passed)
    _print_checks(checks)
    return 0 if passed else 1


def _print_checks(checks: list[Check]) -> None:
    for item in checks:
        print(f"[{'PASS' if item.passed else 'FAIL'}] {item.name} - {item.detail}")
    passed_count = sum(1 for item in checks if item.passed)
    print()
    print(f"EVAL: {'PASS' if passed_count == len(checks) else 'FAIL'} ({passed_count}/{len(checks)})")


def _write_eval_result(
    run_id: str, scenario: Scenario, checks: list[Check], passed: bool
) -> None:
    run_dir = REPORTS_DIR / run_id
    if not run_dir.is_dir():
        return

    rows = "\n".join(
        f"| {index} | {item.name} | {'PASS' if item.passed else 'FAIL'} | {item.detail.replace(chr(10), ' ')} |"
        for index, item in enumerate(checks, start=1)
    )
    passed_count = sum(1 for item in checks if item.passed)
    run_dir.joinpath("eval-result.md").write_text(
        f"""EVAL: {"PASS" if passed else "FAIL"}

# Eval Result

## Run ID
{run_id}

## 시나리오
{scenario.scenario_id}

## 판정 시각
{now_text()}

## 검증 대상 전이
{scenario.transition}

## 자동 검증 항목
| # | 항목 | 결과 | 근거 |
| --- | --- | --- | --- |
{rows}

## 종합
{passed_count}/{len(checks)} 항목 통과
""",
        encoding="utf-8",
    )


def cmd_selftest() -> int:
    """Agent 실행 없이 harness 자체의 회귀를 확인한다.

    시나리오가 늘어나면서 기존 시나리오의 판정이 조용히 달라지는 것이 가장 큰 위험이다.
    보존된 대표 결과를 다시 읽어 항목 이름/순서/판정을 대조한다. 실행 환경에 의존하는 항목은
    replay 대상이 아니므로 항목 이름만 유지하고 판정은 건너뛴다. (`OFFLINE_SKIP_DETAIL`)

    아직 대표 결과가 없는 시나리오는 replay 대상이 아니다. 정의가 실제 파일 및 운영 라우팅
    규칙과 맞물려 있는지만 `_scenario_definition_checks` 로 확인한다.
    """
    checks: list[Check] = []
    for scenario_id, example_name, golden in REGRESSION_EXAMPLES:
        checks.extend(_regression_replay_checks(scenario_id, example_name, golden))

    checks.extend(_scenario_definition_checks())
    checks.extend(_parser_checks(EXAMPLES_DIR / PARSER_EXAMPLE))

    _print_checks(checks)
    return 0 if all(item.passed for item in checks) else 1


def _regression_replay_checks(
    scenario_id: str, example_name: str, golden: tuple[str, ...]
) -> list[Check]:
    """보존된 대표 결과 하나를 현재 판정 코드로 다시 읽어 회귀를 확인한다."""
    example_dir = EXAMPLES_DIR / example_name
    if not example_dir.is_dir():
        return [
            Check(
                f"{scenario_id} 회귀 기준 대표 결과 존재",
                False,
                f"폴더가 없습니다: {example_dir}",
            )
        ]

    checks = [
        Check(
            f"{scenario_id} 회귀 기준 대표 결과 존재",
            True,
            f"reports/examples/{example_name}",
        )
    ]

    scenario = resolve_scenario(scenario_id)
    replayed = build_checks(example_dir, scenario, None, offline=True)
    names = tuple(item.name for item in replayed)
    checks.append(
        Check(
            f"{scenario_id} 검증 항목 이름과 순서가 골든 목록과 일치",
            names == golden,
            f"{len(names)}개 항목 / 골든 {len(golden)}개"
            + ("" if names == golden else f" / 실제={list(names)}"),
        )
    )

    # 승격이 빠뜨린 산출물이 있으면 판정 replay는 성립하지 않는다. 조용히 넘어가면 통과한
    # 것처럼 보이므로, 무엇이 없어서 어디까지만 대조했는지 항목으로 남긴다.
    missing = [
        item for item in scenario.extra_promoted_files if not (example_dir / item).is_file()
    ]
    if missing:
        checks.append(
            Check(
                f"{scenario_id} 판정 replay 범위",
                True,
                f"항목 이름과 순서만 대조 / 대표 결과에 없는 산출물={missing}",
            )
        )
        return checks

    skipped = [item.name for item in replayed if item.detail == OFFLINE_SKIP_DETAIL]
    failed = [item.name for item in replayed if not item.passed]
    checks.append(
        Check(
            f"{scenario_id} 보존된 대표 결과가 현재 판정 코드에서도 전부 PASS",
            not failed,
            f"replay {len(replayed) - len(skipped)}개 판정 / 환경 의존 {len(skipped)}개 제외"
            if not failed
            else f"실패 항목={failed}",
        )
    )
    return checks


def _scenario_definition_checks() -> list[Check]:
    """모든 시나리오 정의가 실제 파일과 맞물려 있는지 확인한다."""
    checks: list[Check] = []
    seen_targets: dict[str, str] = {}

    for scenario_id, scenario in sorted(SCENARIOS.items()):
        missing: list[str] = []
        if not (ROOT / scenario.task).is_file():
            missing.append(scenario.task)
        for fault_id in scenario.fault_ids:
            if not (FAULTS_DIR / f"{fault_id}.py").is_file():
                missing.append(f"evals/faults/{fault_id}.py")
        for fixture_name, _ in scenario.installs:
            if not (FIXTURES_DIR / fixture_name).is_file():
                missing.append(f"evals/fixtures/{fixture_name}")
        checks.append(
            Check(
                f"{scenario_id} 정의 파일이 모두 존재",
                not missing,
                "task / fault / fixture 모두 존재" if not missing else f"없는 파일={missing}",
            )
        )

        duplicated = [
            target for _, target in scenario.installs if seen_targets.get(target) == scenario_id
        ]
        targets = [target for _, target in scenario.installs]
        checks.append(
            Check(
                f"{scenario_id} 설치 경로가 서로 겹치지 않음",
                len(set(targets)) == len(targets) and not duplicated,
                f"설치 경로 {len(targets)}건",
            )
        )
        for target in targets:
            seen_targets[target] = scenario_id

        if scenario.replan_checks:
            fault = load_fault(scenario.fault)
            has_precheck = callable(getattr(fault, "precheck", None))
            outside = fault.TARGET_PATH not in scenario.expected_plan1_allowed
            checks.append(
                Check(
                    f"{scenario_id} 결함이 계획 범위 밖 전제를 스스로 검사",
                    has_precheck and outside,
                    f"precheck={has_precheck} / 주입 대상={fault.TARGET_PATH} / "
                    f"plan 1차 기대 허용 목록={list(scenario.expected_plan1_allowed)}",
                )
            )

        if scenario.outcome == OUTCOME_BLOCKED:
            checks.extend(_blocked_scenario_definition_checks(scenario))
        if scenario.outcome == OUTCOME_RETRY_EXHAUSTED:
            checks.extend(_retry_exhausted_scenario_definition_checks(scenario))
    return checks


def _blocked_scenario_definition_checks(scenario: Scenario) -> list[Check]:
    """즉시 종료 시나리오의 정의가 운영 라우팅 규칙과 맞물려 있는지 확인한다.

    대표 결과가 아직 없어 replay로 확인할 수 없는 동안, 정의만이라도 기계로 검사한다.
    """
    scenario_id = scenario.scenario_id
    fault = load_fault(scenario.fault)
    install_targets = [target for _, target in scenario.installs]
    kind = fault_kind_of(fault)
    has_precheck_fs = callable(getattr(fault, "precheck_fs", None))
    inside_installs = fault.TARGET_PATH in install_targets
    inside_root = fault.TARGET_PATH.startswith(REMOVABLE_ROOT)
    forbidden = {artifact for artifact, _ in scenario.forbidden_artifacts}
    promoted = {*scenario.promoted_files, *scenario.extra_promoted_files}

    return [
        Check(
            f"{scenario_id} 삭제 대상이 이번 eval이 설치한 리소스로 한정됨",
            kind == FAULT_KIND_RESOURCE_REMOVAL
            and has_precheck_fs
            and inside_installs
            and inside_root,
            f"kind={kind} / precheck_fs={has_precheck_fs} / 설치 목록 포함={inside_installs} / "
            f"대상={fault.TARGET_PATH}",
        ),
        Check(
            f"{scenario_id} 기대 종료 상태가 즉시 종료 라우팅과 일치",
            scenario.expected_retry_count == 0
            and scenario.expected_attempts == 1
            and scenario.expected_final_status == "BLOCKED"
            and scenario.expected_blocked_reason == scenario.expected_category,
            f"retry_count={scenario.expected_retry_count} / attempts={scenario.expected_attempts} / "
            f"final_status={scenario.expected_final_status} / "
            f"blocked_reason={scenario.expected_blocked_reason!r}",
        ),
        Check(
            f"{scenario_id} 호출되지 않아야 할 Agent 산출물이 정의됨",
            forbidden == {"change-log-2.md", "test-result-2.md", "review.md"},
            f"forbidden={sorted(forbidden)}",
        ),
        Check(
            f"{scenario_id} Planner 재호출 판정용 스냅샷 설정",
            scenario.snapshot_plan and not scenario.replan_checks,
            f"snapshot_plan={scenario.snapshot_plan} / replan_checks={scenario.replan_checks}",
        ),
        Check(
            f"{scenario_id} 승격 필수 목록에 존재하지 않을 산출물이 없음",
            not (promoted & forbidden),
            f"승격 필수={sorted(promoted)}",
        ),
    ]


def _retry_exhausted_scenario_definition_checks(scenario: Scenario) -> list[Check]:
    """예산 소진 시나리오의 정의가 연쇄 주입 전제와 운영 라우팅 규칙에 맞는지 확인한다.

    대표 결과가 아직 없어 replay로 확인할 수 없는 동안, 정의만이라도 기계로 검사한다.
    """
    scenario_id = scenario.scenario_id
    fault_ids = list(scenario.fault_ids)
    faults = [load_fault(fault_id) for fault_id in fault_ids]
    install_targets = [target for _, target in scenario.installs]
    forbidden = {artifact for artifact, _ in scenario.forbidden_artifacts}
    promoted = {*scenario.promoted_files, *scenario.extra_promoted_files}
    tokens = list(scenario.expected_failing_tokens)
    signatures = [getattr(fault, "SIGNATURE_TEST", None) for fault in faults]
    links = [getattr(fault, "PREVIOUS_FAULT_ID", None) for fault in faults]
    next_attempt = scenario.expected_attempts + 1

    return [
        Check(
            f"{scenario_id} 시도 수만큼 서로 다른 결함이 정의됨",
            len(fault_ids) == scenario.expected_attempts and len(set(fault_ids)) == len(fault_ids),
            f"시도={scenario.expected_attempts} / 결함={fault_ids}",
        ),
        Check(
            f"{scenario_id} 결함이 순서대로 직전 결함을 가리킴",
            links == [None, *fault_ids[:-1]],
            f"PREVIOUS_FAULT_ID={links}",
        ),
        Check(
            f"{scenario_id} 모든 결함이 계획 범위 안 전제를 스스로 검사",
            all(callable(getattr(fault, "precheck", None)) for fault in faults)
            and all(fault.TARGET_PATH in install_targets for fault in faults),
            f"precheck={[callable(getattr(f, 'precheck', None)) for f in faults]} / "
            f"대상={[f.TARGET_PATH for f in faults]}",
        ),
        Check(
            f"{scenario_id} 시도별 실패 증상이 서로 다르게 정의됨",
            len(tokens) == scenario.expected_attempts
            and len(set(tokens)) == len(tokens)
            and tokens == signatures,
            f"기대 실패 테스트={tokens} / 결함 정의의 SIGNATURE_TEST={signatures}",
        ),
        Check(
            f"{scenario_id} 기대 종료 상태가 예산 소진 라우팅과 일치",
            scenario.expected_retry_count == scenario.expected_retry_budget
            and scenario.expected_attempts == scenario.expected_retry_budget
            and scenario.expected_final_status == "BLOCKED"
            and scenario.expected_blocked_reason == "RETRY_BUDGET_EXCEEDED",
            f"retry_count={scenario.expected_retry_count} / "
            f"retry_budget={scenario.expected_retry_budget} / "
            f"attempts={scenario.expected_attempts} / "
            f"blocked_reason={scenario.expected_blocked_reason!r}",
        ),
        Check(
            f"{scenario_id} 예산 소진 이후 산출물이 금지 목록에 정의됨",
            forbidden
            == {
                f"change-log-{next_attempt}.md",
                f"test-result-{next_attempt}.md",
                f"fault-injection-{next_attempt}.md",
                "review.md",
            },
            f"forbidden={sorted(forbidden)}",
        ),
        Check(
            f"{scenario_id} 승격 필수 목록에 존재하지 않을 산출물이 없음",
            not (promoted & forbidden),
            f"승격 필수={sorted(promoted)}",
        ),
    ]


def _parser_checks(example_dir: Path) -> list[Check]:
    """plan / change-log 파서가 실제 Agent 산출물에서 의도한 값만 뽑는지 확인한다."""
    checks: list[Check] = []

    plan = read_run_file(example_dir, "plan.md")
    allowed = plan_allowed_files(plan) if plan else []
    checks.append(
        Check(
            "plan 수정 허용 파일 목록 파서가 목록 항목만 인식",
            allowed == ["sample-project/src/expense/tip.py"],
            f"추출 결과={allowed}",
        )
    )

    change_log = read_run_file(example_dir, "change-log-2.md")
    changed = change_log_files(change_log) if change_log else []
    checks.append(
        Check(
            "change-log 변경 파일 목록 파서가 경로를 인식",
            changed == ["sample-project/src/expense/tip.py"],
            f"추출 결과={changed}",
        )
    )
    return checks


def cmd_status() -> int:
    if not STATE_FILE.exists():
        print("진행 중인 eval 실행이 없습니다.")
        return 0

    print(STATE_FILE.read_text(encoding="utf-8").rstrip())
    print()
    print("현재 sample-project 상태:")
    for line in sample_project_status() or ["  (변경 없음)"]:
        print(f"  {line}")
    return 0


def _scenario_for_promote(run_id: str, run_dir: Path) -> Scenario:
    """승격 시점의 시나리오를 해석한다.

    `finish` 가 teardown에서 실행 상태 파일을 지우므로 승격 시점에는 상태 파일이 없는 것이
    정상이다. 그래서 `eval-result.md` 에 기록된 시나리오와 run-id 접미사를 차례로 본다.
    """
    if STATE_FILE.exists():
        return scenario_of_state(load_state())

    eval_result = read_run_file(run_dir, "eval-result.md")
    recorded = section_value(eval_result, "시나리오") if eval_result else ""
    if recorded in SCENARIOS:
        return SCENARIOS[recorded]

    for scenario_id in SCENARIOS:
        if run_id.lower().endswith(scenario_id):
            return SCENARIOS[scenario_id]
    return resolve_scenario(None)


def cmd_promote(run_id: str, name: str | None) -> int:
    run_dir = run_dir_of(run_id)
    scenario = _scenario_for_promote(run_id, run_dir)

    eval_result = read_run_file(run_dir, "eval-result.md")
    if eval_result is None:
        raise EvalError("eval-result.md 가 없습니다. `assert` 또는 `finish` 를 먼저 실행하세요.")
    if first_line(eval_result) != "EVAL: PASS":
        raise EvalError(
            f"eval 결과가 PASS 가 아니므로 승격하지 않습니다. (첫 줄: {first_line(eval_result)!r})"
        )

    required = [*(scenario.promoted_files or PROMOTED_FILES), *scenario.extra_promoted_files]
    missing = [item for item in required if not (run_dir / item).is_file()]
    if missing:
        raise EvalError(f"대표 결과에 필요한 파일이 없습니다: {missing}")

    target_name = name or f"EVAL-{run_id.removeprefix('RUN-')}"
    target_dir = EXAMPLES_DIR / target_name
    if target_dir.exists():
        raise EvalError(f"이미 존재하는 대표 결과 폴더입니다: reports/examples/{target_name}")

    target_dir.mkdir(parents=True)
    for item in [*required, *OPTIONAL_PROMOTED_FILES]:
        source = run_dir / item
        if source.is_file():
            shutil.copyfile(source, target_dir / item)

    print(f"대표 결과 복사 완료: reports/examples/{target_name}")
    for copied in sorted(path.name for path in target_dir.iterdir()):
        print(f"  {copied}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval_harness.py",
        description="PatchPilot Harness 재시도 루프 eval 실행 도구",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="eval fixture 설치 및 원상태 스냅샷")
    setup_parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO,
        choices=sorted(SCENARIOS),
        help=f"실행할 eval 시나리오 (기본값: {DEFAULT_SCENARIO})",
    )
    setup_parser.add_argument(
        "--task", default=None, help="시나리오 기본 task를 덮어쓸 경로 (기본값: 시나리오 정의)"
    )

    inject_parser = subparsers.add_parser("inject", help="Developer N차 직후 결함 주입")
    inject_parser.add_argument("--run-id", required=True)
    inject_parser.add_argument(
        "--fault", default=None, help="주입할 결함 (기본값: 시나리오 정의)"
    )
    inject_parser.add_argument(
        "--attempt",
        type=int,
        default=None,
        help="몇 번째 시도 직후의 주입인지. 시도마다 다른 결함을 주입하는 시나리오에서는 필수",
    )

    assert_parser = subparsers.add_parser("assert", help="산출물 기반 자동 검증 (teardown 없음)")
    assert_parser.add_argument("--run-id", required=True)

    finish_parser = subparsers.add_parser(
        "finish", help="자동 검증 후 결과와 무관하게 teardown 수행"
    )
    finish_parser.add_argument("--run-id", required=True)

    subparsers.add_parser("teardown", help="설치한 fixture 제거 및 복구 확인")
    subparsers.add_parser("status", help="현재 eval 실행 상태 출력")
    subparsers.add_parser(
        "selftest", help="Agent 실행 없이 harness 자체의 회귀를 확인 (보존된 대표 결과 replay)"
    )

    promote_parser = subparsers.add_parser(
        "promote", help="검증에 통과한 실행 결과를 reports/examples/ 로 복사"
    )
    promote_parser.add_argument("--run-id", required=True)
    promote_parser.add_argument("--name", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup":
            return cmd_setup(args.scenario, args.task)
        if args.command == "inject":
            return cmd_inject(args.run_id, args.fault, args.attempt)
        if args.command == "assert":
            return cmd_assert(args.run_id)
        if args.command == "finish":
            return cmd_finish(args.run_id)
        if args.command == "teardown":
            return cmd_teardown()
        if args.command == "status":
            return cmd_status()
        if args.command == "selftest":
            return cmd_selftest()
        if args.command == "promote":
            return cmd_promote(args.run_id, args.name)
    except EvalError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
