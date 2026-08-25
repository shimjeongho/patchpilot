"""PreToolUse 가드 — Tester / Reviewer 의 Bash 를 역할별 화이트리스트로 제한한다.

`CLAUDE.md §11` 은 Tester 와 Reviewer 에게 제품 코드 수정 권한이 없다고 정한다.
그런데 두 Agent 만 Bash 를 갖고 있어(`tester.md`, `reviewer.md` frontmatter),
`guard_test_files.py` 와 `guard_plan_scope.py` 가 지키는 Write/Edit 경로를 거치지 않고
셸에서 파일을 만들 수 있다. 이 가드는 그 경로를 닫는다.

Claude Code 2.1.241 실측으로 확인한 전제

* Agent frontmatter 의 `Bash(git diff:*)` 같은 세부 스코프는 지원되지 않는다.
  `tools:` 는 `Bash` 하나로 평탄화되므로 명령 단위 집행 수단이 될 수 없다.
* Bash PreToolUse payload 에도 `agent_type` / `agent_id` 가 온다. 역할 분리는
  여기서만 가능하다. `settings.json` 의 `permissions` 는 세션 전역이라 못 한다.
* 평가 순서는 PreToolUse Hook -> permissions -> 실행이다. 훅의 차단이
  `permissions.allow` 보다 우선하므로 이 가드가 1차 집행자다.
* `git diff --output=<path>` 가 실제 저장소에서 파일을 생성하는 것을 실측했다.
  셸 리다이렉션이 아니라 git 자체 옵션이라 Claude Code 내장 가드에 걸리지 않는다.
  그래서 옵션은 "위험한 것을 찾아 막는" 방식이 아니라 "허용된 것만 통과시키는"
  방식으로 검사한다. 새 옵션이 생겨도 자동으로 거부된다.

담당 범위는 `Bash` 도구와 `tester` / `reviewer` 두 주체뿐이다. 그 밖은 판단하지 않는다.

종료 코드: 0 = 허용, 2 = 차단.
"""

import re
import sys
from pathlib import Path

# 훅은 패키지가 아니라 단독 스크립트로 실행되므로 형제 모듈을 경로로 찾는다.
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _guard_common as common  # noqa: E402

HOOK_ID = "guard-bash-scope"

# 이 가드가 판정하는 주체. 나머지는 담당 범위 밖이다.
GUARDED_AGENTS = frozenset({"tester", "reviewer"})

# `CLAUDE.md §10` 의 고정 테스트 명령. 토큰까지 정확히 일치해야 한다.
# 인자를 하나라도 더 붙이면 실행 범위가 달라져 전체 테스트 판정이 아니게 된다.
TESTER_PYTEST_TOKENS = ("uv", "run", "pytest", "sample-project/tests", "-q")

# 아래 옵션 집합은 전부 `reports/` 실측에서 확인된 형태만 담는다.
# "있을 것 같다" 는 이유로 넓히지 않는다.
TESTER_STATUS_FLAGS = frozenset({"--porcelain", "--short", "-s"})
TESTER_DIFF_FLAGS = frozenset({"--stat"})

REVIEWER_STATUS_FLAGS = frozenset(
    {"--porcelain", "--short", "-s", "--untracked-files=all", "--ignored"}
)
REVIEWER_DIFF_FLAGS = frozenset({"--stat", "--cached", "--no-index", "-u"})
REVIEWER_LOG_FLAGS = frozenset({"--oneline"})
CHECK_IGNORE_FLAGS = frozenset({"-v"})
GNU_DIFF_FLAGS = frozenset({"-u", "--strip-trailing-cr"})
CAT_FLAGS = frozenset({"-n"})
GREP_FLAGS = frozenset({"-r", "-n", "-c", "-rn"})

# `git log --oneline -5` 의 개수 지정. 숫자만 허용한다.
_COUNT_OPTION = re.compile(r"^-[0-9]+$")
# `git diff <sha> -- <path>` 의 리비전. 짧은 해시와 HEAD 만 받는다.
_REVISION = re.compile(r"^(HEAD|[0-9a-fA-F]{7,40})$")


