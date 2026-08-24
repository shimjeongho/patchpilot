"""`guard_plan_scope.py` 정책 검증.

담당 범위는 `sample-project/` 하위 중 `sample-project/tests/` 를 뺀 나머지다.
Developer 만 `plan.md` 의 수정 허용 파일 목록 안에서 제품 코드를 고칠 수 있다.
(`CLAUDE.md §3-2`, `§11`, `§17`)
"""

import json
import os
import subprocess
import sys

import pytest

ALLOWED_TARGET = "sample-project/src/expense/service_charge.py"
OUTSIDE_TARGET = "sample-project/src/expense/charge_rounding.py"
TESTS_TARGET = "sample-project/tests/test_service_charge.py"


def _decide(guard, payload, root):
    return guard.decide(payload, root)


# --------------------------------------------------------------------------
# 정책표
# --------------------------------------------------------------------------


def test_developer_inside_plan_scope_is_allowed(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=ALLOWED_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert message is None


def test_developer_outside_plan_scope_is_blocked(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 2
    assert OUTSIDE_TARGET in message
    assert ALLOWED_TARGET in message  # 허용 목록을 그대로 보여준다


def test_developer_without_active_run_is_blocked(guard_plan_scope, make_payload, fake_root):
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=ALLOWED_TARGET, agent_type="developer"), fake_root
    )
    assert code == 2
    assert "활성 run" in message


@pytest.mark.parametrize("who", ["tester", "planner", "reviewer"])
def test_other_agents_cannot_touch_product_code(
    guard_plan_scope, make_payload, fake_root, make_run, who
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=ALLOWED_TARGET, agent_type=who), fake_root
    )
    assert code == 2
    assert "제품 코드 수정 권한" in message


def test_unknown_agent_type_is_blocked(guard_plan_scope, make_payload, fake_root, make_run):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=ALLOWED_TARGET, agent_type="intruder"), fake_root
    )
    assert code == 2
    assert "알 수 없는 주체" in message


