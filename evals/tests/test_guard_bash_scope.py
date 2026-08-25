"""`guard_bash_scope.py` 정책 검증.

담당 범위는 `Bash` 도구와 `tester` / `reviewer` 두 주체뿐이다.

정책의 근거는 두 가지다.

* `reports/` 전체(로컬 RUN 12건 + `examples/EVAL-001~004`)에서 수집한 **실측 명령**.
  허용 목록은 실제로 쓰인 형태만 담는다. `MEASURED_*_ALLOWED` 가 그 회귀 고정이다.
* Claude Code 2.1.241 실측. 특히 `git diff --output=<path>` 가 실제 저장소에서
  파일을 생성한 케이스를 `test_measured_git_diff_output_attack_is_blocked` 로 고정한다.
"""

import json
import os
import subprocess
import sys

import pytest

SRC_PATH = "sample-project/src/expense/tip.py"
TEST_PATH = "sample-project/tests/test_tip.py"
FIXTURE_PATH = "evals/fixtures/tip.py"


def _bash(make_payload, command, agent_type="tester", agent_id="a985f0597c0555546"):
    """Bash PreToolUse payload. 실측 payload 는 command 와 description 을 함께 보낸다."""
    return make_payload(
        tool_name="Bash",
        agent_type=agent_type,
        agent_id=agent_id,
        tool_input={"command": command, "description": "probe"},
    )


def _decide(guard, make_payload, command, root, agent_type="tester"):
    return guard.decide(_bash(make_payload, command, agent_type), root)


def _allowed(guard, make_payload, command, root, agent_type="tester"):
    code, _ = _decide(guard, make_payload, command, root, agent_type)
    return code == 0


# --------------------------------------------------------------------------
# 실측 명령 회귀 고정 (`A3 사전 분석 §3`)
#
# 아래 두 목록은 "정상 실행에서 실제로 쓰인" 명령만 담는다. 정책을 좁힐 때
# EVAL-001~004 리뷰가 깨지는지를 이 목록이 먼저 알려준다.
# --------------------------------------------------------------------------

MEASURED_TESTER_ALLOWED = (
    "uv run pytest sample-project/tests -q",
    "git status",
    "git status --short",
    "git status --porcelain",
    "git diff",
    "git diff --stat",
)

MEASURED_REVIEWER_ALLOWED = (
    "git status --porcelain",
    "git status --short",
    "git status --porcelain --untracked-files=all",
    "git status --porcelain --untracked-files=all --ignored",
    "git diff",
    "git diff --stat",
    "git diff --cached",
    "git diff --cached --stat",
    "git diff --no-index -- " + FIXTURE_PATH + " " + SRC_PATH,
    "git diff 66776a08a25d7964f97fe7dcb0334a80cc04c5b4 -- sample-project/",
    "git diff " + TEST_PATH,
    "git log --oneline -5",
    "git log --oneline -3",
    "git check-ignore -v reports",
    "git hash-object --path " + SRC_PATH + " " + SRC_PATH,
    "git config core.autocrlf",
    "diff --strip-trailing-cr " + FIXTURE_PATH + " " + SRC_PATH,
    "diff -u " + FIXTURE_PATH + " " + SRC_PATH,
    "diff evals/fixtures/test_tip.py " + TEST_PATH,
    "cat -n " + SRC_PATH,
    'grep -c "^def test_" ' + TEST_PATH,
)

# 실측됐지만 이번 정책에서 **의도적으로** 허용하지 않기로 한 명령.
# 정상 allow 목록과 섞지 않는다. 섞으면 "왜 빠졌는지" 가 코드에서 사라진다.
MEASURED_BUT_EXCLUDED = (
    # Tester — 임의 파이썬 실행. 허용하면 화이트리스트 전체가 무의미해진다.
    ("tester", 'uv run python -c "print(1)"'),
    # Tester — Glob / Read 도구로 대체 가능하다.
    ("tester", "ls sample-project/config/settlement_runtime.json"),
    # Reviewer — 실측 0건. "있을 것 같다" 는 이유로 넣지 않는다. (`A3 §5`)
    ("reviewer", "git show --stat"),
    # Reviewer — 파이프. 판정과 무관한 CRLF 참고 사항 산출용이었다.
    ("reviewer", "tr -dc '\\r' < " + SRC_PATH),
    # Reviewer — 셸 메타문자가 든 grep 패턴. Grep 도구로 대체한다.
    ("reviewer", 'grep -rn "patchpilot-eval\\|_split_tip" sample-project/'),
)


