"""`harness-eval-005` (TEST_DEFECT) 도입으로 일반화된 eval 계약의 검증.

검사 대상은 구현 세부가 아니라 **계약** 이다.

* 즉시 종료 시나리오의 `expected_blocked_reason` 이 운영 라우팅 규칙에서 유도되는가
* 테스트 결함 주입이 이번 eval이 설치한 테스트 fixture 밖으로 나가지 못하는가
* 주입 이후 기존 테스트가 하나라도 바뀌면 판정이 FAIL 되는가
* 기존 `harness-eval-003` (ENVIRONMENT_ERROR) 정의 의미가 그대로인가

모든 항목은 반증 사례를 함께 가진다. FAIL 을 만들어낼 수 없는 check 는 계약을 지키는지
말해 주지 못한다.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

NEWLINE = chr(10)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _named(checks, needle: str):
    """이름에 `needle` 이 들어간 항목 하나를 고른다. 없거나 여럿이면 실패시킨다."""
    found = [check for check in checks if needle in check.name]
    assert len(found) == 1, f"{needle!r} 항목이 {len(found)}개입니다: {[c.name for c in checks]}"
    return found[0]


class _StubFault:
    """정의 check 의 반증 사례를 만들기 위한 최소 결함 스텁."""

    def __init__(self, target_path: str, *, precheck_test=None, precheck_fs=None):
        self.FAULT_ID = "stub_fault"
        self.TARGET_PATH = target_path
        self.MARKER = "patchpilot-eval:stub_fault"
        if precheck_test is not None:
            self.precheck_test = precheck_test
        if precheck_fs is not None:
            self.precheck_fs = precheck_fs


def _noop(context: dict) -> None:
    return None


def _run_dir_with_state(tmp_path: Path, scenario, **overrides) -> Path:
    """시나리오 기대값을 그대로 만족하는 `state.json` 을 만든다. 반증은 override 로 만든다."""
    state = {
        "retry_count": scenario.expected_retry_count,
        "retry_budget": scenario.expected_retry_budget,
        "unknown_retry_used": False,
        "final_status": scenario.expected_final_status,
        "current_stage": "DONE",
        "blocked_reason": scenario.expected_blocked_reason,
        "attempts": [{"n": 1, "status": "FAIL", "failure_category": scenario.expected_category}],
        "review": {"verdict": None, "file": None},
    }
    state.update(overrides)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_dir


# ---------------------------------------------------------------------------
# category -> blocked_reason 계약
# ---------------------------------------------------------------------------


def test_blocked_reason_map_covers_every_blocked_scenario(eval_harness):
    """즉시 종료 시나리오의 사유 코드는 전부 라우팅 표에서 유도되어야 한다."""
    blocked = [
        scenario
        for scenario in eval_harness.SCENARIOS.values()
        if scenario.outcome == eval_harness.OUTCOME_BLOCKED
    ]
    assert blocked, "즉시 종료 시나리오가 하나도 없습니다"
    for scenario in blocked:
        expected = eval_harness.BLOCKED_REASON_BY_CATEGORY.get(scenario.expected_category)
        assert expected == scenario.expected_blocked_reason, scenario.scenario_id


def test_blocked_reason_map_matches_orchestrator_contract(eval_harness, repo_root):
    """표의 사유 코드가 `patchpilot.md` 가 실제로 선언한 코드인지 확인한다.

    Eval 편의로 새 계약을 만들지 않았다는 것을 문서 원문으로 확인하는 항목이다.
    """
    command = (repo_root / ".claude" / "commands" / "patchpilot.md").read_text(encoding="utf-8")
    for category, reason in eval_harness.BLOCKED_REASON_BY_CATEGORY.items():
        assert category in eval_harness.FAILURE_CATEGORIES, category
        assert reason in command, reason


def test_test_defect_maps_to_needs_human(eval_harness):
    assert eval_harness.BLOCKED_REASON_BY_CATEGORY["TEST_DEFECT"] == "TEST_DEFECT_NEEDS_HUMAN"


def test_wrong_blocked_reason_for_test_defect_fails_definition_check(eval_harness):
    """반증: TEST_DEFECT 인데 사유 코드가 다르면 정의 check 가 FAIL 해야 한다."""
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-005"],
        expected_blocked_reason="ENVIRONMENT_ERROR",
    )
    check = _named(
        eval_harness._blocked_scenario_definition_checks(scenario), "즉시 종료 라우팅과 일치"
    )
    assert not check.passed


def test_unmapped_category_fails_definition_check(eval_harness):
    """반증: 라우팅 표에 없는 분류로는 즉시 종료 시나리오를 정의할 수 없다."""
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-005"],
        expected_category="PRODUCT_CODE_DEFECT",
    )
    check = _named(
        eval_harness._blocked_scenario_definition_checks(scenario), "즉시 종료 라우팅과 일치"
    )
    assert not check.passed


# ---------------------------------------------------------------------------
# harness-eval-003 회귀 — 기존 의미가 그대로인가
# ---------------------------------------------------------------------------


# `harness-eval-003` 정의 check 의 이름과 순서. 일반화가 기존 판정을 바꾸지 않았다는 기준선이다.
GOLDEN_003_DEFINITION_NAMES = (
    "harness-eval-003 삭제 대상이 이번 eval이 설치한 리소스로 한정됨",
    "harness-eval-003 기대 종료 상태가 즉시 종료 라우팅과 일치",
    "harness-eval-003 호출되지 않아야 할 Agent 산출물이 정의됨",
    "harness-eval-003 Planner 재호출 판정용 스냅샷 설정",
    "harness-eval-003 승격 필수 목록에 존재하지 않을 산출물이 없음",
)


def test_environment_error_definition_checks_unchanged(eval_harness):
    """기존 ENVIRONMENT_ERROR 정의는 이름·순서·판정이 모두 그대로여야 한다."""
    checks = eval_harness._blocked_scenario_definition_checks(
        eval_harness.SCENARIOS["harness-eval-003"]
    )
    assert tuple(check.name for check in checks) == GOLDEN_003_DEFINITION_NAMES
    assert all(check.passed for check in checks), [c for c in checks if not c.passed]


def test_environment_error_still_requires_resource_removal_kind(eval_harness):
    """반증: 삭제 결함이 아닌 것을 ENVIRONMENT_ERROR 시나리오에 넣으면 FAIL 해야 한다."""
    check = eval_harness._blocked_fault_scope_check(
        "harness-eval-003",
        _StubFault("sample-project/config/settlement_runtime.json", precheck_fs=_noop),
        eval_harness.FAULT_KIND_CODE_INJECTION,
        True,
    )
    assert not check.passed


def test_environment_error_scenario_does_not_gain_budget_checks(eval_harness, tmp_path):
    """일반화로 추가한 예산 판정이 기존 시나리오에 새어 들어가지 않아야 한다."""
    scenario = eval_harness.SCENARIOS["harness-eval-003"]
    assert scenario.verify_budget_untouched is False
    names = [
        check.name
        for check in eval_harness._state_json_checks(
            _run_dir_with_state(tmp_path, scenario), scenario
        )
    ]
    assert not [name for name in names if "retry_budget" in name]
    assert not [name for name in names if "unknown_retry_used" in name]


# ---------------------------------------------------------------------------
# 주입 대상 범위
# ---------------------------------------------------------------------------


def test_test_injection_scope_check_passes_for_eval_005(eval_harness):
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    fault = eval_harness.load_fault(scenario.fault)
    assert eval_harness.fault_kind_of(fault) == eval_harness.FAULT_KIND_TEST_INJECTION
    check = _named(
        eval_harness._blocked_scenario_definition_checks(scenario), "테스트 fixture로 한정됨"
    )
    assert check.passed


def test_test_injection_outside_tests_root_fails_definition_check(eval_harness):
    """반증: 주입 대상이 테스트 fixture 밖(제품 코드)을 가리키면 FAIL 해야 한다."""
    check = eval_harness._blocked_fault_scope_check(
        "harness-eval-005",
        _StubFault("sample-project/src/expense/coupon.py", precheck_test=_noop),
        eval_harness.FAULT_KIND_TEST_INJECTION,
        True,
    )
    assert not check.passed


def test_test_injection_without_precheck_fails_definition_check(eval_harness):
    """반증: `precheck_test` 가 없으면 스스로 전제를 검사하지 않는 결함이다."""
    check = eval_harness._blocked_fault_scope_check(
        "harness-eval-005",
        _StubFault("sample-project/tests/test_coupon.py"),
        eval_harness.FAULT_KIND_TEST_INJECTION,
        True,
    )
    assert not check.passed


def test_test_injection_outside_installs_fails_definition_check(eval_harness):
    """반증: 이번 eval이 설치하지 않은 테스트 파일은 주입 대상이 될 수 없다."""
    check = eval_harness._blocked_fault_scope_check(
        "harness-eval-005",
        _StubFault("sample-project/tests/test_coupon.py", precheck_test=_noop),
        eval_harness.FAULT_KIND_TEST_INJECTION,
        False,
    )
    assert not check.passed


@pytest.mark.parametrize(
    "target",
    [
        "sample-project/src/expense/coupon.py",
        "evals/fixtures/test_coupon.py",
        "sample-project/tests/../src/expense/coupon.py",
        "tests/test_coupon.py",
    ],
)
def test_resolve_test_injection_target_rejects_paths_outside_tests_root(eval_harness, target):
    with pytest.raises(eval_harness.EvalError):
        eval_harness._resolve_test_injection_target(target)


def test_resolve_test_injection_target_accepts_installed_test_path(eval_harness):
    resolved = eval_harness._resolve_test_injection_target("sample-project/tests/test_coupon.py")
    assert resolved.name == "test_coupon.py"


# ---------------------------------------------------------------------------
# 주입 안전 조건
# ---------------------------------------------------------------------------


def _context(**overrides) -> dict:
    context = {
        "target": "sample-project/tests/test_coupon.py",
        "installed": ("sample-project/tests/test_coupon.py",),
        "tracked": False,
        "exists": True,
        "content": "same",
        "fixture_content": "same",
    }
    context.update(overrides)
    return context


def test_guard_test_injection_accepts_untouched_installed_fixture(eval_harness):
    eval_harness._guard_test_injection(_context())


@pytest.mark.parametrize(
    "overrides",
    [
        {"exists": False},
        {"tracked": True},
        {"installed": ()},
        {"fixture_content": None},
        {"content": "누군가 이미 고쳤다"},
    ],
    ids=["missing", "tracked", "not-installed", "no-fixture", "content-drift"],
)
def test_guard_test_injection_rejects_unsafe_targets(eval_harness, overrides):
    with pytest.raises(eval_harness.EvalError):
        eval_harness._guard_test_injection(_context(**overrides))


def test_fault_precheck_rejects_modified_test_file(eval_harness):
    """결함 정의도 Harness와 독립적으로 같은 조건을 막아야 한다."""
    fault = eval_harness.load_fault("test_defect_001")
    with pytest.raises(ValueError):
        fault.precheck_test(_context(content="누군가 이미 고쳤다"))


def test_fault_apply_requires_the_contradicted_test(eval_harness):
    """모순의 상대편이 되는 기존 테스트가 없으면 주입하지 않는다."""
    fault = eval_harness.load_fault("test_defect_001")
    with pytest.raises(ValueError):
        fault.apply("def test_something_else():" + NEWLINE + "    assert True" + NEWLINE)


def test_fault_apply_adds_exactly_one_test(eval_harness, repo_root):
    """주입은 테스트를 하나 추가할 뿐 기존 테스트를 건드리지 않는다."""
    fault = eval_harness.load_fault("test_defect_001")
    source = (repo_root / "evals" / "fixtures" / "test_coupon.py").read_text(encoding="utf-8")
    injected = fault.apply(source)

    before = eval_harness.test_function_names(source)
    after = eval_harness.test_function_names(injected)
    assert after - before == {fault.SIGNATURE_TEST}
    assert before <= after
    assert "skip" not in injected
    assert injected.startswith(source.rstrip(NEWLINE))


def test_injected_test_contradicts_an_existing_test(eval_harness, repo_root):
    """두 테스트가 같은 입력에 서로 다른 반환값을 요구하는지 확인한다.

    이 성질이 깨지면 어떤 제품 코드로도 통과할 수 없다는 전제가 무너지고, Developer 재수정만으로
    풀리는 평범한 `PRODUCT_CODE_DEFECT` 가 된다.
    """
    fault = eval_harness.load_fault("test_defect_001")
    fixture = (repo_root / "evals" / "fixtures" / "test_coupon.py").read_text(encoding="utf-8")

    assert "apply_coupon(1000, 3) == [334, 333, 333]" in fixture
    assert "apply_coupon(1000, 3) == [333, 333, 334]" in fault.FAULT_CODE


# ---------------------------------------------------------------------------
# 주입 이후 판정 — 테스트가 그대로인가
# ---------------------------------------------------------------------------


def _install_injected(eval_harness, monkeypatch, tmp_path: Path, content: str | None = None):
    """가짜 저장소 루트에 주입된 테스트 파일을 설치하고 주입 기록을 만든다."""
    fault = eval_harness.load_fault("test_defect_001")
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    fixture = (eval_harness.FIXTURES_DIR / "test_coupon.py").read_text(encoding="utf-8")

    target = tmp_path / "sample-project" / "tests" / "test_coupon.py"
    target.parent.mkdir(parents=True)
    target.write_text(content if content is not None else fault.apply(fixture), encoding="utf-8")

    monkeypatch.setattr(eval_harness, "ROOT", tmp_path)
    record = {
        "fault_id": fault.FAULT_ID,
        "kind": eval_harness.FAULT_KIND_TEST_INJECTION,
        "target": "sample-project/tests/test_coupon.py",
        "marker": fault.MARKER,
    }
    return scenario, record


def test_injected_test_intact_check_passes_when_nothing_changed(
    eval_harness, monkeypatch, tmp_path
):
    scenario, record = _install_injected(eval_harness, monkeypatch, tmp_path)
    check = eval_harness._injected_test_intact_check(scenario, record)
    assert check.passed, check.detail


def test_injected_test_intact_check_fails_when_injected_test_removed(
    eval_harness, monkeypatch, tmp_path
):
    """반증: 누군가 주입된 모순 테스트를 지우면 FAIL 이어야 한다."""
    fixture = (eval_harness.FIXTURES_DIR / "test_coupon.py").read_text(encoding="utf-8")
    scenario, record = _install_injected(eval_harness, monkeypatch, tmp_path, content=fixture)
    assert not eval_harness._injected_test_intact_check(scenario, record).passed


def test_injected_test_intact_check_fails_when_existing_assertion_changed(
    eval_harness, monkeypatch, tmp_path
):
    """반증: 표식은 남기고 기존 assertion 만 고쳐도 FAIL 이어야 한다.

    표식 존재 여부만 보는 판정이었다면 이 사례를 놓친다.
    """
    fault = eval_harness.load_fault("test_defect_001")
    fixture = (eval_harness.FIXTURES_DIR / "test_coupon.py").read_text(encoding="utf-8")
    weakened = fault.apply(fixture).replace(
        "assert apply_coupon(1000, 3) == [334, 333, 333]",
        "assert len(apply_coupon(1000, 3)) == 3",
    )
    scenario, record = _install_injected(eval_harness, monkeypatch, tmp_path, content=weakened)

    check = eval_harness._injected_test_intact_check(scenario, record)
    assert not check.passed
    # 표식은 그대로 남아 있는데도 FAIL 이라는 사실이 근거로 남아야 한다.
    assert "표식 존치=True" in check.detail


def test_injected_test_intact_check_fails_when_existing_test_is_skipped(
    eval_harness, monkeypatch, tmp_path
):
    """반증: 기존 테스트에 skip 을 붙이면 FAIL 이어야 한다."""
    fault = eval_harness.load_fault("test_defect_001")
    fixture = (eval_harness.FIXTURES_DIR / "test_coupon.py").read_text(encoding="utf-8")
    marker = '@pytest.mark.skip(reason="flaky")'
    weakened = fault.apply(fixture).replace(
        "def test_apply_coupon_distributes_remainder_to_earlier_items_first():",
        marker + NEWLINE + "def test_apply_coupon_distributes_remainder_to_earlier_items_first():",
    )
    scenario, record = _install_injected(eval_harness, monkeypatch, tmp_path, content=weakened)
    assert not eval_harness._injected_test_intact_check(scenario, record).passed


def test_injected_test_intact_check_fails_when_file_is_gone(eval_harness, monkeypatch, tmp_path):
    scenario, record = _install_injected(eval_harness, monkeypatch, tmp_path)
    (tmp_path / "sample-project" / "tests" / "test_coupon.py").unlink()
    assert not eval_harness._injected_test_intact_check(scenario, record).passed


def test_injected_test_intact_check_is_offline_skipped(eval_harness):
    """오프라인 replay 에서는 항목 이름만 유지하고 판정하지 않는다."""
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    check = eval_harness._injected_test_intact_check(scenario, None, offline=True)
    assert check.passed
    assert check.detail == eval_harness.OFFLINE_SKIP_DETAIL


def test_fault_state_check_dispatches_by_fault_kind(eval_harness):
    """즉시 종료 경로 안에서도 결함 유형에 따라 다른 항목을 판정해야 한다."""
    removal = eval_harness._fault_state_check(
        eval_harness.SCENARIOS["harness-eval-003"], None, offline=True
    )
    injection = eval_harness._fault_state_check(
        eval_harness.SCENARIOS["harness-eval-005"], None, offline=True
    )
    assert removal.name == "삭제된 런타임 리소스가 복구되지 않음"
    assert injection.name == "주입된 모순 테스트가 그대로 남아 있고 기존 테스트가 변경되지 않음"


# ---------------------------------------------------------------------------
# 예산 미소비 판정
# ---------------------------------------------------------------------------


def test_budget_untouched_checks_present_for_eval_005(eval_harness, tmp_path):
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    assert scenario.verify_budget_untouched is True
    checks = eval_harness._state_json_checks(_run_dir_with_state(tmp_path, scenario), scenario)
    assert _named(checks, "retry_budget == 3").passed
    assert _named(checks, "unknown_retry_used == false").passed
    assert _named(checks, "retry_count == 0").passed
    assert all(check.passed for check in checks), [c for c in checks if not c.passed]


def test_budget_check_fails_when_unknown_retry_was_used(eval_harness, tmp_path):
    """반증: UNKNOWN 재시도를 한 번이라도 썼으면 예산이 온전하지 않다."""
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    run_dir = _run_dir_with_state(tmp_path, scenario, unknown_retry_used=True)
    assert not _named(
        eval_harness._state_json_checks(run_dir, scenario), "unknown_retry_used == false"
    ).passed


def test_budget_check_fails_when_retry_budget_is_not_three(eval_harness, tmp_path):
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    run_dir = _run_dir_with_state(tmp_path, scenario, retry_budget=1)
    assert not _named(
        eval_harness._state_json_checks(run_dir, scenario), "retry_budget == 3"
    ).passed


def test_blocked_reason_check_fails_on_wrong_reason(eval_harness, tmp_path):
    """반증: state.json 의 사유 코드가 다르면 FAIL 이어야 한다."""
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    run_dir = _run_dir_with_state(tmp_path, scenario, blocked_reason="ENVIRONMENT_ERROR")
    assert not _named(
        eval_harness._state_json_checks(run_dir, scenario),
        "blocked_reason == TEST_DEFECT_NEEDS_HUMAN",
    ).passed


def test_attempt_category_check_fails_when_not_test_defect(eval_harness, tmp_path):
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    run_dir = _run_dir_with_state(
        tmp_path,
        scenario,
        attempts=[{"n": 1, "status": "FAIL", "failure_category": "PRODUCT_CODE_DEFECT"}],
    )
    assert not _named(
        eval_harness._state_json_checks(run_dir, scenario), "attempts[0] 이 FAIL / TEST_DEFECT"
    ).passed


# ---------------------------------------------------------------------------
# 시나리오 정의 파일 존재
# ---------------------------------------------------------------------------


def _definition_checks_for(eval_harness, scenario):
    """시나리오 하나만 담긴 `SCENARIOS` 로 정의 check 를 돌린다."""
    original = eval_harness.SCENARIOS
    eval_harness.SCENARIOS = {scenario.scenario_id: scenario}
    try:
        return eval_harness._scenario_definition_checks()
    finally:
        eval_harness.SCENARIOS = original


def test_missing_fault_module_fails_definition_check(eval_harness):
    """반증: 결함 모듈이 없으면 정의 check 가 FAIL 해야 한다."""
    scenario = replace(eval_harness.SCENARIOS["harness-eval-005"], fault="does_not_exist_001")
    checks = _definition_checks_for(eval_harness, scenario)
    assert not _named(checks, "정의 파일이 모두 존재").passed


def test_missing_fixture_fails_definition_check(eval_harness):
    """반증: 설치 fixture 가 없으면 정의 check 가 FAIL 해야 한다."""
    scenario = replace(
        eval_harness.SCENARIOS["harness-eval-005"],
        installs=(("does_not_exist.py", "sample-project/tests/test_coupon.py"),),
    )
    checks = _definition_checks_for(eval_harness, scenario)
    assert not _named(checks, "정의 파일이 모두 존재").passed


def test_eval_005_definition_files_exist(eval_harness, repo_root):
    scenario = eval_harness.SCENARIOS["harness-eval-005"]
    assert (repo_root / scenario.task).is_file()
    assert (repo_root / "evals" / "faults" / "test_defect_001.py").is_file()
    for fixture_name, _ in scenario.installs:
        assert (repo_root / "evals" / "fixtures" / fixture_name).is_file()


def test_eval_005_installs_do_not_collide_with_other_scenarios(eval_harness):
    """설치 경로가 겹치면 시나리오끼리 서로의 fixture 를 덮어쓴다."""
    targets = {target for _, target in eval_harness.SCENARIOS["harness-eval-005"].installs}
    others = {
        target
        for scenario_id, scenario in eval_harness.SCENARIOS.items()
        if scenario_id != "harness-eval-005"
        for _, target in scenario.installs
    }
    assert not (targets & others)
