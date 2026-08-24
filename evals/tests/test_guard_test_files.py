"""`guard_test_files.py` 정책 검증.

담당 범위는 `sample-project/tests/` 하위뿐이고, 회귀 테스트를 추가할 권한은
Tester 에게만 있다. (`CLAUDE.md §11`, `§21`)
"""

import json
import os
import subprocess
import sys

import pytest

TESTS_TARGET = "sample-project/tests/test_tip.py"
SRC_TARGET = "sample-project/src/expense/tip.py"


def _decide(guard, payload, root):
    return guard.decide(payload, root)


# --------------------------------------------------------------------------
# 정책표
# --------------------------------------------------------------------------


def test_developer_writing_test_file_is_blocked(guard_test_files, make_payload, fake_root):
    code, message = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    assert code == 2
    assert "차단" in message
    assert TESTS_TARGET in message


def test_tester_writing_test_file_is_allowed(guard_test_files, make_payload, fake_root):
    code, message = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="tester"), fake_root
    )
    assert code == 0
    assert message is None


def test_planner_writing_test_file_is_blocked(guard_test_files, make_payload, fake_root):
    code, _ = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="planner"), fake_root
    )
    assert code == 2


def test_reviewer_writing_test_file_is_blocked(guard_test_files, make_payload, fake_root):
    code, _ = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="reviewer"), fake_root
    )
    assert code == 2


def test_main_session_is_blocked_while_a_run_is_active(
    guard_test_files, make_payload, fake_root, make_run
):
    make_run(status="RUNNING")
    code, message = _decide(guard_test_files, make_payload(file_path=TESTS_TARGET), fake_root)
    assert code == 2
    assert "RUN-20260824-1600-BUG-001" in message


def test_main_session_is_allowed_when_no_run_is_active(
    guard_test_files, make_payload, fake_root, make_run
):
    make_run(status="SUCCESS")
    code, message = _decide(guard_test_files, make_payload(file_path=TESTS_TARGET), fake_root)
    assert code == 0
    assert message is None


def test_unknown_agent_type_is_blocked(guard_test_files, make_payload, fake_root):
    code, message = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="intruder"), fake_root
    )
    assert code == 2
    assert "알 수 없는 주체" in message


def test_non_string_agent_type_is_treated_as_unknown(guard_test_files, make_payload, fake_root):
    code, _ = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type=17), fake_root
    )
    assert code == 2


# --------------------------------------------------------------------------
# 담당 범위 밖
# --------------------------------------------------------------------------