@pytest.mark.parametrize("command", MEASURED_TESTER_ALLOWED)
def test_measured_tester_command_stays_allowed(guard_bash_scope, make_payload, fake_root, command):
    assert _allowed(guard_bash_scope, make_payload, command, fake_root, "tester")


@pytest.mark.parametrize("command", MEASURED_REVIEWER_ALLOWED)
def test_measured_reviewer_command_stays_allowed(guard_bash_scope, make_payload, fake_root, command):
    assert _allowed(guard_bash_scope, make_payload, command, fake_root, "reviewer")


@pytest.mark.parametrize("agent_type,command", MEASURED_BUT_EXCLUDED)
def test_measured_but_intentionally_excluded_command_is_blocked(
    guard_bash_scope, make_payload, fake_root, agent_type, command
):
    """실측됐으나 정책에서 제외하기로 결정한 명령. 실수로 열리면 여기서 깨진다."""
    assert not _allowed(guard_bash_scope, make_payload, command, fake_root, agent_type)


# --------------------------------------------------------------------------
# A. Tester 정상
# --------------------------------------------------------------------------


def test_tester_fixed_pytest_command_is_allowed(guard_bash_scope, make_payload, fake_root):
    assert _allowed(
        guard_bash_scope, make_payload, "uv run pytest sample-project/tests -q", fake_root, "tester"
    )


def test_tester_git_status_is_allowed(guard_bash_scope, make_payload, fake_root):
    assert _allowed(guard_bash_scope, make_payload, "git status", fake_root, "tester")


def test_tester_git_status_porcelain_is_allowed(guard_bash_scope, make_payload, fake_root):
    assert _allowed(guard_bash_scope, make_payload, "git status --porcelain", fake_root, "tester")


def test_tester_git_diff_stat_is_allowed(guard_bash_scope, make_payload, fake_root):
    assert _allowed(guard_bash_scope, make_payload, "git diff --stat", fake_root, "tester")


# --------------------------------------------------------------------------
# B. Reviewer 정상
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git status --porcelain",
        "git diff",
        "git diff --stat",
        "git diff --cached",
        "git diff --no-index -- " + FIXTURE_PATH + " " + SRC_PATH,
        "diff --strip-trailing-cr " + FIXTURE_PATH + " " + SRC_PATH,
        "cat -n " + SRC_PATH,
        "grep -rn pattern sample-project/",
        "git check-ignore -v reports",
        "git hash-object --path " + SRC_PATH + " " + SRC_PATH,
        "git config core.autocrlf",
    ],
)
def test_reviewer_review_command_is_allowed(guard_bash_scope, make_payload, fake_root, command):
    assert _allowed(guard_bash_scope, make_payload, command, fake_root, "reviewer")


def test_reviewer_git_config_with_a_value_is_blocked(guard_bash_scope, make_payload, fake_root):
    """조회는 허용하지만 값 설정은 저장소 상태를 바꾼다."""
    assert not _allowed(
        guard_bash_scope, make_payload, "git config core.autocrlf false", fake_root, "reviewer"
    )


def test_reviewer_hash_object_write_flag_is_blocked(guard_bash_scope, make_payload, fake_root):
    """`-w` 는 오브젝트 DB 에 실제로 기록한다."""
    assert not _allowed(
        guard_bash_scope, make_payload, "git hash-object -w " + SRC_PATH, fake_root, "reviewer"
    )


# --------------------------------------------------------------------------
# C. 역할 분리
# --------------------------------------------------------------------------


def test_reviewer_cannot_run_pytest(guard_bash_scope, make_payload, fake_root):
    """테스트 판정 권한은 Tester 에게만 있다. (`CLAUDE.md §11`, `reviewer.md §5`)"""
    assert not _allowed(
        guard_bash_scope,
        make_payload,
        "uv run pytest sample-project/tests -q",
        fake_root,
        "reviewer",
    )


