"""`harness-eval-006` (REVIEW_CHANGES_REQUESTED_NO_BUDGET) 계약 검증.

이 종료 경로의 정체성은 하나다.

    **Tester 는 매번 통과하는데 Reviewer 의 CHANGES_REQUESTED 만으로 예산이 소진된다.**

그래서 검증도 두 방향으로 한다. 성립해야 하는 것(Tester PASS ×3, 최종 review 가
CHANGES_REQUESTED, retry_count == retry_budget)과, 성립하면 안 되는 것(Tester FAIL 이 섞임,
최종 review 가 APPROVED, 4차 산출물 존재)을 함께 본다.

`harness-eval-004` 와 의미가 섞이지 않는지도 확인한다. 두 시나리오는 종료 사유가 다르고
(`RETRY_BUDGET_EXCEEDED` vs `REVIEW_CHANGES_REQUESTED_NO_BUDGET`) Tester 기대값이 정반대다.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

NEWLINE = chr(10)

REVIEW_OK = "VERDICT: CHANGES_REQUESTED"
STATUS_OK = "STATUS: PASS"
PYTEST_LINE = "uv run pytest sample-project/tests -q"


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _named(checks, needle: str):
    found = [check for check in checks if needle in check.name]
    assert len(found) == 1, f"{needle!r} 항목이 {len(found)}개입니다: {[c.name for c in checks]}"
    return found[0]


def _failing(checks) -> list[str]:
    return [check.name for check in checks if not check.passed]


def _build_run(
    tmp_path: Path,
    *,
    attempts: int = 3,
    statuses: tuple[str, ...] = (STATUS_OK, STATUS_OK, STATUS_OK),
    verdict: str = REVIEW_OK,
    fault_ids: tuple[str, ...] = (
        "review_budget_001",
        "review_budget_002",
        "review_budget_003",
    ),
    extra_files: tuple[str, ...] = (),
    state_overrides: dict | None = None,
) -> Path:
    """오프라인 replay 가 읽을 수 있는 완결된 run 디렉터리를 만든다.

    기본값은 검증 대상 전이를 그대로 만족한다. 반증 사례는 인자 하나만 바꿔서 만든다.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)

    plan = "# Plan" + NEWLINE * 2 + "## 7. 수정 허용 파일 목록" + NEWLINE + (
        "- `sample-project/src/expense/refund.py`" + NEWLINE
    )
    (run_dir / "plan.md").write_text(plan, encoding="utf-8")
    (run_dir / "plan-1.md").write_text(plan, encoding="utf-8")

    for index in range(1, attempts + 1):
        hypothesis = "최초 시도" if index == 1 else f"review.md 지적 {index}번째 항목을 제거"
        (run_dir / f"change-log-{index}.md").write_text(
            f"# Change Log {index}{NEWLINE * 2}"
            f"## 수정 가설{NEWLINE}{hypothesis}{NEWLINE * 2}"
            f"## 이전 시도와의 차이{NEWLINE}"
            + ("최초 시도" if index == 1 else f"Reviewer 지적을 근거로 {index}차 수정")
            + NEWLINE,
            encoding="utf-8",
        )
        (run_dir / f"fault-injection-{index}.md").write_text(
            f"# Fault Injection{NEWLINE * 2}## Fault ID{NEWLINE}{fault_ids[index - 1]}{NEWLINE}",
            encoding="utf-8",
        )
        status = statuses[index - 1] if len(statuses) >= index else STATUS_OK
        body = f"{status}{NEWLINE * 2}# Test Result {index}{NEWLINE * 2}## 실행 명령{NEWLINE}`{PYTEST_LINE}`{NEWLINE}"
        if status == "STATUS: FAIL":
            body += (
                NEWLINE
                + "```text"
                + NEWLINE
                + "FAILED sample-project/tests/test_refund.py::test_split_refund_broken"
                + NEWLINE
                + "```"
                + NEWLINE
            )
        (run_dir / f"test-result-{index}.md").write_text(body, encoding="utf-8")

    (run_dir / "review.md").write_text(
        f"{verdict}{NEWLINE * 2}# Review{NEWLINE}", encoding="utf-8"
    )
    (run_dir / "report.md").write_text(
        f"# PatchPilot Report{NEWLINE * 2}BLOCKED{NEWLINE}"
        f"REVIEW_CHANGES_REQUESTED_NO_BUDGET{NEWLINE}",
        encoding="utf-8",
    )

    state = {
        "retry_count": 3,
        "retry_budget": 3,
        "unknown_retry_used": False,
        "final_status": "BLOCKED",
        "current_stage": "DONE",
        "blocked_reason": "REVIEW_CHANGES_REQUESTED_NO_BUDGET",
        "attempts": [
            {
                "n": index,
                "change_log": f"change-log-{index}.md",
                "test_result": f"test-result-{index}.md",
                "status": "PASS" if statuses[index - 1] == STATUS_OK else "FAIL",
                "failure_category": None,
            }
            for index in range(1, attempts + 1)
        ],
        "review": {"verdict": verdict.split(": ", 1)[1], "file": "review.md"},
    }
    state.update(state_overrides or {})
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for name in extra_files:
        (run_dir / name).write_text("사후 산출물" + NEWLINE, encoding="utf-8")

    return run_dir