def test_product_code_path_is_out_of_scope(guard_test_files, make_payload, fake_root):
    code, message = _decide(
        guard_test_files, make_payload(file_path=SRC_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert message is None


def test_reports_path_is_out_of_scope(guard_test_files, make_payload, fake_root):
    payload = make_payload(
        file_path="reports/RUN-20260824-1600-BUG-001/change-log-1.md", agent_type="developer"
    )
    code, _ = _decide(guard_test_files, payload, fake_root)
    assert code == 0


def test_bash_tool_is_out_of_scope(guard_test_files, make_payload, fake_root):
    code, _ = _decide(guard_test_files, make_payload(tool_name="Bash", agent_type="developer"), fake_root)
    assert code == 0


def test_path_outside_repository_is_out_of_scope(guard_test_files, make_payload, fake_root, tmp_path):
    outside = tmp_path.parent / "elsewhere" / "sample-project" / "tests" / "x.py"
    code, _ = _decide(
        guard_test_files, make_payload(file_path=str(outside), agent_type="developer"), fake_root
    )
    assert code == 0


def test_edit_tool_is_in_scope(guard_test_files, make_payload, fake_root):
    code, _ = _decide(
        guard_test_files,
        make_payload(tool_name="Edit", file_path=TESTS_TARGET, agent_type="developer"),
        fake_root,
    )
    assert code == 2


def test_missing_file_path_is_allowed(guard_test_files, make_payload, fake_root):
    payload = make_payload(agent_type="developer", tool_input={"content": "x"})
    code, _ = _decide(guard_test_files, payload, fake_root)
    assert code == 0


# --------------------------------------------------------------------------
# 경로 정규화
# --------------------------------------------------------------------------


def test_relative_and_absolute_paths_decide_identically(guard_test_files, make_payload, fake_root):
    relative = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    absolute = _decide(
        guard_test_files,
        make_payload(file_path=str(fake_root / "sample-project" / "tests" / "test_tip.py"),
                     agent_type="developer"),
        fake_root,
    )
    assert relative[0] == absolute[0] == 2


def test_parent_traversal_cannot_escape_the_guard(guard_test_files, make_payload, fake_root):
    sneaky = "sample-project/src/../tests/test_tip.py"
    code, _ = _decide(guard_test_files, make_payload(file_path=sneaky, agent_type="developer"), fake_root)
    assert code == 2


@pytest.mark.skipif(os.name != "nt", reason="드라이브 문자와 역슬래시는 Windows 경로 규칙이다")
def test_drive_letter_case_does_not_change_the_decision(guard_test_files, make_payload, fake_root):
    absolute = str(fake_root / "sample-project" / "tests" / "test_tip.py")
    lowered = absolute[0].lower() + absolute[1:]
    uppered = absolute[0].upper() + absolute[1:]
    for variant in (lowered, uppered):
        code, _ = _decide(
            guard_test_files, make_payload(file_path=variant, agent_type="developer"), fake_root
        )
        assert code == 2, variant


@pytest.mark.skipif(os.name != "nt", reason="역슬래시는 Windows 에서만 경로 구분자다")
def test_slash_direction_does_not_change_the_decision(guard_test_files, make_payload, fake_root):
    absolute = str(fake_root / "sample-project" / "tests" / "test_tip.py")
    for variant in (absolute, absolute.replace("\\", "/")):
        code, _ = _decide(
            guard_test_files, make_payload(file_path=variant, agent_type="developer"), fake_root
        )
        assert code == 2, variant


def test_symlinked_directory_cannot_bypass_the_guard(guard_test_files, make_payload, fake_root):
    link = fake_root / "sample-project" / "tests-link"
    try:
        link.symlink_to(fake_root / "sample-project" / "tests", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("이 환경에서는 심볼릭 링크를 만들 수 없다")
    code, _ = _decide(
        guard_test_files,
        make_payload(file_path=str(link / "test_tip.py"), agent_type="developer"),
        fake_root,
    )
    assert code == 2


# --------------------------------------------------------------------------
# 비활성 스위치
# --------------------------------------------------------------------------


def test_own_hook_id_disables_the_guard(guard_test_files, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-test-files")
    code, message = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "비활성화됨" in message


def test_all_disables_the_guard(guard_test_files, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", " ALL ")
    code, message = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    assert code == 0
    assert "비활성화됨" in message


def test_another_hook_id_keeps_the_policy(guard_test_files, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-plan-scope")
    code, _ = _decide(
        guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root
    )
    assert code == 2


def test_disable_switch_is_case_insensitive_and_trimmed(guard_common, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "  Guard-Test-Files , other ")
    assert guard_common.is_disabled("guard-test-files") is True
    assert guard_common.is_disabled("guard-plan-scope") is False


# --------------------------------------------------------------------------
# fail-open
# --------------------------------------------------------------------------


def test_broken_json_yields_no_payload(guard_common):
    import io

    assert guard_common.read_payload(io.StringIO("{not json")) is None
    assert guard_common.read_payload(io.StringIO("")) is None
    assert guard_common.read_payload(io.StringIO("   ")) is None
    assert guard_common.read_payload(io.StringIO("[1, 2, 3]")) is None


def test_ambiguous_run_state_is_allowed_with_warning(
    guard_test_files, make_payload, fake_root, make_run
):
    make_run(name="RUN-20260824-1600-BUG-001", status="RUNNING")
    make_run(name="RUN-20260824-1700-BUG-002", status="RUNNING")
    code, message = _decide(guard_test_files, make_payload(file_path=TESTS_TARGET), fake_root)
    assert code == 0
    assert "경고" in message


def test_corrupt_state_json_is_allowed_with_warning(
    guard_test_files, make_payload, fake_root, make_run
):
    make_run(state_text="{ broken")
    code, message = _decide(guard_test_files, make_payload(file_path=TESTS_TARGET), fake_root)
    assert code == 0
    assert "경고" in message


# --------------------------------------------------------------------------
# 실제 진입점 (subprocess) — 종료 코드 배선 확인
# --------------------------------------------------------------------------


def _run_hook(hooks_dir, repo_root, payload_text, env_extra=None):
    """훅을 실제 진입점으로 실행한다.

    stdout/stderr 를 바이트로 받는다. 콘솔 코드페이지가 아니라 UTF-8 로 나오는지까지
    확인해야 하므로 `text=True` 로 자동 디코드하지 않는다.
    """
    env = dict(os.environ)
    env.pop("PATCHPILOT_DISABLED_HOOKS", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(hooks_dir / "guard_test_files.py")],
        input=payload_text.encode("utf-8"),
        capture_output=True,
        cwd=str(repo_root),
        env=env,
    )


def test_entrypoint_blocks_developer_writing_tests(hooks_dir, repo_root, make_payload):
    payload = make_payload(file_path=TESTS_TARGET, agent_type="developer")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    assert result.returncode == 2
    assert b"guard-test-files" in result.stderr


def test_entrypoint_stderr_is_utf8(hooks_dir, repo_root, make_payload):
    """차단 메시지는 모델에게 전달된다. 콘솔 코드페이지로 인코딩되면 근거가 깨진다."""
    payload = make_payload(file_path=TESTS_TARGET, agent_type="developer")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    decoded = result.stderr.decode("utf-8")  # 실패하면 UnicodeDecodeError 로 테스트가 깨진다
    assert "차단: 테스트 파일 쓰기 권한 없음" in decoded
    assert "CLAUDE.md §21" in decoded


def test_entrypoint_allows_broken_stdin(hooks_dir, repo_root):
    result = _run_hook(hooks_dir, repo_root, "{ not json")
    assert result.returncode == 0


def test_entrypoint_honours_disable_switch(hooks_dir, repo_root, make_payload):
    payload = make_payload(file_path=TESTS_TARGET, agent_type="developer")
    result = _run_hook(
        hooks_dir,
        repo_root,
        json.dumps(payload, ensure_ascii=False),
        env_extra={"PATCHPILOT_DISABLED_HOOKS": "all"},
    )
    assert result.returncode == 0


def test_block_message_contains_agent_id(guard_test_files, make_payload, fake_root):
    payload = make_payload(file_path=TESTS_TARGET, agent_type="developer", agent_id="abc123")
    _, message = _decide(guard_test_files, payload, fake_root)
    assert "agent_id=abc123" in message


def test_guard_writes_nothing_to_the_repository(guard_test_files, make_payload, fake_root):
    """훅이 상태를 남기면 실행 간 결정론이 깨진다. 판정 전후 파일 목록이 같아야 한다."""
    before = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    _decide(guard_test_files, make_payload(file_path=TESTS_TARGET, agent_type="developer"), fake_root)
    after = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    assert before == after
