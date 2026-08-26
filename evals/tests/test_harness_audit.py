"""`evals/harness_audit.py` 자기 검증.

핵심 규율은 하나다.

    **모든 check 는 FAIL 을 만들어내는 테스트를 가진다.**

FAIL 시킬 수 없는 check 는 반증 불가능한 check 이고, 반증 불가능한 check 는 점수가
아니라 장식이다. 자기가 만든 저장소를 자기가 채점하는 도구에서 이것은 타협할 수 없다.
`test_every_check_has_a_falsifying_case` 가 33개 전부에 반증 사례가 있는지 강제한다.

fixture 구성

* `audit_baseline` — 실제 저장소의 감사 대상 파일만 복사한 뒤, 계약을 **전부**
  만족하도록 두 가지를 더한 세션 1회 baseline 이다. (CI 워크플로, 나머지 종료 경로
  시나리오) 100/100 PASS 가 나와야 한다.
* `audit_repo` — 테스트마다 baseline 을 복사한 사본. 여기에만 변형을 가한다.

실제 저장소는 어떤 테스트에서도 수정하지 않는다. 읽기만 한다.

실제 저장소의 점수는 골든으로 고정하지 않는다. 저장소가 정당하게 바뀔 때마다 깨지는
골든은 노이즈다. `test_real_repository_smoke` 는 결과를 보고만 하고 점수를 단정하지
않는다.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# baseline 구성
# ---------------------------------------------------------------------------

# 감사 대상이 되는 파일만 복사한다. 저장소 전체를 복사하지 않는 이유는 두 가지다.
# 복사 비용을 줄이고, "Audit 이 무엇을 읽는가" 를 이 목록으로 드러내기 위해서다.
COPY_FILES = (
    "CLAUDE.md",
    "README.md",
    ".gitignore",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    ".claude/settings.json",
    ".claude/commands/patchpilot.md",
    "evals/eval_harness.py",
    "dashboard/lib/types.ts",
    "dashboard/lib/parse.ts",
)

COPY_TREES = (
    ".claude/agents",
    ".claude/hooks",
    "evals/fixtures",
    "evals/faults",
    "evals/tests",
    "reports/examples",
    # F1 이 `CLAUDE.md §22` 의 완료 항목에서 `sample-project/` 와
    # `sample-project/tests/` 를 경로로 읽는다. 감사 대상이므로 함께 복사한다.
    "sample-project",
    "tasks",
)

# G1 이 요구하는 세 검증기를 모두 부르는 워크플로. 실제 저장소에는 아직 없다.
CI_WORKFLOW = """name: verify
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv run pytest evals/tests -q
      - run: uv run python evals/eval_harness.py selftest
      - run: uv run python evals/harness_audit.py