def _checks(eval_harness, run_dir: Path, scenario=None):
    scenario = scenario or eval_harness.SCENARIOS["harness-eval-006"]
    return eval_harness.build_checks(run_dir, scenario, None, offline=True)


# ---------------------------------------------------------------------------
# 정상 전이
# ---------------------------------------------------------------------------


def test_review_exhausted_run_passes_every_check(eval_harness, tmp_path):
    checks = _checks(eval_harness, _build_run(tmp_path))
    assert not _failing(checks), _failing(checks)


def test_scenario_uses_its_own_outcome(eval_harness):
    scenario = eval_harness.SCENARIOS["harness-eval-006"]
    assert scenario.outcome == eval_harness.OUTCOME_REVIEW_EXHAUSTED
    assert scenario.outcome != eval_harness.OUTCOME_RETRY_EXHAUSTED
    assert scenario.expected_final_status == "BLOCKED"
    assert scenario.expected_blocked_reason == "REVIEW_CHANGES_REQUESTED_NO_BUDGET"


def test_blocked_reason_is_declared_by_the_orchestrator_contract(eval_harness, repo_root):
    """사유 코드가 `patchpilot.md` 가 실제로 선언한 값인지 원문으로 확인한다."""
    command = (repo_root / ".claude" / "commands" / "patchpilot.md").read_text(encoding="utf-8")
    assert "REVIEW_CHANGES_REQUESTED_NO_BUDGET" in command


def test_stop_gate_requires_changes_requested_for_this_reason(guard_stop_gate):
    """`guard_stop_gate.py` G16 과 기대 산출물이 어긋나지 않는지 확인한다."""
    assert "REVIEW_CHANGES_REQUESTED_NO_BUDGET" in guard_stop_gate.BLOCKED_REASONS


# ---------------------------------------------------------------------------
# 반증 — Tester 가 실패하면 이 경로가 아니다
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failing_attempt", [1, 2, 3])
def test_any_tester_failure_fails_verification(eval_harness, tmp_path, failing_attempt):
    """반증: 한 회차라도 Tester 가 실패하면 예산 소비 주체를 특정할 수 없다."""
    statuses = [STATUS_OK, STATUS_OK, STATUS_OK]
    statuses[failing_attempt - 1] = "STATUS: FAIL"
    checks = _checks(eval_harness, _build_run(tmp_path, statuses=tuple(statuses)))

    assert not _named(
        checks, f"test-result-{failing_attempt}.md 첫 줄이 STATUS: PASS"
    ).passed
    assert not _named(checks, "재시도 예산을 소비한 주체가 Reviewer 임").passed


def test_broken_tests_fail_even_when_status_line_says_pass(eval_harness, tmp_path):
    """반증: 첫 줄만 PASS 로 적고 pytest 출력에 실패가 있으면 통과하면 안 된다."""
    run_dir = _build_run(tmp_path)
    (run_dir / "test-result-2.md").write_text(
        f"{STATUS_OK}{NEWLINE * 2}## 실행 명령{NEWLINE}`{PYTEST_LINE}`{NEWLINE * 2}"
        f"```text{NEWLINE}"
        f"FAILED sample-project/tests/test_refund.py::test_split_refund_broken{NEWLINE}"
        f"```{NEWLINE}",
        encoding="utf-8",
    )
    checks = _checks(eval_harness, run_dir)
    assert not _named(checks, "2차 주입 결함이 테스트를 깨뜨리지 않음").passed


# ---------------------------------------------------------------------------
# 반증 — Reviewer 판정
# ---------------------------------------------------------------------------