def test_tester_cannot_run_git_log(guard_bash_scope, make_payload, fake_root):
    """Reviewer 전용 명령을 Tester 에게 자동으로 공유하지 않는다."""
    assert not _allowed(guard_bash_scope, make_payload, "git log --oneline -1", fake_root, "tester")


@pytest.mark.parametrize("agent_type", ["planner", "developer"])
def test_agents_without_bash_are_out_of_scope(
    guard_bash_scope, make_payload, fake_root, agent_type
):
    """Planner / Developer 는 tools 에 Bash 가 없다. 이 가드의 담당 범위 밖이다."""
    assert _allowed(guard_bash_scope, make_payload, "rm -rf sample-project", fake_root, agent_type)


def test_main_session_bash_is_out_of_scope(guard_bash_scope, make_payload, fake_root):
    """메인 세션은 `patchpilot.md` 의 allowed-tools 와 permissions 가 담당한다."""
    payload = make_payload(tool_name="Bash", tool_input={"command": "git log --oneline -5"})
    code, message = guard_bash_scope.decide(payload, fake_root)
    assert code == 0
    assert message is None


def test_unknown_agent_type_is_allowed_with_a_warning(guard_bash_scope, make_payload, fake_root):
    """알 수 없는 주체는 통과시키되 반드시 보이게 한다.

    `guard_test_files.py` 는 알 수 없는 주체를 **차단**하지만, 그 가드의 담당 축은
    경로(`sample-project/tests/`)라서 차단 범위가 좁다. 이 가드의 담당 축은 주체이므로
    같은 규칙을 쓰면 Harness 개발에 쓰는 다른 서브에이전트의 Bash 까지 전부 멈춘다.
    통과 + 경고로 두고, settings.json 연결 단계에서 실제 등장하는 agent_type 을 보고
    다시 판단한다.
    """
    code, message = _decide(
        guard_bash_scope, make_payload, "git log --oneline -5", fake_root, "code-reviewer"
    )
    assert code == 0
    assert "담당 범위 밖의 주체" in message


def test_non_string_agent_type_is_treated_as_unknown(guard_bash_scope, make_payload, fake_root):
    code, message = _decide(guard_bash_scope, make_payload, "git status", fake_root, 42)
    assert code == 0
    assert "담당 범위 밖의 주체" in message


# --------------------------------------------------------------------------
# D. 실제 우회
# --------------------------------------------------------------------------


def test_measured_git_diff_output_attack_is_blocked(guard_bash_scope, make_payload, fake_root):
    """Claude Code 2.1.241 실측 케이스.

    `git diff --output=probe_redir_tmp2.txt HEAD` 는 실제 PatchPilot 저장소에서
    파일을 생성했다. 셸 리다이렉션이 아니라 git 자체 옵션이라 Claude Code 내장
    가드에 걸리지 않는다. 이 가드가 유일한 방어선이다.
    """
    code, message = _decide(
        guard_bash_scope,
        make_payload,
        "git diff --output=probe_redir_tmp2.txt HEAD",
        fake_root,
        "reviewer",
    )
    assert code == 2
    assert "--output=probe_redir_tmp2.txt" in message


@pytest.mark.parametrize(
    "command",
    [
        "git diff --output=x.py",
        "git diff --output x.py",
        "git diff -O x",
        "git diff --ext-diff",
    ],
)
def test_git_diff_write_options_are_blocked(guard_bash_scope, make_payload, fake_root, command):
    """옵션은 blocklist 가 아니라 allowlist 다. 허용 목록에 없으면 자동으로 막힌다."""
    assert not _allowed(guard_bash_scope, make_payload, command, fake_root, "reviewer")