def _paths_ok(arguments: list, root: Path) -> str | None:
    """모든 인자가 저장소 안의 경로인지 확인한다. 문제가 있으면 사유 문자열."""
    for argument in arguments:
        if common.repo_relative_arg(argument, root) is None:
            return "저장소 밖이거나 형태가 올바르지 않은 경로 인자: " + argument
    return None


def _split_flags(rest: list, allowed: frozenset) -> tuple:
    """(위치 인자 목록, 사유). 허용 목록에 없는 옵션이면 즉시 사유를 만든다."""
    positional = []
    for token in rest:
        if token.startswith("-"):
            if token not in allowed:
                return [], "허용되지 않은 옵션: " + token
            continue
        positional.append(token)
    return positional, None


def _check_no_positional(rest: list, allowed: frozenset) -> str | None:
    """옵션만 받고 위치 인자는 받지 않는 명령."""
    positional, reason = _split_flags(rest, allowed)
    if reason is not None:
        return reason
    if positional:
        return "이 명령에는 위치 인자를 붙일 수 없다: " + " ".join(positional)
    return None


def _check_flags_then_paths(
    rest: list, allowed: frozenset, root: Path, minimum: int, maximum: int | None
) -> str | None:
    """옵션 뒤에 저장소 경로가 오는 형태."""
    positional, reason = _split_flags(rest, allowed)
    if reason is not None:
        return reason
    if len(positional) < minimum:
        return "경로 인자가 {0}개 이상 필요하다".format(minimum)
    if maximum is not None and len(positional) > maximum:
        return "경로 인자는 최대 {0}개다".format(maximum)
    return _paths_ok(positional, root)


def _check_git_diff(rest: list, allowed: frozenset, root: Path) -> str | None:
    """`git diff` 계열. 구분자 앞은 리비전/경로, 뒤는 경로만 온다.

    `--output=` / `-O` / `--ext-diff` 는 개별 차단 규칙이 아니라 허용 옵션 목록에
    없다는 이유로 자동으로 걸린다. 새 옵션이 추가돼도 같은 방식으로 걸린다.
    """
    separated = False
    before = []
    after = []
    for token in rest:
        if token == "--":
            if separated:
                return "경로 구분자가 두 번 나왔다"
            separated = True
            continue
        if separated:
            after.append(token)
            continue
        if token.startswith("-"):
            if token not in allowed:
                return "허용되지 않은 옵션: " + token
            continue
        before.append(token)

    if len(before) > 1:
        return "구분자 앞의 위치 인자는 하나까지다: " + " ".join(before)
    for token in before:
        if _REVISION.match(token):
            continue
        if common.repo_relative_arg(token, root) is None:
            return "리비전도 저장소 경로도 아닌 인자: " + token
    return _paths_ok(after, root)


def _check_git_log(rest: list) -> str | None:
    """`git log --oneline -5` 형태. 개수 지정만 예외로 받는다."""
    for token in rest:
        if _COUNT_OPTION.match(token):
            continue
        if token.startswith("-"):
            if token not in REVIEWER_LOG_FLAGS:
                return "허용되지 않은 옵션: " + token
            continue
        return "git log 에는 위치 인자를 붙일 수 없다: " + token
    return None


def _check_git_hash_object(rest: list, root: Path) -> str | None:
    """`git hash-object --path <p> <p>` 형태.

    `-w` 는 오브젝트 DB 에 실제로 기록하므로 허용 목록에 두지 않는다.
    """
    paths = []
    expect_path_value = False
    for token in rest:
        if expect_path_value:
            paths.append(token)
            expect_path_value = False
            continue
        if token == "--path":
            expect_path_value = True
            continue
        if token.startswith("-"):
            return "허용되지 않은 옵션: " + token
        paths.append(token)
    if expect_path_value:
        return "--path 뒤에 경로가 없다"
    if not paths:
        return "경로 인자가 1개 이상 필요하다"
    return _paths_ok(paths, root)