def test_approved_review_fails_verification(eval_harness, tmp_path):
    """반증: 최종 review 가 APPROVED 면 이 종료 경로가 성립하지 않는다."""
    run_dir = _build_run(tmp_path, verdict="VERDICT: APPROVED")
    checks = _checks(eval_harness, run_dir)
    assert not _named(checks, "review.md 첫 줄이 VERDICT: CHANGES_REQUESTED").passed
    assert not _named(checks, "state.json review.verdict == CHANGES_REQUESTED").passed


def test_missing_review_fails_verification(eval_harness, tmp_path):
    run_dir = _build_run(tmp_path)
    (run_dir / "review.md").unlink()
    assert not _named(
        _checks(eval_harness, run_dir), "review.md 첫 줄이 VERDICT: CHANGES_REQUESTED"
    ).passed


# ---------------------------------------------------------------------------
# 반증 — 예산과 시도 기록
# ---------------------------------------------------------------------------


def test_retry_count_below_budget_fails_verification(eval_harness, tmp_path):
    """반증: 예산이 남았는데 종료했다면 이 사유 코드가 아니다."""
    run_dir = _build_run(tmp_path, state_overrides={"retry_count": 2})
    assert not _named(_checks(eval_harness, run_dir), "state.json retry_count == 3").passed


def test_wrong_retry_budget_fails_verification(eval_harness, tmp_path):
    run_dir = _build_run(tmp_path, state_overrides={"retry_budget": 5})
    assert not _named(_checks(eval_harness, run_dir), "state.json retry_budget == 3").passed


def test_unknown_retry_used_fails_verification(eval_harness, tmp_path):
    """반증: UNKNOWN 재시도를 썼다면 3회가 전부 Reviewer 지적이 아니다."""
    run_dir = _build_run(tmp_path, state_overrides={"unknown_retry_used": True})
    assert not _named(
        _checks(eval_harness, run_dir), "state.json unknown_retry_used == false"
    ).passed


def test_wrong_attempt_count_fails_verification(eval_harness, tmp_path):
    run_dir = _build_run(tmp_path, attempts=3, state_overrides={"attempts": []})
    assert not _named(_checks(eval_harness, run_dir), "state.json attempts 가 3회 기록").passed


def test_attempt_with_failure_category_fails_verification(eval_harness, tmp_path):
    """반증: 시도에 실패 원인 분류가 있으면 그 실패가 예산을 소비했을 수 있다."""
    run_dir = _build_run(tmp_path)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    state["attempts"][1]["failure_category"] = "PRODUCT_CODE_DEFECT"
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert not _named(
        _checks(eval_harness, run_dir), "attempts[1] 이 PASS / 실패 원인 분류 없음"
    ).passed


def test_wrong_blocked_reason_fails_verification(eval_harness, tmp_path):
    run_dir = _build_run(
        tmp_path, state_overrides={"blocked_reason": "RETRY_BUDGET_EXCEEDED"}
    )
    assert not _named(
        _checks(eval_harness, run_dir),
        "state.json blocked_reason == REVIEW_CHANGES_REQUESTED_NO_BUDGET",
    ).passed


# ---------------------------------------------------------------------------
# 반증 — 4차 산출물
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "artifact,needle",
    [
        ("change-log-4.md", "Developer 4차가 호출되지 않음"),
        ("test-result-4.md", "Tester 4차가 호출되지 않음"),
        ("fault-injection-4.md", "4차 결함 주입이 이루어지지 않음"),
    ],
)
def test_fourth_round_artifacts_fail_verification(eval_harness, tmp_path, artifact, needle):
    """반증: 예산이 소진된 뒤 4차 산출물이 있으면 안 된다."""
    run_dir = _build_run(tmp_path, extra_files=(artifact,))
    assert not _named(_checks(eval_harness, run_dir), needle).passed


def test_replan_fails_verification(eval_harness, tmp_path):
    """반증: Planner 가 다시 불려 plan.md 가 바뀌면 이 경로가 아니다."""
    run_dir = _build_run(tmp_path)
    (run_dir / "plan.md").write_text("# Plan v2" + NEWLINE, encoding="utf-8")
    assert not _named(_checks(eval_harness, run_dir), "Planner 2차가 호출되지 않음").passed


# ---------------------------------------------------------------------------
# 반증 — 결함이 회차마다 달라야 한다
# ---------------------------------------------------------------------------


def test_repeated_fault_fails_verification(eval_harness, tmp_path):
    """반증: 같은 결함을 두 번 주입하면 회차가 실제로 진행됐다고 볼 수 없다."""
    run_dir = _build_run(
        tmp_path,
        fault_ids=("review_budget_001", "review_budget_001", "review_budget_003"),
    )
    checks = _checks(eval_harness, run_dir)
    assert not _named(checks, "2차 주입 결함이 review_budget_002").passed
    assert not _named(checks, "2차 주입 결함이 이전 시도와 다름").passed


