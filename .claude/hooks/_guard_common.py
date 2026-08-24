"""PatchPilot 차단 Hook 공통 모듈.

`guard_test_files.py` 와 `guard_plan_scope.py` 가 공유하는 판정 재료만 담는다.
정책 자체는 각 가드가 갖고, 이 모듈은 payload 해석·경로 정규화·활성 run 조회·
`plan.md` 파싱처럼 두 가드가 똑같이 필요로 하는 것만 제공한다.

설계 원칙

* 파일을 쓰지 않는다. 로그도 남기지 않는다. 훅이 상태를 남기면 그 자체가
  실행 간 결정론의 변수가 되어 `evals/` 의 재현성을 깨뜨린다.
* 시각·난수·네트워크에 의존하지 않는다. 판정은 (payload, state.json, plan.md)
  세 입력만의 함수다.
* 판단할 수 없으면 통과시킨다. 훅 오류로 실행이 죽는 것이 위반을 한 번 놓치는
  것보다 나쁘다. 놓친 위반은 Reviewer 의 git diff 검토(`CLAUDE.md §15`)와
  Orchestrator 의 계획 검증(`patchpilot.md §2`)이 다시 잡는다.
"""

import json
import os
import re
import sys
from pathlib import Path

# PreToolUse 종료 코드. 2 만 도구 호출을 막고 stderr 를 모델에게 돌려준다.
ALLOW = 0
BLOCK = 2

# Phase 0 실측(46건)에서 확인한 서브에이전트 식별자.
# 값은 `.claude/agents/<name>.md` 의 frontmatter `name:` 과 같은 문자열이며,
# 메인 세션(Orchestrator) payload 에는 `agent_type` 키 자체가 없다.
AGENT_TYPES = frozenset({"planner", "developer", "tester", "reviewer"})

# Developer 의 tools 는 Read/Grep/Glob/Edit/Write 뿐이므로 파일을 쓰는 도구는 둘이다.
FILE_WRITE_TOOLS = frozenset({"Write", "Edit"})

# 담당 경로. 문자열이 아니라 경로 조각으로 두어 접두사 비교를 쓰지 않는다.
SAMPLE_PROJECT = ("sample-project",)
SAMPLE_TESTS = ("sample-project", "tests")

DISABLE_ENV = "PATCHPILOT_DISABLED_HOOKS"

# `CLAUDE.md §13` 의 7번 항목 제목. Agent 가 쓰는 제목에는 번호가 붙어
# 형태가 조금씩 달라지므로 제목 전체 일치가 아니라 키워드 포함으로 찾는다.
PLAN_SECTION_KEYWORD = "수정 허용 파일 목록"

_BACKTICK = re.compile(r"`([^`]+)`")


def repo_root() -> Path:
    """저장소 루트. 이 파일은 `<root>/.claude/hooks/` 에 있다."""
    return Path(__file__).resolve().parents[2]


def write_stderr(text: str) -> None:
    """stderr 로 UTF-8 바이트를 직접 쓴다.

    Windows 에서 `sys.stderr` 의 기본 인코딩은 콘솔 코드페이지(예: cp949)다.
    차단 메시지는 모델에게 그대로 전달되는 내용이므로, stdin 으로 받는 JSON 과 같은
    UTF-8 로 고정하지 않으면 근거와 다음 행동이 깨진 글자로 전달된다.
    """
    payload = text if text.endswith("\n") else text + "\n"
    buffer = getattr(sys.stderr, "buffer", None)
    if buffer is None:
        # 테스트 등에서 stderr 가 텍스트 전용 객체로 바뀐 경우.
        sys.stderr.write(payload)
        return
    buffer.write(payload.encode("utf-8"))
    buffer.flush()


def read_payload(stream) -> dict | None:
    """stdin 의 PreToolUse payload 를 dict 로 읽는다. 읽을 수 없으면 None.

    None 은 "판단할 재료가 없다" 는 뜻이며 호출자는 통과시켜야 한다.
    """
    try:
        raw = stream.read()
    except (OSError, UnicodeDecodeError):
        return None
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def is_disabled(hook_id: str) -> bool:
    """`PATCHPILOT_DISABLED_HOOKS` 에 자기 ID 나 `all` 이 있으면 True.

    쉼표로 나누고 공백을 없앤 뒤 대소문자를 무시하고 비교한다. 목록에 다른 훅의
    ID 나 모르는 값이 섞여 있어도 오류로 다루지 않는다.
    """
    raw = os.environ.get(DISABLE_ENV) or ""
    entries = {item.strip().casefold() for item in raw.split(",")}
    entries.discard("")
    return "all" in entries or hook_id.casefold() in entries


def disabled_notice(hook_id: str) -> str:
    """비활성 상태를 반드시 보이게 한다. 조용히 꺼져 있는 훅이 가장 위험하다."""
    return "[" + hook_id + "] 비활성화됨 (" + DISABLE_ENV + ") - 검사를 건너뜁니다"


def actor(payload: dict) -> object | None:
    """호출 주체를 가공 없이 돌려준다.

    메인 세션은 `agent_type` 키 자체가 없으므로 None 이 된다. 문자열이 아닌 값도
    그대로 넘겨서 호출자가 `AGENT_TYPES` 에 없는 "알 수 없는 주체" 로 판정하게 한다.
    """
    return payload.get("agent_type")