def _check_grep(rest: list, root: Path) -> str | None:
    """`grep -rn <패턴> <경로>` 형태. 첫 위치 인자가 패턴, 나머지가 경로다."""
    positional, reason = _split_flags(rest, GREP_FLAGS)
    if reason is not None:
        return reason
    if len(positional) < 2:
        return "패턴과 경로 인자가 각각 필요하다"
    return _paths_ok(positional[1:], root)


def _check_tester(tokens: list, root: Path) -> str | None:
    """Tester 정책. `CLAUDE.md §10`, `§21`, `tester.md §3`."""
    if tuple(tokens) == TESTER_PYTEST_TOKENS:
        return None
    if tokens[:1] == ["uv"]:
        return (
            "CLAUDE.md §10 의 고정 명령과 정확히 일치하지 않는다. 허용되는 형태는 "
            + " ".join(TESTER_PYTEST_TOKENS)
            + " 하나뿐이다"
        )
    if tokens[:2] == ["git", "status"]:
        return _check_no_positional(tokens[2:], TESTER_STATUS_FLAGS)
    if tokens[:2] == ["git", "diff"]:
        return _check_no_positional(tokens[2:], TESTER_DIFF_FLAGS)
    return "Tester 화이트리스트에 없는 명령이다"


def _check_reviewer(tokens: list, root: Path) -> str | None:
    """Reviewer 정책. `CLAUDE.md §15`, `reviewer.md §3`."""
    if tokens[:2] == ["git", "status"]:
        return _check_no_positional(tokens[2:], REVIEWER_STATUS_FLAGS)
    if tokens[:2] == ["git", "diff"]:
        return _check_git_diff(tokens[2:], REVIEWER_DIFF_FLAGS, root)
    if tokens[:2] == ["git", "log"]:
        return _check_git_log(tokens[2:])
    if tokens[:2] == ["git", "check-ignore"]:
        return _check_flags_then_paths(tokens[2:], CHECK_IGNORE_FLAGS, root, 1, None)
    if tokens[:2] == ["git", "hash-object"]:
        return _check_git_hash_object(tokens[2:], root)
    if tokens[:2] == ["git", "config"]:
        # 읽기 전용 조회만 허용한다. 값이 붙으면 설정 변경이다.
        if tokens == ["git", "config", "core.autocrlf"]:
            return None
        return "git config 는 core.autocrlf 조회만 허용한다"
    if tokens[:1] == ["diff"]:
        return _check_flags_then_paths(tokens[1:], GNU_DIFF_FLAGS, root, 2, 2)
    if tokens[:1] == ["cat"]:
        return _check_flags_then_paths(tokens[1:], CAT_FLAGS, root, 1, None)
    if tokens[:1] == ["grep"]:
        return _check_grep(tokens[1:], root)
    return "Reviewer 화이트리스트에 없는 명령이다"


def _next_action(who: str) -> list:
    """차단 뒤 무엇을 해야 하는지. 주체마다 남은 수단이 다르다."""
    if who == "tester":
        return [
            "테스트는 uv run pytest sample-project/tests -q 하나로만 실행한다. (CLAUDE.md §10)",
            "회귀 테스트 추가는 Bash 가 아니라 Write 도구로 한다. (CLAUDE.md §21)",
            "테스트가 잘못됐다고 판단되면 고치지 말고 TEST_DEFECT 로 분류하라. (CLAUDE.md §14)",
        ]
    return [
        "파일 내용 확인은 Bash 가 아니라 Read / Grep / Glob 도구로 한다.",
        "변경 확인은 허용된 git status / git diff 형태로만 한다. (CLAUDE.md §15)",
        "테스트 실행은 Reviewer 의 권한이 아니다. (reviewer.md §5)",
    ]