@pytest.mark.parametrize(
    "command",
    [
        "git status > x.py",
        "git status >> x.py",
        "cat > x.py <<EOF",
        "git diff | tee x.py",
        "git status && rm -rf sample-project",
        "git diff ; python evil.py",
        "git diff $(git rev-parse HEAD)",
        "git log --oneline `whoami`",
        "git diff $BRANCH",
        "git diff ${BRANCH}",
        "git status\ngit commit -m x",
    ],
)
def test_shell_composition_is_blocked(guard_bash_scope, make_payload, fake_root, command):
    assert not _allowed(guard_bash_scope, make_payload, command, fake_root, "reviewer")


def test_shell_composition_is_reported_before_the_whitelist(
    guard_bash_scope, make_payload, fake_root
):
    """메타문자 검사가 화이트리스트보다 먼저 돈다는 사실을 메시지로 고정한다."""
    _, message = _decide(guard_bash_scope, make_payload, "git status > x.py", fake_root, "reviewer")
    assert "셸 합성 요소" in message


def test_unbalanced_quotes_are_blocked(guard_bash_scope, make_payload, fake_root):
    assert not _allowed(guard_bash_scope, make_payload, 'cat -n "unterminated', fake_root, "reviewer")


# --------------------------------------------------------------------------
# E. 임의 실행
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        'uv run python -c "open(1)"',
        'python -c "x"',
        'python3 -c "x"',
        'sh -c "x"',
        'bash -c "x"',
        'powershell -c "x"',
        'pwsh -c "x"',
        "cmd /c x",
        'node -e "x"',
    ],
)
@pytest.mark.parametrize("agent_type", ["tester", "reviewer"])
def test_arbitrary_interpreters_are_blocked(
    guard_bash_scope, make_payload, fake_root, command, agent_type
):
    assert not _allowed(guard_bash_scope, make_payload, command, fake_root, agent_type)


# --------------------------------------------------------------------------
# F. pytest 조작
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest sample-project/tests -q -k test_x",
        "uv run pytest sample-project/tests -q --deselect sample-project/tests/test_tip.py::test_a",
        "uv run pytest sample-project/tests -q -p no:cacheprovider",
        "uv run pytest sample-project/tests",
        "uv run pytest",
        "pytest sample-project/tests -q",
        "python -m pytest sample-project/tests -q",
    ],
)
def test_pytest_variants_are_blocked(guard_bash_scope, make_payload, fake_root, command):
    """`CLAUDE.md §10` 고정 명령은 토큰까지 정확히 일치해야 한다."""
    assert not _allowed(guard_bash_scope, make_payload, command, fake_root, "tester")


def test_pytest_variant_message_points_at_the_fixed_command(
    guard_bash_scope, make_payload, fake_root
):
    _, message = _decide(
        guard_bash_scope,
        make_payload,
        "uv run pytest sample-project/tests -q -k test_x",
        fake_root,
        "tester",
    )
    assert "uv run pytest sample-project/tests -q" in message


# --------------------------------------------------------------------------
# G. 경로
# --------------------------------------------------------------------------


def test_parent_traversal_argument_is_blocked(guard_bash_scope, make_payload, fake_root):
    assert not _allowed(
        guard_bash_scope, make_payload, "cat -n ../secret.txt", fake_root, "reviewer"
    )


def test_traversal_that_returns_inside_is_still_blocked(guard_bash_scope, make_payload, fake_root):
    """`resolve()` 결과가 저장소 안이어도 거부한다. 경로를 눈으로 대조할 수 없게 된다."""
    assert not _allowed(
        guard_bash_scope,
        make_payload,
        "cat -n sample-project/../sample-project/src/expense/tip.py",
        fake_root,
        "reviewer",
    )


def test_absolute_path_outside_repository_is_blocked(
    guard_bash_scope, make_payload, fake_root, tmp_path
):
    outside = (tmp_path.parent / "outside.txt").as_posix()
    assert not _allowed(
        guard_bash_scope, make_payload, "cat -n " + outside, fake_root, "reviewer"
    )


def test_absolute_path_inside_repository_is_allowed(guard_bash_scope, make_payload, fake_root):
    inside = (fake_root / "sample-project" / "src" / "expense" / "tip.py").as_posix()
    assert _allowed(guard_bash_scope, make_payload, "cat -n " + inside, fake_root, "reviewer")