def test_change_log_without_review_reference_fails_verification(eval_harness, tmp_path):
    """반증: 재수정 근거로 Reviewer 지적을 적지 않으면 통과하면 안 된다."""
    run_dir = _build_run(tmp_path)
    (run_dir / "change-log-2.md").write_text(
        f"# Change Log 2{NEWLINE * 2}## 수정 가설{NEWLINE}그냥 고쳤다{NEWLINE * 2}"
        f"## 이전 시도와의 차이{NEWLINE}특별히 없다{NEWLINE}",
        encoding="utf-8",
    )
    assert not _named(
        _checks(eval_harness, run_dir), "change-log-2.md 가 Reviewer 지적을 재수정 근거로 사용"
    ).passed


# ---------------------------------------------------------------------------
# 정의 check
# ---------------------------------------------------------------------------


def test_definition_checks_pass_for_eval_006(eval_harness):
    checks = eval_harness._review_exhausted_scenario_definition_checks(
        eval_harness.SCENARIOS["harness-eval-006"]
    )
    assert not _failing(checks), _failing(checks)


def test_definition_fails_when_fault_target_is_outside_plan_scope(eval_harness, monkeypatch):
    """반증: 주입 대상이 설치 목록 밖이면 계획 범위 안 전제가 깨진다.

    범위 밖이면 Developer 가 결함을 지울 수 없어 `SCOPE_OUT_OF_PLAN` 으로 끝난다.
    검증하려는 종료 경로가 아니므로 정의 단계에서 걸러야 한다.
    """
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        installs=(("refund.py", "sample-project/src/expense/other.py"),),
    )
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "계획 범위 안 전제를 스스로 검사").passed


def test_definition_fails_when_expected_blocked_reason_is_wrong(eval_harness):
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        expected_blocked_reason="RETRY_BUDGET_EXCEEDED",
    )
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "Reviewer 예산 소진 라우팅과 일치").passed


def test_definition_fails_when_retry_count_is_below_budget(eval_harness):
    scenario = replace(eval_harness.SCENARIOS["harness-eval-006"], expected_retry_count=2)
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "Reviewer 예산 소진 라우팅과 일치").passed


def test_definition_fails_when_attempts_is_not_three(eval_harness):
    scenario = replace(eval_harness.SCENARIOS["harness-eval-006"], expected_attempts=2)
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "Reviewer 예산 소진 라우팅과 일치").passed


def test_definition_fails_when_a_tester_failure_is_expected(eval_harness):
    """반증: Tester 실패를 기대하면 이 경로의 정체성이 무너진다."""
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        expected_category="PRODUCT_CODE_DEFECT",
    )
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "Tester 실패를 기대하지 않음").passed


def test_definition_fails_when_review_is_not_promoted(eval_harness):
    """반증: `review.md` 가 승격 필수 목록에 없으면 종료 사유의 근거가 보존되지 않는다."""
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        promoted_files=("report.md", "state.json"),
    )
    checks = eval_harness._review_exhausted_scenario_definition_checks(scenario)
    assert not _named(checks, "승격 필수 목록에 review.md 가 포함됨").passed


def test_missing_fault_module_fails_definition(eval_harness):
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        fault_sequence=("review_budget_001", "does_not_exist", "review_budget_003"),
    )
    original = eval_harness.SCENARIOS
    eval_harness.SCENARIOS = {scenario.scenario_id: scenario}
    try:
        checks = eval_harness._scenario_definition_checks()
    finally:
        eval_harness.SCENARIOS = original
    assert not _named(checks, "정의 파일이 모두 존재").passed


def test_missing_fixture_fails_definition(eval_harness):
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-006"],
        installs=(("does_not_exist.py", "sample-project/src/expense/refund.py"),),
    )
    original = eval_harness.SCENARIOS
    eval_harness.SCENARIOS = {scenario.scenario_id: scenario}
    try:
        checks = eval_harness._scenario_definition_checks()
    finally:
        eval_harness.SCENARIOS = original
    assert not _named(checks, "정의 파일이 모두 존재").passed


# ---------------------------------------------------------------------------
# 결함 자체의 성질
# ---------------------------------------------------------------------------


CASES = [(1000, 3), (1001, 3), (900, 3), (1000, 4), (9999, 7), (0, 3), (1000, 1)]