def test_main_session_is_blocked_while_a_run_is_active(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(guard_plan_scope, make_payload(file_path=ALLOWED_TARGET), fake_root)
    assert code == 2
    assert "Orchestrator" in message


def test_main_session_is_allowed_when_no_run_is_active(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(status="SUCCESS", allowed=(ALLOWED_TARGET,))
    code, message = _decide(guard_plan_scope, make_payload(file_path=ALLOWED_TARGET), fake_root)
    assert code == 0
    assert message is None


# --------------------------------------------------------------------------
# 담당 범위 밖
# --------------------------------------------------------------------------


def test_tests_path_is_left_to_the_other_guard(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert message is None


def test_reports_path_is_out_of_scope(guard_plan_scope, make_payload, fake_root, make_run):
    """Developer 가 사유를 적고 중단하는 경로를 막으면 규칙이 실행 불가능해진다."""
    run_dir = make_run(allowed=(ALLOWED_TARGET,))
    payload = make_payload(
        file_path="reports/" + run_dir.name + "/change-log-1.md", agent_type="developer"
    )
    code, _ = _decide(guard_plan_scope, payload, fake_root)
    assert code == 0


def test_bash_tool_is_out_of_scope(guard_plan_scope, make_payload, fake_root, make_run):
    make_run(allowed=(ALLOWED_TARGET,))
    code, _ = _decide(
        guard_plan_scope, make_payload(tool_name="Bash", agent_type="developer"), fake_root
    )
    assert code == 0


def test_repository_files_outside_sample_project_are_out_of_scope(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, _ = _decide(
        guard_plan_scope, make_payload(file_path="CLAUDE.md", agent_type="developer"), fake_root
    )
    assert code == 0


# --------------------------------------------------------------------------
# 허용 목록 비교는 완전 일치로만 한다
# --------------------------------------------------------------------------


def test_suffix_extension_is_not_covered_by_the_allowlist(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    code, _ = _decide(
        guard_plan_scope,
        make_payload(file_path=ALLOWED_TARGET + ".bak", agent_type="developer"),
        fake_root,
    )
    assert code == 2


def test_sibling_with_shared_prefix_is_not_covered(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=("sample-project/src/expense/tip.py",))
    code, _ = _decide(
        guard_plan_scope,
        make_payload(file_path="sample-project/src/expense/tip_extra.py", agent_type="developer"),
        fake_root,
    )
    assert code == 2


def test_directory_boundary_difference_is_not_covered(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=("sample-project/src/expense/tip.py",))
    code, _ = _decide(
        guard_plan_scope,
        make_payload(file_path="sample-project/src/expense/nested/tip.py", agent_type="developer"),
        fake_root,
    )
    assert code == 2


def test_traversal_into_an_allowed_file_still_resolves(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    sneaky = "sample-project/tests/../src/expense/service_charge.py"
    code, _ = _decide(guard_plan_scope, make_payload(file_path=sneaky, agent_type="developer"), fake_root)
    assert code == 0


def test_traversal_out_of_allowed_file_is_blocked(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    sneaky = "sample-project/src/expense/../expense/charge_rounding.py"
    code, _ = _decide(guard_plan_scope, make_payload(file_path=sneaky, agent_type="developer"), fake_root)
    assert code == 2


# --------------------------------------------------------------------------
# fail-open
# --------------------------------------------------------------------------


def test_two_running_states_are_allowed_with_warning(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(name="RUN-20260824-1600-BUG-001")
    make_run(name="RUN-20260824-1700-BUG-002")
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "RUNNING 상태의 run 이 2개" in message


def test_corrupt_state_json_is_allowed_with_warning(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(state_text="{ broken")
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "경고" in message


def test_missing_plan_is_allowed_with_warning(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(write_plan=False)
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "경고" in message


def test_plan_without_the_allowlist_section_is_allowed_with_warning(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(plan_text="# Plan\n\n## 1. 요구사항 요약\n아무 목록도 없다\n")
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "수정 허용 파일 목록을 읽지 못했습니다" in message


def test_empty_allowlist_is_allowed_with_warning(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=())
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "경고" in message


# --------------------------------------------------------------------------
# 비활성 스위치
# --------------------------------------------------------------------------


def test_own_hook_id_disables_the_guard(
    guard_plan_scope, make_payload, fake_root, make_run, monkeypatch
):
    make_run(allowed=(ALLOWED_TARGET,))
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-plan-scope")
    code, message = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "비활성화됨" in message


def test_all_disables_the_guard(guard_plan_scope, make_payload, fake_root, make_run, monkeypatch):
    make_run(allowed=(ALLOWED_TARGET,))
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "all")
    code, _ = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0


def test_another_hook_id_keeps_the_policy(
    guard_plan_scope, make_payload, fake_root, make_run, monkeypatch
):
    make_run(allowed=(ALLOWED_TARGET,))
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-test-files")
    code, _ = _decide(
        guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root
    )
    assert code == 2


# --------------------------------------------------------------------------
# harness-eval-002 재계획 경로 재현
# --------------------------------------------------------------------------


def test_replanned_scope_unblocks_the_second_attempt(
    guard_plan_scope, make_payload, fake_root, make_run
):
    """EVAL-002 경로: Planner 2차가 plan.md 를 갱신하면 Developer 2차가 통과해야 한다."""
    run_dir = make_run(allowed=(ALLOWED_TARGET,))
    payload = make_payload(file_path=OUTSIDE_TARGET, agent_type="developer")

    assert _decide(guard_plan_scope, payload, fake_root)[0] == 2

    # Planner 2차가 같은 plan.md 를 덮어쓴다. 스냅샷(plan-1.md)이 아니라 live 파일을 본다.
    updated = (run_dir / "plan.md").read_text(encoding="utf-8").replace(
        "- `" + ALLOWED_TARGET + "`",
        "- `" + ALLOWED_TARGET + "`\n- `" + OUTSIDE_TARGET + "`",
    )
    (run_dir / "plan.md").write_text(updated, encoding="utf-8")

    assert _decide(guard_plan_scope, payload, fake_root)[0] == 0


# --------------------------------------------------------------------------
# 실제 진입점 (subprocess)
# --------------------------------------------------------------------------


def _run_hook(hooks_dir, repo_root, payload_text, env_extra=None):
    """훅을 실제 진입점으로 실행한다. stderr 인코딩까지 보려고 바이트로 받는다."""
    env = dict(os.environ)
    env.pop("PATCHPILOT_DISABLED_HOOKS", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(hooks_dir / "guard_plan_scope.py")],
        input=payload_text.encode("utf-8"),
        capture_output=True,
        cwd=str(repo_root),
        env=env,
    )


def test_entrypoint_blocks_planner_touching_product_code(hooks_dir, repo_root, make_payload):
    payload = make_payload(file_path=ALLOWED_TARGET, agent_type="planner")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    assert result.returncode == 2
    assert b"guard-plan-scope" in result.stderr


def test_entrypoint_stderr_is_utf8(hooks_dir, repo_root, make_payload):
    """차단 메시지는 모델에게 전달된다. 콘솔 코드페이지로 인코딩되면 근거가 깨진다."""
    payload = make_payload(file_path=ALLOWED_TARGET, agent_type="planner")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    decoded = result.stderr.decode("utf-8")
    assert "차단: 계획 허용 목록 밖 파일 쓰기" in decoded
    assert "CLAUDE.md §11" in decoded


def test_entrypoint_allows_empty_stdin(hooks_dir, repo_root):
    result = _run_hook(hooks_dir, repo_root, "")
    assert result.returncode == 0


def test_entrypoint_honours_disable_switch(hooks_dir, repo_root, make_payload):
    payload = make_payload(file_path=ALLOWED_TARGET, agent_type="planner")
    result = _run_hook(
        hooks_dir,
        repo_root,
        json.dumps(payload, ensure_ascii=False),
        env_extra={"PATCHPILOT_DISABLED_HOOKS": "guard-plan-scope"},
    )
    assert result.returncode == 0


def test_guard_writes_nothing_to_the_repository(
    guard_plan_scope, make_payload, fake_root, make_run
):
    make_run(allowed=(ALLOWED_TARGET,))
    before = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    _decide(guard_plan_scope, make_payload(file_path=OUTSIDE_TARGET, agent_type="developer"), fake_root)
    after = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    assert before == after