def test_forward_slash_path_is_allowed(guard_bash_scope, make_payload, fake_root):
    assert _allowed(guard_bash_scope, make_payload, "cat -n " + SRC_PATH, fake_root, "reviewer")


def test_backslash_path_is_blocked_instead_of_being_mangled(
    guard_bash_scope, make_payload, fake_root
):
    """백슬래시는 `shlex` POSIX 모드에서 다음 글자를 먹는다.

    `sample-project\\src\\expense\\tip.py` 는 `sample-projectsrcexpense` 와 `ip.py`
    두 토큰으로 뭉개진다. 뭉개진 토큰도 저장소 안 경로로 보이기 때문에 그대로 두면
    검사를 통과해 버린다. 검사한 문자열과 실행되는 문자열이 다른 상태를 허용하지
    않도록 백슬래시 자체를 거부한다. 실측 정상 명령은 전부 슬래시를 쓴다.
    """
    code, message = _decide(
        guard_bash_scope,
        make_payload,
        "cat -n sample-project\\src\\expense\\tip.py",
        fake_root,
        "reviewer",
    )
    assert code == 2
    assert "이스케이프" in message


def test_drive_letter_case_does_not_change_the_decision(guard_bash_scope, make_payload, fake_root):
    absolute = (fake_root / "sample-project" / "src" / "expense" / "tip.py").as_posix()
    if not absolute[1:2] == ":":
        pytest.skip("드라이브 문자가 있는 플랫폼에서만 의미가 있다")
    lower = "cat -n " + absolute[0].lower() + absolute[1:]
    upper = "cat -n " + absolute[0].upper() + absolute[1:]
    assert _allowed(guard_bash_scope, make_payload, lower, fake_root, "reviewer") is _allowed(
        guard_bash_scope, make_payload, upper, fake_root, "reviewer"
    )


def test_symlinked_directory_cannot_bypass_the_guard(
    guard_bash_scope, make_payload, fake_root, tmp_path
):
    outside_dir = tmp_path.parent / "outside_target"
    outside_dir.mkdir(exist_ok=True)
    link = fake_root / "sample-project" / "linked"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("이 환경에서는 심볼릭 링크를 만들 수 없다")
    assert not _allowed(
        guard_bash_scope, make_payload, "cat -n sample-project/linked/x.txt", fake_root, "reviewer"
    )


# --------------------------------------------------------------------------
# H. 위생
# --------------------------------------------------------------------------