def _block_message(payload: dict, command: str, who: str, reason: str) -> str:
    lines = [
        "[" + HOOK_ID + "] 차단: 허용되지 않은 Bash 명령",
        "  명령  : " + command,
        "  행위자: " + common.actor_label(payload),
        "  사유  : " + reason,
        "",
        "  근거  :",
        "    CLAUDE.md §11 (Tester / Reviewer - 제품 코드 수정 금지)",
        "    CLAUDE.md §3-1 (수정 대상은 sample-project/ 하위로 제한)",
        "    tester.md §5 / reviewer.md §5 (Bash 로 파일을 수정하는 모든 행위 금지)",
        "",
        "  다음 행동:",
    ]
    lines.extend("    " + item for item in _next_action(who))
    return "\n".join(lines)


def decide(payload: dict, root: Path) -> tuple:
    """(종료 코드, stderr 메시지) 를 돌려주는 순수 판정 함수.

    파일을 쓰지 않고 시각·난수·네트워크에 의존하지 않는다. 같은 입력이면 항상 같은 결과다.
    """
    if common.is_disabled(HOOK_ID):
        return common.ALLOW, common.disabled_notice(HOOK_ID)

    if payload.get("tool_name") != common.BASH_TOOL:
        return common.ALLOW, None

    who = common.actor(payload)
    if who is None:
        # 메인 세션(Orchestrator). `patchpilot.md` 의 allowed-tools 와 settings 의
        # permissions 가 담당한다. 여기서 다시 막으면 Harness 개발 자체를 방해한다.
        return common.ALLOW, None
    if who not in GUARDED_AGENTS:
        if isinstance(who, str) and who in common.AGENT_TYPES:
            # planner / developer 는 tools 에 Bash 자체가 없다. 담당 범위 밖이다.
            return common.ALLOW, None
        # 알 수 없는 주체. Write/Edit 가드는 담당 **경로** 안에서 이런 주체를 막지만,
        # 이 가드의 담당 축은 경로가 아니라 주체다. 모르는 주체의 Bash 를 전부 막으면
        # Harness 개발에 쓰는 다른 서브에이전트까지 멈춘다. 통과시키되 반드시 보이게 한다.
        return common.ALLOW, "[{0}] 경고: 담당 범위 밖의 주체 {1} - 검사를 건너뜁니다".format(
            HOOK_ID, common.actor_label(payload)
        )

    command = common.bash_command(payload)
    if command is None:
        return common.ALLOW, "[{0}] 경고: 명령 문자열이 없어 검사를 건너뜁니다".format(HOOK_ID)

    found = common.shell_metacharacter(command)
    if found is not None:
        character, description = found
        reason = "셸 합성 요소 {0} ({1}) 가 있다. 단일 명령만 허용한다".format(
            character, description
        )
        return common.BLOCK, _block_message(payload, command, who, reason)

    tokens = common.split_bash_tokens(command)
    if not tokens:
        return common.BLOCK, _block_message(
            payload, command, who, "인용부호가 맞지 않아 명령을 토큰으로 나눌 수 없다"
        )

    checker = _check_tester if who == "tester" else _check_reviewer
    reason = checker(tokens, root)
    if reason is None:
        return common.ALLOW, None
    return common.BLOCK, _block_message(payload, command, who, reason)


def main() -> int:
    try:
        payload = common.read_payload(sys.stdin)
        if payload is None:
            return common.ALLOW
        code, message = decide(payload, common.repo_root())
    except Exception as error:
        # 훅의 오류가 도구 호출을 막아서는 안 된다. 오류를 숨기지 않고 stderr 로
        # 남긴 뒤 통과시킨다. (`CLAUDE.md §8` - 조용히 무시하지 않는다)
        common.write_stderr(
            "[{0}] 검사를 건너뜁니다 (예상치 못한 오류 {1}: {2})".format(
                HOOK_ID, type(error).__name__, error
            )
        )
        return common.ALLOW

    if message:
        common.write_stderr(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