def actor_label(payload: dict) -> str:
    """차단 메시지에 쓸 주체 표기. agent_id 는 동시 실행되는 Agent 를 구분한다."""
    who = payload.get("agent_type")
    name = who if isinstance(who, str) and who else "메인 세션(Orchestrator)"
    identifier = payload.get("agent_id")
    if isinstance(identifier, str) and identifier:
        return "{0} (agent_id={1})".format(name, identifier)
    return str(name)


def target_path(payload: dict) -> str | None:
    """파일을 쓰는 도구 호출의 대상 경로. 대상이 아니면 None."""
    if payload.get("tool_name") not in FILE_WRITE_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    return file_path


def relative_parts(file_path: str, root: Path) -> tuple[str, ...] | None:
    """`file_path` 를 저장소 기준 상대 경로 조각으로 바꾼다. 저장소 밖이면 None.

    Phase 0 실측에서 `file_path` 는 12/12 절대 경로였고, 상대 경로로 지시해도
    도구가 절대 경로로 정규화해 전달했다. 그래도 상대 경로를 방어적으로 받는다.

    `..`, 심볼릭 링크, 드라이브 문자 대소문자, 슬래시 방향이 우회 수단이 되지
    않도록 `resolve()` 로 실제 경로를 구한 뒤 조각 단위로 비교한다.
    문자열 접두사 비교는 쓰지 않는다.
    """
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        base = root.resolve()
    except OSError:
        return None

    base_parts = [part.casefold() for part in base.parts]
    target_parts = list(resolved.parts)
    if len(target_parts) <= len(base_parts):
        return None
    if [part.casefold() for part in target_parts[: len(base_parts)]] != base_parts:
        return None
    return tuple(target_parts[len(base_parts):])


def is_under(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    """`parts` 가 `prefix` 디렉터리 하위인지 조각 단위로 판단한다."""
    if len(parts) <= len(prefix):
        return False
    head = tuple(part.casefold() for part in parts[: len(prefix)])
    return head == tuple(part.casefold() for part in prefix)


def to_posix(parts: tuple[str, ...]) -> str:
    return "/".join(parts)


def find_active_run(root: Path) -> tuple[Path | None, str | None]:
    """(활성 run 디렉터리, 모호 사유) 를 돌려준다.

    `reports/RUN-*/state.json` 의 `status` 가 `RUNNING` 인 것을 활성 run 으로 본다.
    Orchestrator 가 `patchpilot.md §1-5` 에서 만들고 `§10` 에서 마감하므로 동시에
    두 개일 수 없다. 새 포인터 파일을 만들지 않고 이미 있는 상태 파일만 읽는다.

    모호 사유가 있으면 호출자는 판정하지 말고 통과시켜야 한다. 잘못된 run 의
    `plan.md` 로 판정하는 것보다 통과가 안전하다.
    """
    reports = root / "reports"
    if not reports.is_dir():
        return None, None

    running: list[Path] = []
    # 정렬해서 순회 순서를 고정한다. 훅 판정에 디렉터리 나열 순서가 섞이면 안 된다.
    for run_dir in sorted(reports.glob("RUN-*")):
        state_file = run_dir / "state.json"
        if not state_file.is_file():
            continue
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            reason = "{0}/state.json 을 읽지 못했습니다 ({1})".format(
                run_dir.name, type(error).__name__
            )
            return None, reason
        if isinstance(state, dict) and state.get("status") == "RUNNING":
            running.append(run_dir)

    if not running:
        return None, None
    if len(running) > 1:
        names = ", ".join(run_dir.name for run_dir in running)
        return None, "RUNNING 상태의 run 이 {0}개입니다: {1}".format(len(running), names)
    return running[0], None


def plan_allowed_files(plan_text: str) -> list[str]:
    """`plan.md` 의 수정 허용 파일 목록을 등장 순서대로 돌려준다. (`CLAUDE.md §13`)

    목록 항목만 읽는다. 같은 절의 산문에는 범위 밖 파일이 근거로 함께 언급되는
    경우가 있어서 산문까지 읽으면 허용 목록이 실제보다 넓게 잡힌다.

    `evals/eval_harness.py` 의 `plan_allowed_files()` 와 같은 결과를 내야 한다.
    두 파서가 갈라지면 `evals/tests/test_plan_parser_agreement.py` 가 실패한다.
    """
    collected: list[str] = []
    inside = False
    for line in plan_text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = PLAN_SECTION_KEYWORD in line
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        for match in _BACKTICK.findall(stripped):
            candidate = match.strip()
            if candidate.startswith("sample-project/") and candidate not in collected:
                collected.append(candidate)
    return collected


def allowed_lookup(entries: list[str]) -> set[tuple[str, ...]]:
    """허용 목록을 비교용 경로 조각 집합으로 바꾼다.

    비교는 완전 일치로만 한다. 접두사 비교를 쓰면 `service_charge.py` 를 허용했을 때
    `service_charge.py.bak` 까지 열리기 때문이다.
    """
    lookup: set[tuple[str, ...]] = set()
    for entry in entries:
        cleaned = entry.replace("\\", "/")
        parts = tuple(part for part in cleaned.split("/") if part and part != ".")
        if not parts or ".." in parts:
            continue
        lookup.add(tuple(part.casefold() for part in parts))
    return lookup


def matches_allowed(parts: tuple[str, ...], lookup: set[tuple[str, ...]]) -> bool:
    """허용 목록 완전 일치 여부."""
    return tuple(part.casefold() for part in parts) in lookup