"""

# baseline 이 종료 경로 7개를 모두 덮게 만드는 시나리오 추가분.
# 실제 저장소에는 아직 없는 세 경로다. E4b 의 PASS 분기를 baseline 에서 실행하고,
# 변형 테스트가 그 분기를 무너뜨리는 것을 볼 수 있게 한다.
BASELINE_SCENARIO_PATCH = '''

# --- evals/tests/test_harness_audit.py baseline 전용 추가분 ---
for _audit_sid, _audit_reason in (
    ("harness-eval-901", "TEST_DEFECT_NEEDS_HUMAN"),
    ("harness-eval-902", "UNKNOWN_TWICE"),
    ("harness-eval-903", "REVIEW_CHANGES_REQUESTED_NO_BUDGET"),
):
    SCENARIOS[_audit_sid] = Scenario(
        scenario_id=_audit_sid,
        task="evals/fixtures/HARNESS-EVAL-001.md",
        fault="retry_001",
        installs=(),
        expected_category="UNKNOWN",
        expected_failing_token="audit-fixture",
        transition="audit fixture",
        outcome=OUTCOME_BLOCKED,
        expected_blocked_reason=_audit_reason,
    )
'''

BASELINE_SCORE = 100
BASELINE_VERDICT = "PASS"

# 변형 대상으로 고르는 보존된 대표 결과. SUCCESS 한 건과 BLOCKED 한 건이 필요하다.
SUCCESS_EXAMPLE = "EVAL-20260820-1318-HARNESS-EVAL-001"
BLOCKED_EXAMPLE = "EVAL-20260820-1554-HARNESS-EVAL-003"


def _materialize(source: Path, dest: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for relative in COPY_FILES:
        target = dest.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.joinpath(*relative.split("/")), target)
    for relative in COPY_TREES:
        shutil.copytree(
            source.joinpath(*relative.split("/")),
            dest.joinpath(*relative.split("/")),
            ignore=ignore,
        )


@pytest.fixture(scope="session")
def audit_baseline(tmp_path_factory, repo_root: Path) -> Path:
    """계약을 전부 만족하는 저장소. 세션당 한 번만 만든다."""
    dest = tmp_path_factory.mktemp("audit") / "baseline"
    dest.mkdir()
    _materialize(repo_root, dest)

    workflow = dest / ".github" / "workflows" / "verify.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(CI_WORKFLOW, encoding="utf-8")

    harness = dest / "evals" / "eval_harness.py"
    harness.write_text(
        harness.read_text(encoding="utf-8") + BASELINE_SCENARIO_PATCH, encoding="utf-8"
    )
    return dest


@pytest.fixture
def audit_repo(audit_baseline: Path, tmp_path: Path) -> Path:
    """이 테스트에서만 쓰는 baseline 사본. 실제 저장소는 건드리지 않는다."""
    dest = tmp_path / "repo"
    shutil.copytree(audit_baseline, dest)
    return dest


# ---------------------------------------------------------------------------
# 변형 도우미
# ---------------------------------------------------------------------------


def read(root: Path, relative: str) -> str:
    return root.joinpath(*relative.split("/")).read_text(encoding="utf-8")


def write(root: Path, relative: str, body: str) -> None:
    root.joinpath(*relative.split("/")).write_text(body, encoding="utf-8")


def edit(root: Path, relative: str, old: str, new: str) -> None:
    """정확 문자열 치환. 대상이 없으면 fixture 가 실제 저장소와 어긋난 것이다."""
    body = read(root, relative)
    if old not in body:
        raise AssertionError("{0} 에서 치환 대상을 찾지 못했습니다: {1!r}".format(relative, old))
    write(root, relative, body.replace(old, new))


def remove(root: Path, relative: str) -> None:
    target = root.joinpath(*relative.split("/"))
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def load_json(root: Path, relative: str):
    return json.loads(read(root, relative))


def dump_json(root: Path, relative: str, document) -> None:
    write(root, relative, json.dumps(document, ensure_ascii=False, indent=2))


def patch_state(root: Path, example: str, **values) -> None:
    relative = "reports/examples/{0}/state.json".format(example)
    state = load_json(root, relative)
    state.update(values)
    dump_json(root, relative, state)


def drop_line(root: Path, relative: str, needle: str) -> None:
    body = read(root, relative)
    kept = [line for line in body.splitlines() if needle not in line]
    if len(kept) == len(body.splitlines()):
        raise AssertionError("{0} 에서 삭제할 줄을 찾지 못했습니다: {1!r}".format(relative, needle))
    write(root, relative, "\n".join(kept) + "\n")


def failing_ids(report: dict) -> set[str]:
    return {
        check["id"]
        for category in report["categories"]
        for check in category["checks"]
        if check["result"] == "FAIL"
    }


def check_of(report: dict, check_id: str) -> dict:
    for category in report["categories"]:
        for check in category["checks"]:
            if check["id"] == check_id:
                return check
    raise AssertionError("rubric 에 없는 check id: {0}".format(check_id))


# ---------------------------------------------------------------------------
# 개별 변형
# ---------------------------------------------------------------------------


def _delete_agent(root: Path) -> None:
    remove(root, ".claude/agents/planner.md")


def _grant_developer_bash(root: Path) -> None:
    edit(
        root,
        ".claude/agents/developer.md",
        "tools: Read, Grep, Glob, Edit, Write",
        "tools: Read, Grep, Glob, Edit, Write, Bash",
    )


def _delete_guard_file(root: Path) -> None:
    remove(root, ".claude/hooks/guard_bash_scope.py")


def _drift_hook_id(root: Path) -> None:
    edit(
        root,
        ".claude/hooks/guard_plan_scope.py",
        'HOOK_ID = "guard-plan-scope"',
        'HOOK_ID = "plan-scope"',
    )


def _unregister_guard(root: Path) -> None:
    settings = load_json(root, ".claude/settings.json")
    settings["hooks"]["PreToolUse"] = [
        entry
        for entry in settings["hooks"]["PreToolUse"]
        if not any(
            "guard_bash_scope" in hook.get("command", "") for hook in entry.get("hooks", [])
        )
    ]
    dump_json(root, ".claude/settings.json", settings)


def _flatten_stop_hook(root: Path) -> None:
    """평면형 등록. 파싱 오류 없이 조용히 무시되는 무증상 실패 모드다."""
    settings = load_json(root, ".claude/settings.json")
    nested = settings["hooks"]["Stop"][0]["hooks"]
    settings["hooks"]["Stop"] = nested
    dump_json(root, ".claude/settings.json", settings)


def _delete_guard_test(root: Path) -> None:
    remove(root, "evals/tests/test_guard_plan_scope.py")


def _drift_failure_categories(root: Path) -> None:
    drop_line(root, "dashboard/lib/types.ts", "  'UNKNOWN',")


def _drift_blocked_reasons(root: Path) -> None:
    edit(root, ".claude/commands/patchpilot.md", "\nUNKNOWN_TWICE\n", "\n")


def _drift_pytest_command(root: Path) -> None:
    edit(
        root,
        ".claude/agents/tester.md",
        "uv run pytest sample-project/tests -q",
        "uv run pytest sample-project/tests",
    )


def _drift_retry_budget(root: Path) -> None:
    edit(root, ".claude/commands/patchpilot.md", '"retry_budget": 3', '"retry_budget": 5')


def _drift_machine_token(root: Path) -> None:
    body = read(root, "dashboard/lib/parse.ts")
    write(root, "dashboard/lib/parse.ts", body + "\n// STATUS: DONE\n")


def _delete_example_report(root: Path) -> None:
    remove(root, "reports/examples/{0}/report.md".format(SUCCESS_EXAMPLE))


def _drift_blocked_reason_value(root: Path) -> None:
    patch_state(root, BLOCKED_EXAMPLE, blocked_reason="NOT_A_REAL_REASON")


def _drift_current_stage(root: Path) -> None:
    patch_state(root, SUCCESS_EXAMPLE, current_stage="TESTING")


def _drift_eval_verdict(root: Path) -> None:
    relative = "reports/examples/{0}/eval-result.md".format(SUCCESS_EXAMPLE)
    edit(root, relative, "EVAL: PASS", "EVAL: FAIL")


def _drift_gitignore(root: Path) -> None:
    drop_line(root, ".gitignore", "!reports/examples/**")


def _delete_scenario_task(root: Path) -> None:
    remove(root, "evals/fixtures/HARNESS-EVAL-002.md")


def _delete_regression_example(root: Path) -> None:
    remove(root, "reports/examples/{0}".format(BLOCKED_EXAMPLE))


def _drift_eval_summary(root: Path) -> None:
    relative = "reports/examples/{0}/eval-result.md".format(SUCCESS_EXAMPLE)
    body = read(root, relative)
    write(root, relative, re.sub(r"\d+/(\d+) 항목 통과", r"1/\1 항목 통과", body))


def _shrink_route_coverage(root: Path) -> None:
    relative = "evals/eval_harness.py"
    write(
        root,
        relative,
        read(root, relative)
        + "\nfor _drop in [k for k in SCENARIOS if k not in"
        ' ("harness-eval-001", "harness-eval-002")]:\n    del SCENARIOS[_drop]\n',
    )


def _delete_fault_module(root: Path) -> None:
    remove(root, "evals/faults/retry_001.py")


def _repeat_chained_fault(root: Path) -> None:
    relative = "evals/eval_harness.py"
    write(
        root,
        relative,
        read(root, relative)
        + "\nimport dataclasses as _dc\n"
        'SCENARIOS["harness-eval-004"] = _dc.replace(\n'
        '    SCENARIOS["harness-eval-004"],\n'
        '    fault_sequence=("retry_budget_001", "retry_budget_001", "retry_budget_003"),\n'
        ")\n",
    )


def _drift_todo_checklist(root: Path) -> None:
    edit(root, "CLAUDE.md", "(`guard_stop_gate.py`, §25)", "(`guard_absent.py`, §25)")


def _drop_readme_hook_row(root: Path) -> None:
    drop_line(root, "README.md", "| `guard_bash_scope.py` |")


def _drift_readme_tools(root: Path) -> None:
    edit(
        root,
        "README.md",
        "| Planner | `Read` `Grep` `Glob` `Write` |",
        "| Planner | `Read` `Grep` `Glob` `Write` `Bash` |",
    )


def _drift_gid_claim(root: Path) -> None:
    edit(root, "README.md", "G1~G19", "G1~G21")


def _delete_ci_workflow(root: Path) -> None:
    remove(root, ".github/workflows/verify.yml")


def _delete_uv_lock(root: Path) -> None:
    remove(root, "uv.lock")


def _tamper_rubric(rubric):
    """배점을 몰래 1점 올린다. rubric_digest 가 이것을 잡아야 한다."""
    return tuple(
        replace(spec, max_score=spec.max_score + 1) if spec.id == "A1" else spec
        for spec in rubric
    )


# ---------------------------------------------------------------------------
# 반증 사례 표
#
# `targets` 는 이 사례가 **떨어뜨리려고 만든** check 다. 변형이 다른 check 까지
# 연쇄로 떨어뜨리는 것은 정상이므로 부분집합으로 확인한다.
# `gates` 가 비어 있으면 Critical 이 하나도 없어야 한다는 뜻이다.
# 여기서 지키는 기준선: **거짓말이면 Critical, 미완성이면 감점.**
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    id: str
    targets: tuple[str, ...]
    gates: tuple[str, ...] = ()
    mutate: object = None
    rubric: object = None


CASES = (
    # 정의 파일이 없는 것은 미완성이다. 최소 권한 주장이 거짓이 된 것이 아니므로
    # Critical 이 아니다. (A3 는 남아 있는 Agent 만 판정한다)
    Case("agent-file-missing", ("A1", "A2", "A4", "F3"), mutate=_delete_agent),
    # Developer 가 Bash 를 얻으면 "테스트를 실행할 수 없다" 는 주장이 거짓이 된다.
    Case(
        "developer-gains-bash",
        ("A3", "F3"),
        ("ROLE_PRIVILEGE_DRIFT",),
        mutate=_grant_developer_bash,
    ),
    Case(
        "guard-file-missing",
        ("B1", "B2", "B3"),
        ("GUARD_NOT_ENFORCED",),
        mutate=_delete_guard_file,
    ),
    Case("hook-id-drift", ("B2",), mutate=_drift_hook_id),
    Case(
        "guard-unregistered",
        ("B3", "F2"),
        ("GUARD_NOT_ENFORCED",),
        mutate=_unregister_guard,
    ),
    Case(
        "stop-hook-flat",
        ("B4",),
        ("STOP_GATE_SHAPE_INVALID", "GUARD_NOT_ENFORCED"),
        mutate=_flatten_stop_hook,
    ),
    Case("guard-test-missing", ("B5",), mutate=_delete_guard_test),
    Case(
        "failure-category-drift",
        ("C1",),
        ("CONTRACT_DIVERGENCE",),
        mutate=_drift_failure_categories,
    ),
    Case(
        "blocked-reason-drift",
        ("C2",),
        ("CONTRACT_DIVERGENCE",),
        mutate=_drift_blocked_reasons,
    ),
    Case("pytest-command-drift", ("C3",), mutate=_drift_pytest_command),
    Case("retry-budget-drift", ("C4",), mutate=_drift_retry_budget),
    Case("machine-token-drift", ("C5",), mutate=_drift_machine_token),
    Case(
        "example-report-missing",
        ("D1", "D3"),
        ("EVIDENCE_INVALID",),
        mutate=_delete_example_report,
    ),
    Case(
        "example-blocked-reason-invalid",
        ("D2", "D3"),
        ("EVIDENCE_INVALID",),
        mutate=_drift_blocked_reason_value,
    ),
    Case(
        "example-stage-not-done",
        ("D3",),
        ("EVIDENCE_INVALID",),
        mutate=_drift_current_stage,
    ),
    Case("example-eval-fail", ("D4",), ("EVIDENCE_INVALID",), mutate=_drift_eval_verdict),
    Case("gitignore-drift", ("D5",), mutate=_drift_gitignore),
    Case("scenario-task-missing", ("E1",), mutate=_delete_scenario_task),
    Case("regression-example-missing", ("E2",), mutate=_delete_regression_example),
    Case("eval-summary-drift", ("E3",), mutate=_drift_eval_summary),
    # 종료 경로 미비는 미완성이다. 감점이지 게이트가 아니다.
    Case("route-coverage-shrunk", ("E4a", "E4b"), mutate=_shrink_route_coverage),
    Case("fault-module-missing", ("E5",), mutate=_delete_fault_module),
    Case("chained-fault-repeated", ("E6",), mutate=_repeat_chained_fault),
    Case("todo-checklist-drift", ("F1",), mutate=_drift_todo_checklist),
    Case("readme-hook-row-missing", ("F2",), mutate=_drop_readme_hook_row),
    Case("readme-tools-drift", ("F3",), mutate=_drift_readme_tools),
    Case("readme-gid-claim-drift", ("F4",), mutate=_drift_gid_claim),
    Case("ci-workflow-missing", ("G1",), mutate=_delete_ci_workflow),
    Case("uv-lock-missing", ("G2",), mutate=_delete_uv_lock),
    Case("rubric-tampered", ("G3",), rubric=_tamper_rubric),
)


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------


def test_baseline_fixture_satisfies_the_whole_contract(harness_audit, audit_repo):
    report = harness_audit.run_audit(audit_repo)
    assert failing_ids(report) == set()
    assert report["score"] == BASELINE_SCORE
    assert report["max_score"] == harness_audit.MAX_SCORE
    assert report["verdict"] == BASELINE_VERDICT
    assert report["critical_failures"] == []
    assert report["next_actions"] == []


def test_rubric_shape_is_the_declared_contract(harness_audit):
    rubric = harness_audit.RUBRIC
    assert len(rubric) == 33
    assert sum(spec.max_score for spec in rubric) == harness_audit.MAX_SCORE
    assert sorted(spec.id for spec in rubric if spec.critical) == [
        "A3",
        "B3",
        "B4",
        "C1",
        "C2",
        "D3",
        "D4",
    ]
    expected = {
        "agent-isolation": 13,
        "guard-enforcement": 20,
        "contract-consistency": 19,
        "artifact-evidence": 13,
        "eval-coverage": 17,
        "doc-consistency": 10,
        "automation": 8,
    }
    actual = {}
    for spec in rubric:
        actual[spec.category] = actual.get(spec.category, 0) + spec.max_score
    assert actual == expected


def test_rubric_version_is_pinned(harness_audit):
    assert harness_audit.RUBRIC_VERSION == "1.0.0"
    assert harness_audit.AUDIT_VERSION == "1.0.0"
    assert harness_audit.SCHEMA_VERSION == 1
    assert harness_audit.rubric_digest() == harness_audit.RUBRIC_DIGEST


def test_every_check_is_binary(harness_audit, audit_repo):
    """부분 점수는 없다. PASS 면 만점, FAIL 이면 0점이다."""
    report = harness_audit.run_audit(audit_repo)
    for category in report["categories"]:
        for check in category["checks"]:
            expected = check["max_score"] if check["result"] == "PASS" else 0
            assert check["score"] == expected, check["id"]


# ---------------------------------------------------------------------------
# 반증 — 모든 check 는 떨어뜨릴 수 있어야 한다
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_case_falsifies_its_target_checks(harness_audit, audit_repo, case):
    if case.mutate is not None:
        case.mutate(audit_repo)
    rubric = case.rubric(harness_audit.RUBRIC) if case.rubric else harness_audit.RUBRIC

    report = harness_audit.run_audit(audit_repo, rubric)
    failing = failing_ids(report)
    assert set(case.targets) <= failing, "기대한 FAIL 이 나오지 않았습니다: {0}".format(
        sorted(set(case.targets) - failing)
    )
    for check_id in case.targets:
        check = check_of(report, check_id)
        assert check["score"] == 0
        assert check["evidence"], "FAIL 인데 근거가 비어 있습니다: {0}".format(check_id)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_case_gate_classification(harness_audit, audit_repo, case):
    """거짓말이면 Critical, 미완성이면 감점 — 그 분류가 유지되는가."""
    if case.mutate is not None:
        case.mutate(audit_repo)
    rubric = case.rubric(harness_audit.RUBRIC) if case.rubric else harness_audit.RUBRIC

    report = harness_audit.run_audit(audit_repo, rubric)
    gates = {failure["gate"] for failure in report["critical_failures"]}
    assert gates == set(case.gates)
    assert report["verdict"] == ("FAIL" if case.gates else "PASS")


def test_every_check_has_a_falsifying_case(harness_audit):
    """반증 사례가 없는 check 는 점수가 아니라 장식이다."""
    covered = {check_id for case in CASES for check_id in case.targets}
    declared = {spec.id for spec in harness_audit.RUBRIC}
    assert declared - covered == set(), "반증 사례가 없는 check: {0}".format(
        sorted(declared - covered)
    )
    assert covered - declared == set()


# ---------------------------------------------------------------------------
# 결정론
# ---------------------------------------------------------------------------


def test_same_input_produces_byte_identical_json(harness_audit, audit_repo):
    first = harness_audit.to_json(harness_audit.run_audit(audit_repo))
    second = harness_audit.to_json(harness_audit.run_audit(audit_repo))
    assert first == second


def test_json_carries_no_time_or_git_provenance(harness_audit, audit_repo):
    """시각·git SHA 를 넣는 순간 파일 내용의 순수 함수가 아니게 된다."""
    body = harness_audit.to_json(harness_audit.run_audit(audit_repo))
    for forbidden in ("generated_at", "timestamp", "commit", "git_sha", "created"):
        assert forbidden not in body


def test_json_carries_no_absolute_paths(harness_audit, audit_repo):
    body = harness_audit.to_json(harness_audit.run_audit(audit_repo))
    assert str(audit_repo) not in body
    assert str(audit_repo.as_posix()) not in body


def test_unrelated_files_do_not_move_the_score(harness_audit, audit_repo):
    """와일드카드 스캔이 없다는 증거. 무관한 파일은 점수에 영향을 주지 않는다."""
    before = harness_audit.to_json(harness_audit.run_audit(audit_repo))
    (audit_repo / "NOTES.txt").write_text("메모", encoding="utf-8")
    (audit_repo / "scratch.md").write_text("# 초안\n", encoding="utf-8")
    (audit_repo / ".claude" / "hooks" / "README.md").write_text("설명\n", encoding="utf-8")
    (audit_repo / "evals" / "faults" / "notes.txt").write_text("메모\n", encoding="utf-8")
    assert harness_audit.to_json(harness_audit.run_audit(audit_repo)) == before


def test_rubric_declaration_order_does_not_change_the_result(harness_audit, audit_repo):
    """선언 순서는 표현일 뿐 계약이 아니다. 총점도 digest 도 바뀌면 안 된다."""
    forward = harness_audit.run_audit(audit_repo, harness_audit.RUBRIC)
    reversed_rubric = tuple(reversed(harness_audit.RUBRIC))
    backward = harness_audit.run_audit(audit_repo, reversed_rubric)
    assert harness_audit.rubric_digest(reversed_rubric) == harness_audit.RUBRIC_DIGEST
    assert harness_audit.to_json(backward) == harness_audit.to_json(forward)


def test_json_schema_envelope(harness_audit, audit_repo):
    report = harness_audit.run_audit(audit_repo)
    assert set(report) == {
        "schema_version",
        "audit_version",
        "rubric_version",
        "rubric_digest",
        "verdict",
        "score",
        "max_score",
        "categories",
        "critical_failures",
        "warnings",
        "next_actions",
    }
    assert [category["id"] for category in report["categories"]] == [
        category_id for category_id, _title in harness_audit.CATEGORIES
    ]
    for category in report["categories"]:
        ids = [check["id"] for check in category["checks"]]
        assert ids == sorted(ids)
        for check in category["checks"]:
            assert set(check) == {
                "id",
                "title",
                "result",
                "score",
                "max_score",
                "critical",
                "contract",
                "evidence",
                "remediation",
            }
            assert check["contract"]
            assert check["remediation"]


def test_next_actions_are_sorted_critical_first(harness_audit, audit_repo):
    _delete_guard_file(audit_repo)
    _delete_ci_workflow(audit_repo)
    report = harness_audit.run_audit(audit_repo)
    order = [
        (not action["critical"], -action["max_score"], action["check_id"])
        for action in report["next_actions"]
    ]
    assert order == sorted(order)
    assert report["next_actions"][0]["check_id"] == "B3"


# ---------------------------------------------------------------------------
# 판단 불가 — 검사 FAIL 과 Audit 실행 오류의 구분
# ---------------------------------------------------------------------------


def test_broken_settings_json_is_an_execution_error(harness_audit, audit_repo):
    """정상적으로 읽은 settings 에서 guard 누락은 FAIL. 깨진 JSON 은 실행 오류다."""
    write(audit_repo, ".claude/settings.json", "{ this is not json")
    with pytest.raises(harness_audit.AuditError):
        harness_audit.run_audit(audit_repo)


def test_broken_frontmatter_is_an_execution_error(harness_audit, audit_repo):
    body = read(audit_repo, ".claude/agents/tester.md")
    write(audit_repo, ".claude/agents/tester.md", body.replace("---", "", 1))
    with pytest.raises(harness_audit.AuditError):
        harness_audit.run_audit(audit_repo)


def test_missing_root_is_an_execution_error(harness_audit, tmp_path):
    with pytest.raises(harness_audit.AuditError):
        harness_audit.run_audit(tmp_path / "does-not-exist")


def test_missing_file_is_a_check_failure_not_an_execution_error(harness_audit, audit_repo):
    remove(audit_repo, ".claude/agents/reviewer.md")
    report = harness_audit.run_audit(audit_repo)
    assert "A1" in failing_ids(report)


# ---------------------------------------------------------------------------
# 보존된 증거 — 현재 계약을 옛 증거에 소급 적용하지 않는다
# ---------------------------------------------------------------------------


def test_preserved_examples_have_no_session_id(repo_root: Path):
    """대표 결과는 Stop Gate 도입 전에 승격되었으므로 `session_id` 키가 없다.

    이 사실이 깨지면 아래 회귀 테스트의 전제가 사라진다. 먼저 사실을 고정한다.
    """
    examples = sorted((repo_root / "reports" / "examples").iterdir())
    assert examples
    for example in examples:
        state = json.loads((example / "state.json").read_text(encoding="utf-8"))
        assert "session_id" not in state, example.name


def test_absent_session_id_fails_no_check(harness_audit, audit_repo):
    """승격 이후 도입된 필드를 옛 증거에 요구하지 않는다.

    현재 계약을 소급 적용하면 정상 저장소에 첫 실행부터 Critical 이 4건 뜬다.
    `session_id` 는 Audit 의 어떤 판정에도 들어가서는 안 된다.
    """
    base = audit_repo / "reports" / "examples"
    for example in sorted(base.iterdir()):
        state = json.loads((example / "state.json").read_text(encoding="utf-8"))
        assert "session_id" not in state

    report = harness_audit.run_audit(audit_repo)
    for check_id in ("D1", "D2", "D3", "D4", "D5"):
        assert check_of(report, check_id)["result"] == "PASS", check_id

    # 값이 생겨도 판정이 달라지면 안 된다. 검사 대상이 아니기 때문이다.
    before = harness_audit.to_json(report)
    for example in sorted(base.iterdir()):
        relative = "reports/examples/{0}/state.json".format(example.name)
        state = load_json(audit_repo, relative)
        state["session_id"] = "0000-session"
        dump_json(audit_repo, relative, state)
    assert harness_audit.to_json(harness_audit.run_audit(audit_repo)) == before


def test_d3_replays_the_real_stop_gate_not_a_copy(harness_audit, audit_repo, monkeypatch):
    """D3 는 판정을 재구현하지 않는다. `check_run()` 을 실제로 호출한다.

    가드의 판정 함수를 호출하지 않도록 막으면 D3 가 통과할 수 없어야 한다. 통과한다면
    Audit 안에 두 번째 파서가 생긴 것이다.
    """
    repo = harness_audit.Repo(audit_repo)
    gate = repo.stop_gate()
    assert hasattr(gate, "check_run")

    calls = []
    original = gate.check_run

    def spy(state, run_dir):
        calls.append(run_dir.name)
        return original(state, run_dir)

    monkeypatch.setattr(gate, "check_run", spy)
    outcome = harness_audit.check_d3(repo)
    assert outcome.passed
    assert sorted(calls) == repo.example_dirs()


# ---------------------------------------------------------------------------
# Stop Gate 회귀 — check_run() 추가로 decide() 가 달라지지 않았는가
# ---------------------------------------------------------------------------


def _stop_payload(session_id: str) -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "stop_hook_active": False,
    }


@pytest.mark.parametrize(
    "final_status, blocked_reason, expect_block",
    [
        ("SUCCESS", None, False),
        ("BLOCKED", "ENVIRONMENT_ERROR", False),
        ("BLOCKED", "NOT_A_REASON", True),
    ],
)
def test_decide_and_check_run_share_one_judgement_path(
    guard_stop_gate, fake_root, final_status, blocked_reason, expect_block
):
    """`decide()` 의 차단 여부가 `check_run()` 의 위반 유무와 정확히 같은 경계인가."""
    run_dir = fake_root / "reports" / "RUN-20260825-0900-BUG-001"
    run_dir.mkdir(parents=True)
    state = {
        "run_id": run_dir.name,
        "session_id": "session-under-test",
        "status": final_status,
        "current_stage": "DONE",
        "retry_count": 0,
        "retry_budget": 3,
        "finished_at": "20260825-0930",
        "attempts": [
            {
                "n": 1,
                "change_log": "change-log-1.md",
                "test_result": "test-result-1.md",
                "status": "PASS" if final_status == "SUCCESS" else "FAIL",
            }
        ],
        "review": {"verdict": "APPROVED" if final_status == "SUCCESS" else None},
        "final_status": final_status,
        "blocked_reason": blocked_reason,
    }
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (run_dir / "report.md").write_text("# report\n", encoding="utf-8")
    (run_dir / "change-log-1.md").write_text("# change log\n", encoding="utf-8")
    (run_dir / "test-result-1.md").write_text(
        "STATUS: PASS\n" if final_status == "SUCCESS" else "STATUS: FAIL\n", encoding="utf-8"
    )
    (run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    (run_dir / "review.md").write_text(
        "VERDICT: APPROVED\n" if final_status == "SUCCESS" else "VERDICT: CHANGES_REQUESTED\n",
        encoding="utf-8",
    )

    result = guard_stop_gate.check_run(state, run_dir)
    decision, reason, _notes = guard_stop_gate.decide(
        _stop_payload("session-under-test"), fake_root
    )

    assert bool(result.violations) is expect_block
    assert (decision == guard_stop_gate.DECISION_BLOCK) is expect_block
    if expect_block:
        for violation in result.violations:
            assert "[{0}]".format(violation.gid) in reason
    else:
        assert reason is None


def test_check_run_writes_nothing_and_is_pure(guard_stop_gate, repo_root: Path):
    """보존된 대표 결과를 replay 해도 저장소 상태가 변하지 않는다."""
    base = repo_root / "reports" / "examples"
    before = sorted((path.name, path.stat().st_size) for path in base.rglob("*") if path.is_file())
    for example in sorted(base.iterdir()):
        state = json.loads((example / "state.json").read_text(encoding="utf-8"))
        first = guard_stop_gate.check_run(state, example)
        second = guard_stop_gate.check_run(state, example)
        assert first.violations == second.violations == []
        assert first.notes == second.notes
    after = sorted((path.name, path.stat().st_size) for path in base.rglob("*") if path.is_file())
    assert before == after


# ---------------------------------------------------------------------------
# 실제 저장소 smoke — 점수를 골든으로 고정하지 않는다
# ---------------------------------------------------------------------------


def test_real_repository_smoke(harness_audit, repo_root: Path, capsys):
    """실제 저장소를 읽기 전용으로 1회 감사하고 결과를 보고만 한다.

    점수를 assertion 으로 고정하지 않는다. 저장소가 정당하게 바뀔 때마다 깨지는
    골든은 노이즈이고, 그런 골든이 있으면 저장소를 고치는 대신 골든을 고치게 된다.
    고정하는 것은 rubric 의 동일성이다.
    """
    report = harness_audit.run_audit(repo_root)
    assert report["verdict"] in ("PASS", "FAIL")
    assert report["max_score"] == harness_audit.MAX_SCORE
    assert report["rubric_digest"] == harness_audit.RUBRIC_DIGEST

    with capsys.disabled():
        print()
        print(
            "[harness-audit] {0} {1}/{2} · critical {3}".format(
                report["verdict"],
                report["score"],
                report["max_score"],
                len(report["critical_failures"]),
            )
        )
        for category in report["categories"]:
            failed = [
                check["id"] for check in category["checks"] if check["result"] == "FAIL"
            ]
            print(
                "  {0:<22} {1:>3}/{2:<3} {3}".format(
                    category["id"],
                    category["score"],
                    category["max_score"],
                    "FAIL: " + ", ".join(failed) if failed else "",
                )
            )


# ---------------------------------------------------------------------------
# CLI
#
# CLI 는 `run_audit()` 위의 얇은 층이어야 한다. 여기서 고정하는 것은 두 가지다.
#
#   1. 종료 코드 계약 (0 PASS / 1 FAIL / 2 실행 오류) — CI 가 이것에 의존한다.
#   2. 렌더러가 판정을 새로 하지 않는다 — 세 형식의 verdict 는 항상 같다.
#
# 특히 `--min-score` 는 verdict 만 내리고 `critical_failures` 는 건드리지 않는다.
# 임계값 미달을 Critical 로 위장하면 Hard Gate 목록이 호출자 인자에 오염된다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliResult:
    code: int
    out: str
    err: str


@pytest.fixture
def cli(harness_audit, capsys):
    """`main()` 을 프로세스 없이 호출하고 종료 코드와 스트림을 함께 돌려준다."""

    def run(*argv: str) -> CliResult:
        code = harness_audit.main(list(argv))
        captured = capsys.readouterr()
        return CliResult(code, captured.out, captured.err)

    return run


def audit_files(root: Path) -> list[str]:
    base = root / "reports" / "audit"
    if not base.is_dir():
        return []
    return sorted(path.relative_to(base).as_posix() for path in base.rglob("*"))


def reports_snapshot(root: Path) -> dict[str, bytes]:
    base = root / "reports"
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in base.rglob("*")
        if path.is_file()
    }


def test_default_format_is_text(cli, audit_repo, harness_audit):
    result = cli("--root", str(audit_repo))
    assert result.code == 0
    lines = result.out.splitlines()
    assert lines[0] == "AUDIT: PASS"
    assert "Score: {0} / 100".format(BASELINE_SCORE) in lines
    assert "Critical: 0" in lines
    assert "Rubric: " + harness_audit.RUBRIC_VERSION in lines
    assert "Digest: " + harness_audit.RUBRIC_DIGEST in lines
    for _category_id, title in harness_audit.CATEGORIES:
        assert any(line.startswith("- {0}:".format(title)) for line in lines), title


def test_json_format_is_only_json_on_stdout(cli, audit_repo, harness_audit):
    result = cli("--root", str(audit_repo), "--format", "json")
    assert result.code == 0
    assert result.err == ""
    document = json.loads(result.out)
    assert result.out == harness_audit.to_json(harness_audit.run_audit(audit_repo))
    assert document["verdict"] == BASELINE_VERDICT
    assert document["score"] == BASELINE_SCORE


def test_markdown_format_declares_the_verdict_on_the_first_line(cli, audit_repo):
    result = cli("--root", str(audit_repo), "--format", "markdown")
    assert result.code == 0
    lines = result.out.splitlines()
    assert lines[0] == "AUDIT: PASS"
    for heading in (
        "# PatchPilot Harness Audit",
        "## 종합",
        "## Critical Hard Gate",
        "## Category 요약",
        "## Check 상세",
        "## 다음 행동",
        "## 경고 (점수 미반영)",
        "## Audit이 검사하지 않는 것",
    ):
        assert heading in lines, heading


def test_every_check_appears_in_the_markdown_detail(cli, audit_repo, harness_audit):
    result = cli("--root", str(audit_repo), "--format", "markdown")
    for spec in harness_audit.RUBRIC:
        assert "#### {0} - ".format(spec.id) in result.out, spec.id


def test_three_formats_never_disagree_on_the_verdict(cli, audit_repo):
    """렌더러가 판정을 새로 하지 않는다는 증거. 형식만 다르고 결론은 하나다."""
    _unregister_guard(audit_repo)
    verdicts = set()
    codes = set()
    for output_format in ("text", "json", "markdown"):
        result = cli("--root", str(audit_repo), "--format", output_format)
        codes.add(result.code)
        first = result.out.splitlines()[0]
        verdicts.add(
            json.loads(result.out)["verdict"]
            if output_format == "json"
            else first[len("AUDIT: ") :]
        )
    assert verdicts == {"FAIL"}
    assert codes == {1}


def test_unknown_format_is_an_execution_error(cli, audit_repo):
    result = cli("--root", str(audit_repo), "--format", "yaml")
    assert result.code == 2
    assert result.out == ""


def test_unknown_flag_is_an_execution_error(cli, audit_repo):
    assert cli("--root", str(audit_repo), "--nope").code == 2


def test_non_integer_min_score_is_an_execution_error(cli, audit_repo):
    assert cli("--root", str(audit_repo), "--min-score", "high").code == 2


def test_help_exits_zero(cli):
    result = cli("--help")
    assert result.code == 0
    assert "--min-score" in result.out


def test_critical_failure_exits_one(cli, audit_repo):
    _unregister_guard(audit_repo)
    result = cli("--root", str(audit_repo), "--format", "json")
    assert result.code == 1
    document = json.loads(result.out)
    assert document["verdict"] == "FAIL"
    assert [failure["check_id"] for failure in document["critical_failures"]] == ["B3"]


def test_non_critical_failure_alone_still_passes(cli, audit_repo):
    """감점은 게이트가 아니다. Critical 이 없으면 종료 코드는 0 이다."""
    _delete_ci_workflow(audit_repo)
    result = cli("--root", str(audit_repo), "--format", "json")
    assert result.code == 0
    document = json.loads(result.out)
    assert document["verdict"] == "PASS"
    assert document["score"] < BASELINE_SCORE
    assert document["critical_failures"] == []


def test_min_score_met_exits_zero(cli, audit_repo):
    result = cli("--root", str(audit_repo), "--min-score", str(BASELINE_SCORE))
    assert result.code == 0
    assert result.out.splitlines()[0] == "AUDIT: PASS"


def test_min_score_below_threshold_exits_one(cli, audit_repo):
    result = cli("--root", str(audit_repo), "--min-score", str(BASELINE_SCORE + 1))
    assert result.code == 1
    assert result.out.splitlines()[0] == "AUDIT: FAIL"


def test_min_score_failure_does_not_fabricate_critical_failures(cli, audit_repo):
    """임계값은 호출자의 기준이지 Hard Gate 가 아니다.

    이것이 무너지면 `--min-score` 하나로 "거짓말이면 Critical" 기준선이 오염되고,
    Critical 목록을 근거로 삼는 모든 소비자가 없는 게이트 위반을 보고하게 된다.
    """
    result = cli(
        "--root", str(audit_repo), "--format", "json", "--min-score", str(BASELINE_SCORE + 1)
    )
    assert result.code == 1
    document = json.loads(result.out)
    assert document["verdict"] == "FAIL"
    assert document["critical_failures"] == []
    assert document["score"] == BASELINE_SCORE
    # 점수와 check 결과는 임계값과 무관하다. 달라지는 것은 verdict 하나뿐이다.
    baseline = json.loads(cli("--root", str(audit_repo), "--format", "json").out)
    assert failing_ids(document) == failing_ids(baseline)
    assert document["next_actions"] == baseline["next_actions"]


def test_min_score_does_not_lift_a_critical_failure(cli, audit_repo):
    """충족한 임계값이 Critical 을 덮지 않는다. 게이트가 항상 우선이다."""
    _unregister_guard(audit_repo)
    result = cli("--root", str(audit_repo), "--format", "json", "--min-score", "0")
    assert result.code == 1
    assert json.loads(result.out)["verdict"] == "FAIL"


def test_same_arguments_produce_byte_identical_json(cli, audit_repo):
    for argv in (
        ("--root", str(audit_repo), "--format", "json"),
        ("--root", str(audit_repo), "--format", "json", "--min-score", "101"),
    ):
        first = cli(*argv)
        second = cli(*argv)
        assert first.out == second.out
        assert first.code == second.code


def test_broken_repository_exits_two_without_stdout(cli, audit_repo):
    """감사 실패는 감사 불합격이 아니다. 1 로 새어나가면 CI 가 고장을 FAIL 로 읽는다."""
    write(audit_repo, ".claude/settings.json", "{ this is not json")
    result = cli("--root", str(audit_repo), "--format", "json")
    assert result.code == 2
    assert result.out == ""
    assert "ERROR:" in result.err


def test_missing_root_exits_two(cli, tmp_path):
    assert cli("--root", str(tmp_path / "does-not-exist")).code == 2


# ---------------------------------------------------------------------------
# --write
# ---------------------------------------------------------------------------


def test_without_write_no_file_is_created(cli, audit_repo):
    before = reports_snapshot(audit_repo)
    for output_format in ("text", "json", "markdown"):
        assert cli("--root", str(audit_repo), "--format", output_format).code == 0
    assert reports_snapshot(audit_repo) == before
    assert audit_files(audit_repo) == []


def test_write_creates_exactly_two_latest_files(cli, audit_repo):
    assert cli("--root", str(audit_repo), "--write").code == 0
    assert audit_files(audit_repo) == ["latest.json", "latest.md"]


def test_write_touches_nothing_outside_reports_audit(cli, audit_repo):
    """보존된 대표 결과와 실행 산출물은 감사 대상이지 감사의 출력 대상이 아니다."""
    (audit_repo / "reports" / "RUN-20260826-1200-BUG-001").mkdir()
    write(audit_repo, "reports/RUN-20260826-1200-BUG-001/state.json", '{"run_id": "x"}\n')
    before = reports_snapshot(audit_repo)

    assert cli("--root", str(audit_repo), "--write").code == 0

    after = reports_snapshot(audit_repo)
    added = set(after) - set(before)
    assert added == {"audit/latest.json", "audit/latest.md"}
    for relative, body in before.items():
        assert after[relative] == body, relative


def test_write_keeps_only_latest_and_never_accumulates_history(cli, audit_repo):
    """이력은 git 이 갖는다. 날짜별 파일을 쌓으면 어느 것이 현재인지 물어야 한다."""
    for _ in range(3):
        assert cli("--root", str(audit_repo), "--write").code == 0
    assert audit_files(audit_repo) == ["latest.json", "latest.md"]


def test_written_files_match_stdout(cli, audit_repo):
    json_out = cli("--root", str(audit_repo), "--format", "json", "--write").out
    markdown_out = cli("--root", str(audit_repo), "--format", "markdown", "--write").out
    assert read(audit_repo, "reports/audit/latest.json") == json_out
    assert read(audit_repo, "reports/audit/latest.md") == markdown_out


def test_write_keeps_stdout_pure_json(cli, audit_repo):
    """`--write` 의 진단 문구가 stdout 을 오염시키면 파이프라인이 깨진다."""
    result = cli("--root", str(audit_repo), "--format", "json", "--write")
    assert json.loads(result.out)["verdict"] == BASELINE_VERDICT
    assert "reports/audit/latest.json" in result.err


def test_written_markdown_declares_the_verdict_on_the_first_line(cli, audit_repo):
    assert cli("--root", str(audit_repo), "--write").code == 0
    body = read(audit_repo, "reports/audit/latest.md")
    assert body.splitlines()[0] == "AUDIT: {0}".format(BASELINE_VERDICT)


def test_write_failure_is_an_execution_error(cli, audit_repo, monkeypatch, harness_audit):
    """한 파일만 쓰이고 조용히 PASS 로 끝나는 것이 가장 나쁜 결말이다."""
    original = Path.write_text

    def explode(self, *args, **kwargs):
        if self.name == "latest.md":
            raise OSError("디스크 오류")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", explode)
    result = cli("--root", str(audit_repo), "--write")
    assert result.code == 2
    assert result.out == ""
    assert "ERROR:" in result.err


def test_write_is_the_only_way_to_touch_the_repository(cli, audit_repo):
    """`--write` 없는 실행은 감사 대상 저장소 전체를 바꾸지 않는다."""
    before = sorted(
        (path.relative_to(audit_repo).as_posix(), path.stat().st_size)
        for path in audit_repo.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    assert cli("--root", str(audit_repo), "--format", "json").code == 0
    after = sorted(
        (path.relative_to(audit_repo).as_posix(), path.stat().st_size)
        for path in audit_repo.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    assert after == before