FIXED_SOURCE = (
    "def split_refund(amount: int, methods: int) -> list[int]:" + NEWLINE
    + "    if methods <= 0:" + NEWLINE
    + '        raise ValueError("methods")' + NEWLINE
    + "    if amount < 0:" + NEWLINE
    + '        raise ValueError("amount")' + NEWLINE
    + "    base = amount // methods" + NEWLINE
    + "    remainder = amount % methods" + NEWLINE
    + "    return [base + 1 if i < remainder else base for i in range(methods)]" + NEWLINE
)


@pytest.mark.parametrize(
    "fault_id", ["review_budget_001", "review_budget_002", "review_budget_003"]
)
def test_fault_does_not_change_behaviour(eval_harness, fault_id):
    """세 결함 모두 반환값과 예외 동작을 바꾸지 않아야 한다.

    동작이 바뀌면 Tester 가 실패하고, 그 순간 예산을 소비한 주체가 Reviewer 라고 말할 수
    없게 된다. 이 성질이 시나리오 전체의 전제다.
    """
    fault = eval_harness.load_fault(fault_id)
    namespace: dict = {}
    exec(compile(fault.apply(FIXED_SOURCE), fault_id, "exec"), namespace)
    split_refund = namespace["split_refund"]

    for amount, methods in CASES:
        shares = split_refund(amount, methods)
        assert sum(shares) == amount, (fault_id, amount, methods, shares)
        assert len(shares) == methods, (fault_id, amount, methods, shares)
        assert max(shares) - min(shares) <= 1, (fault_id, amount, methods, shares)

    assert split_refund(1000, 3) == [334, 333, 333], fault_id
    for bad in ((1000, 0), (-1, 3)):
        with pytest.raises(ValueError):
            split_refund(*bad)


@pytest.mark.parametrize(
    "fault_id", ["review_budget_001", "review_budget_002", "review_budget_003"]
)
def test_fault_precheck_rejects_out_of_plan_target(eval_harness, fault_id):
    """반증: 주입 대상이 계획 허용 목록 밖이면 결함 정의가 스스로 거부해야 한다."""
    fault = eval_harness.load_fault(fault_id)
    fault.precheck([fault.TARGET_PATH])
    with pytest.raises(ValueError):
        fault.precheck(["sample-project/src/expense/somewhere_else.py"])
    with pytest.raises(ValueError):
        fault.precheck([])


def test_faults_declare_distinct_violated_rules(eval_harness):
    """세 결함이 서로 다른 규칙을 어겨야 회차마다 다른 지적이 나온다."""
    rules = [
        eval_harness.load_fault(fault_id).VIOLATED_RULE
        for fault_id in ("review_budget_001", "review_budget_002", "review_budget_003")
    ]
    assert len(set(rules)) == 3, rules


# ---------------------------------------------------------------------------
# 기존 시나리오와 섞이지 않는지
# ---------------------------------------------------------------------------


def test_retry_exhausted_scenario_is_unaffected(eval_harness):
    """`harness-eval-004` 는 여전히 Tester 실패로 예산을 소진하는 시나리오다."""
    scenario = eval_harness.SCENARIOS["harness-eval-004"]
    assert scenario.outcome == eval_harness.OUTCOME_RETRY_EXHAUSTED
    assert scenario.expected_blocked_reason == "RETRY_BUDGET_EXCEEDED"
    assert scenario.expected_category == "PRODUCT_CODE_DEFECT"


def test_test_defect_scenario_is_unaffected(eval_harness):
    """`harness-eval-005` 의 TEST_DEFECT 경로가 그대로인지 확인한다."""
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    assert scenario.outcome == eval_harness.OUTCOME_BLOCKED
    assert scenario.expected_blocked_reason == "TEST_DEFECT_NEEDS_HUMAN"
    assert scenario.expected_category == "TEST_DEFECT"


def test_every_blocked_reason_is_used_by_at_most_one_scenario(eval_harness):
    """종료 사유가 겹치면 어느 시나리오가 그 경로를 검증하는지 말할 수 없다."""
    reasons = [
        scenario.expected_blocked_reason
        for scenario in eval_harness.SCENARIOS.values()
        if scenario.expected_blocked_reason
    ]
    assert len(reasons) == len(set(reasons)), reasons


def test_install_paths_do_not_collide_with_other_scenarios(eval_harness):
    targets = {target for _, target in eval_harness.SCENARIOS["harness-eval-006"].installs}
    others = {
        target
        for scenario_id, scenario in eval_harness.SCENARIOS.items()
        if scenario_id != "harness-eval-006"
        for _, target in scenario.installs
    }
    assert not (targets & others)