def test_own_hook_id_disables_the_guard(guard_bash_scope, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-bash-scope")
    code, message = _decide(guard_bash_scope, make_payload, "git status > x", fake_root, "tester")
    assert code == 0
    assert "비활성화됨" in message


def test_all_disables_the_guard(guard_bash_scope, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "ALL")
    code, _ = _decide(guard_bash_scope, make_payload, "git status > x", fake_root, "tester")
    assert code == 0


def test_another_hook_id_keeps_the_policy(guard_bash_scope, make_payload, fake_root, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-test-files")
    code, _ = _decide(guard_bash_scope, make_payload, "git status > x", fake_root, "tester")
    assert code == 2


def test_non_bash_tool_is_out_of_scope(guard_bash_scope, make_payload, fake_root):
    """Write/Edit 는 기존 두 가드가 담당한다. 담당 도구가 겹치지 않는다."""
    code, message = guard_bash_scope.decide(
        make_payload(file_path=TEST_PATH, agent_type="tester"), fake_root
    )
    assert code == 0
    assert message is None


def test_missing_command_is_allowed_with_a_warning(guard_bash_scope, make_payload, fake_root):
    payload = make_payload(tool_name="Bash", agent_type="tester", tool_input={"description": "x"})
    code, message = guard_bash_scope.decide(payload, fake_root)
    assert code == 0
    assert "명령 문자열이 없어" in message


def test_blank_command_is_allowed_with_a_warning(guard_bash_scope, make_payload, fake_root):
    code, message = _decide(guard_bash_scope, make_payload, "   ", fake_root, "tester")
    assert code == 0
    assert "명령 문자열이 없어" in message


def test_non_string_command_is_allowed(guard_bash_scope, make_payload, fake_root):
    payload = make_payload(tool_name="Bash", agent_type="tester", tool_input={"command": 42})
    code, _ = guard_bash_scope.decide(payload, fake_root)
    assert code == 0


def test_crlf_is_normalised_before_the_check(guard_bash_scope, make_payload, fake_root):
    """CRLF 가 섞여도 정상 명령은 통과하고, 남은 개행은 합성으로 잡힌다."""
    assert _allowed(
        guard_bash_scope, make_payload, "git status --porcelain\r\n", fake_root, "tester"
    )
    assert not _allowed(
        guard_bash_scope, make_payload, "git status\r\ngit diff", fake_root, "tester"
    )


def test_block_message_contains_agent_id(guard_bash_scope, make_payload, fake_root):
    _, message = _decide(
        guard_bash_scope,
        make_payload,
        "git log --oneline -1",
        fake_root,
        "tester",
    )
    assert "agent_id=" in message
    assert "tester" in message


def test_block_message_is_deterministic(guard_bash_scope, make_payload, fake_root):
    first = _decide(guard_bash_scope, make_payload, "git diff --output=x.py", fake_root, "reviewer")
    second = _decide(guard_bash_scope, make_payload, "git diff --output=x.py", fake_root, "reviewer")
    assert first == second


def test_guard_writes_nothing_to_the_repository(guard_bash_scope, make_payload, fake_root):
    """훅이 상태를 남기면 실행 간 결정론이 깨진다. 판정 전후 파일 목록이 같아야 한다."""
    before = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    for agent_type, command in MEASURED_BUT_EXCLUDED:
        _decide(guard_bash_scope, make_payload, command, fake_root, agent_type)
    for command in MEASURED_REVIEWER_ALLOWED:
        _decide(guard_bash_scope, make_payload, command, fake_root, "reviewer")
    after = sorted(p.relative_to(fake_root).as_posix() for p in fake_root.rglob("*"))
    assert before == after


# --------------------------------------------------------------------------
# 엔트리포인트
# --------------------------------------------------------------------------


def _run_hook(hooks_dir, repo_root, payload_text, env_extra=None):
    env = dict(os.environ)
    env.pop("PATCHPILOT_DISABLED_HOOKS", None)
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(hooks_dir / "guard_bash_scope.py")],
        input=payload_text.encode("utf-8"),
        capture_output=True,
        cwd=str(repo_root),
        env=env,
    )


def test_entrypoint_blocks_a_write_capable_command(hooks_dir, repo_root, make_payload):
    payload = _bash(make_payload, "git diff --output=x.py", "reviewer")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    assert result.returncode == 2
    assert b"guard-bash-scope" in result.stderr


def test_entrypoint_stderr_is_utf8(hooks_dir, repo_root, make_payload):
    """차단 메시지는 모델에게 그대로 전달된다. 콘솔 코드페이지로 인코딩되면 근거가 깨진다."""
    payload = _bash(make_payload, "git diff --output=x.py", "reviewer")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    decoded = result.stderr.decode("utf-8")  # 실패하면 UnicodeDecodeError 로 테스트가 깨진다
    assert "차단: 허용되지 않은 Bash 명령" in decoded
    assert "CLAUDE.md §11" in decoded


def test_entrypoint_allows_the_fixed_pytest_command(hooks_dir, repo_root, make_payload):
    payload = _bash(make_payload, "uv run pytest sample-project/tests -q", "tester")
    result = _run_hook(hooks_dir, repo_root, json.dumps(payload, ensure_ascii=False))
    assert result.returncode == 0


def test_entrypoint_allows_broken_stdin(hooks_dir, repo_root):
    result = _run_hook(hooks_dir, repo_root, "{ not json")
    assert result.returncode == 0


def test_entrypoint_honours_disable_switch(hooks_dir, repo_root, make_payload):
    payload = _bash(make_payload, "git diff --output=x.py", "reviewer")
    result = _run_hook(
        hooks_dir,
        repo_root,
        json.dumps(payload, ensure_ascii=False),
        env_extra={"PATCHPILOT_DISABLED_HOOKS": "all"},
    )
    assert result.returncode == 0
