"""Stop 가드 — 종료 선언과 실제 산출물의 결정론적 모순을 종료 직전에 한 번 대조한다.

`CLAUDE.md §19` 는 최종 실행 상태를 Orchestrator 가 결정한다고 정한다. 그 결정은
`reports/<run-id>/state.json` 의 `final_status` 로 선언되고, 근거는 같은 폴더의
산출물이어야 한다(`patchpilot.md §0-6`). 이 가드는 선언과 근거가 **서로 모순되는
경우에만** 종료를 한 번 막고, 발견한 모순을 그대로 Orchestrator 에게 돌려준다.

Claude Code 2.1.241 실측으로 확인한 전제

* Stop 훅 등록은 중첩형(`"Stop": [{"hooks": [...]}]`)이어야 한다. 평면형은 파싱
  오류 없이 조용히 무시된다.
* 판정은 종료 코드가 아니라 stdout 의 JSON 으로 전달한다.
  `{"decision": "block", "reason": ...}` + exit 0 이다. exit 2 + stderr 도 차단은
  되지만 훅 커맨드 라인 전문이 모델 컨텍스트에 그대로 실린다.
* 차단 이후 이어진 assistant turn 이 끝나면 Stop 훅이 **다시 호출될 수 있고**,
  그때 payload 의 `stop_hook_active` 가 참이 된다.
* 훅 프로세스의 `CLAUDE_CODE_SESSION_ID` 와 Stop payload 의 `session_id` 는 같다.

따라서 "한 user prompt 안에서 최대 한 번만 차단한다" 는 성질은 런타임이 아니라
이 파일의 `stop_hook_active` 분기가 직접 보장한다. 그 분기를 지우면
Stop -> block -> Stop 재호출 루프가 반복된다. 방어 코드가 아니라 필수 제어 흐름이다.

설계 원칙은 다른 가드와 같다.

* 파일을 쓰지 않고 상태를 남기지 않는다. 판정은 (payload, state.json, 산출물)
  만의 함수이며 시각·난수·네트워크·git 에 의존하지 않는다.
* 확실하게 모순이라고 증명할 수 있을 때만 막는다. 판단할 수 없으면 통과시킨다.
  읽지 못한 파일을 "없음" 으로 취급하지 않는다. 디스크 오류가 차단 근거가 되면
  이 원칙이 곧바로 깨진다.
* 산출물의 의미를 해석하지 않는다. 첫 줄 비교는 `patchpilot.md §4-1` / `§7-1` 과
  같이 완전 일치로만 한다. 실패 원인 분류나 change-log 본문은 읽지 않는다.

판정 전달: 항상 exit 0. 차단은 stdout JSON 으로만 알린다.
"""

import sys
from collections import namedtuple
from pathlib import Path

# 훅은 패키지가 아니라 단독 스크립트로 실행되므로 형제 모듈을 경로로 찾는다.
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _guard_common as common  # noqa: E402

HOOK_ID = "guard-stop-gate"

# Stop 은 종료 코드로 판정을 표현하지 않는다. 두 값 모두 프로세스는 0 으로 끝난다.
DECISION_ALLOW = "allow"
DECISION_BLOCK = "block"

STOP_EVENT = "Stop"

FINAL_SUCCESS = "SUCCESS"
FINAL_BLOCKED = "BLOCKED"
FINAL_STATUSES = frozenset({FINAL_SUCCESS, FINAL_BLOCKED})

# `patchpilot.md §10` 이 열거한 사유 코드. 목록 밖의 값은 계약 위반이다.
BLOCKED_REASONS = frozenset(
    {
        "PLANNER_NO_OUTPUT",
        "PLAN_INCOMPLETE",
        "PLAN_SCOPE_VIOLATION",
        "DEVELOPER_NO_OUTPUT",
        "SCOPE_OUT_OF_PLAN",
        "TESTER_INVALID_STATUS",
        "INVALID_FAILURE_CATEGORY",
        "TEST_DEFECT_NEEDS_HUMAN",
        "ENVIRONMENT_ERROR",
        "UNKNOWN_TWICE",
        "RETRY_BUDGET_EXCEEDED",
        "REVIEWER_INVALID_VERDICT",
        "REVIEW_CHANGES_REQUESTED_NO_BUDGET",
    }
)

REASON_RETRY_BUDGET_EXCEEDED = "RETRY_BUDGET_EXCEEDED"
REASON_REVIEW_NO_BUDGET = "REVIEW_CHANGES_REQUESTED_NO_BUDGET"
REASON_REVIEWER_INVALID = "REVIEWER_INVALID_VERDICT"
REASON_PLANNER_NO_OUTPUT = "PLANNER_NO_OUTPUT"

# 기계 판정 대상 첫 줄. 해석하지 않고 완전 일치로만 비교한다.
VERDICT_APPROVED = "VERDICT: APPROVED"
VERDICT_CHANGES_REQUESTED = "VERDICT: CHANGES_REQUESTED"
STATUS_PASS = "STATUS: PASS"

PLAN_FILE = "plan.md"
REVIEW_FILE = "review.md"
REPORT_FILE = "report.md"
STATE_FILE = "state.json"

# 파일을 읽지 못한 이유. "없음" 과 "읽지 못함" 을 구분하기 위한 값이다.
MISSING = "missing"
UNREADABLE = "unreadable"

# 확인된 위반 하나. 기대·실제·근거를 함께 들고 다녀야 reason 이 재구성 가능해진다.
Violation = namedtuple("Violation", "gid expected actual evidence")


def _is_integer(value) -> bool:
    """정수인지 확인한다. bool 은 int 의 하위형이므로 제외한다."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_plain_name(value) -> bool:
    """run 디렉터리 바로 아래의 파일 이름인지 확인한다.

    경로 조각이 섞인 값은 판단하지 않는다. 훅이 run 디렉터리 밖을 보게 되면
    판정 범위가 조용히 넓어진다.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    if "/" in value or "\\" in value:
        return False
    return value not in (".", "..")


class RunArtifacts:
    """run 디렉터리의 산출물을 읽고 읽기 실패를 기억한다.

    읽지 못한 파일을 "없음" 으로 취급하지 않는다. 그 구분이 없으면 디스크 오류
    하나가 곧바로 차단 근거가 된다.
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.skipped: list = []

    def evidence(self, name: str) -> str:
        return "reports/{0}/{1}".format(self.run_dir.name, name)

    def exists(self, name: str):
        """존재하면 True, 없으면 False, 확인 자체가 실패하면 None."""
        try:
            return (self.run_dir / name).is_file()
        except OSError:
            self._skip(name, "존재 여부를 확인하지 못했습니다")
            return None

    def first_line(self, name: str):
        """(첫 줄, 문제) 를 돌려준다. 문제는 MISSING / UNREADABLE / None."""
        present = self.exists(name)
        if present is None:
            return None, UNREADABLE
        if not present:
            return None, MISSING
        try:
            text = (self.run_dir / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._skip(name, "읽지 못했습니다")
            return None, UNREADABLE
        return common.first_line(text), None

    def _skip(self, name: str, detail: str) -> None:
        self.skipped.append(
            "{0} 을 {1} - 해당 검사만 건너뜁니다".format(self.evidence(name), detail)
        )


def _last_attempt(state: dict):
    """attempts 의 마지막 항목. 목록이 아니거나 비어 있으면 None."""
    attempts = state.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return None
    last = attempts[-1]
    return last if isinstance(last, dict) else None


def _check_common(state: dict, artifacts: RunArtifacts, notes: list) -> list:
    """SUCCESS / BLOCKED 어느 쪽이든 성립해야 하는 마감 계약. (G1~G6)"""
    violations = []
    evidence = artifacts.evidence(STATE_FILE)

    status = state.get("status")
    final_status = state.get("final_status")
    if status != final_status:
        violations.append(
            Violation(
                "G1",
                "status 와 final_status 가 같음",
                "status={0!r} / final_status={1!r}".format(status, final_status),
                evidence,
            )
        )

    current_stage = state.get("current_stage")
    if current_stage != "DONE":
        violations.append(
            Violation("G2", 'current_stage == "DONE"', repr(current_stage), evidence)
        )

    finished_at = state.get("finished_at")
    if finished_at is None or (isinstance(finished_at, str) and not finished_at.strip()):
        violations.append(
            Violation("G3", "finished_at 이 기록됨", repr(finished_at), evidence)
        )

    if artifacts.exists(REPORT_FILE) is False:
        violations.append(
            Violation("G4", "report.md 존재", "없음", artifacts.evidence(REPORT_FILE))
        )

    attempts = state.get("attempts")
    if isinstance(attempts, list):
        for index, attempt in enumerate(attempts, start=1):
            if not isinstance(attempt, dict):
                continue
            for key in ("change_log", "test_result"):
                name = attempt.get(key)
                if not _is_plain_name(name):
                    continue
                if artifacts.exists(name) is False:
                    violations.append(
                        Violation(
                            "G5",
                            "attempts[{0}].{1} 이 가리키는 파일 존재".format(index, key),
                            "없음",
                            artifacts.evidence(name),
                        )
                    )

    retry_count = state.get("retry_count")
    retry_budget = state.get("retry_budget")
    if _is_integer(retry_count) and _is_integer(retry_budget):
        if not 0 <= retry_count <= retry_budget:
            violations.append(
                Violation(
                    "G6",
                    "0 <= retry_count <= retry_budget",
                    "retry_count={0} / retry_budget={1}".format(retry_count, retry_budget),
                    evidence,
                )
            )
    else:
        notes.append(
            "[{0}] retry_count / retry_budget 이 정수가 아니어서 G6 을 건너뜁니다".format(
                HOOK_ID
            )
        )

    return violations


def _check_success(state: dict, artifacts: RunArtifacts) -> list:
    """final_status == SUCCESS 일 때만 성립해야 하는 계약. (G7~G13)

    근거는 `patchpilot.md §8` 이다. SUCCESS 는 최종 `test-result-N.md` 가
    `STATUS: PASS` 이고 `review.md` 가 `VERDICT: APPROVED` 일 때만 쓸 수 있다.
    """
    violations = []
    evidence = artifacts.evidence(STATE_FILE)

    blocked_reason = state.get("blocked_reason")
    if blocked_reason is not None:
        violations.append(
            Violation("G7", "blocked_reason 이 null", repr(blocked_reason), evidence)
        )

    if artifacts.exists(PLAN_FILE) is False:
        violations.append(
            Violation("G8", "plan.md 존재", "없음", artifacts.evidence(PLAN_FILE))
        )

    review_line, review_problem = artifacts.first_line(REVIEW_FILE)
    if review_problem == MISSING:
        violations.append(
            Violation("G9", "review.md 존재", "없음", artifacts.evidence(REVIEW_FILE))
        )
    elif review_problem is None and review_line != VERDICT_APPROVED:
        violations.append(
            Violation(
                "G10",
                "review.md 첫 줄이 " + VERDICT_APPROVED,
                repr(review_line),
                artifacts.evidence(REVIEW_FILE),
            )
        )

    review = state.get("review")
    if isinstance(review, dict) and review.get("verdict") != "APPROVED":
        violations.append(
            Violation(
                "G11",
                'review.verdict == "APPROVED"',
                repr(review.get("verdict")),
                evidence,
            )
        )

    last = _last_attempt(state)
    if last is None:
        violations.append(
            Violation(
                "G12",
                "attempts 에 최소 1건이 기록됨",
                repr(state.get("attempts")),
                evidence,
            )
        )
    else:
        name = last.get("test_result")
        if _is_plain_name(name):
            line, problem = artifacts.first_line(name)
            if problem == MISSING:
                violations.append(
                    Violation(
                        "G12",
                        "마지막 attempt 의 test_result 파일 존재",
                        "없음",
                        artifacts.evidence(name),
                    )
                )
            elif problem is None and line != STATUS_PASS:
                violations.append(
                    Violation(
                        "G12",
                        "마지막 test-result 첫 줄이 " + STATUS_PASS,
                        repr(line),
                        artifacts.evidence(name),
                    )
                )
        if last.get("status") != "PASS":
            violations.append(
                Violation(
                    "G13",
                    '마지막 attempt 의 status == "PASS"',
                    repr(last.get("status")),
                    evidence,
                )
            )

    return violations


def _check_blocked(state: dict, artifacts: RunArtifacts) -> list:
    """final_status == BLOCKED 일 때만 성립해야 하는 계약. (G14~G19)

    사유 코드마다 추가로 볼 수 있는 것은 "파일 존재" 와 "고정된 첫 줄" 뿐이다.
    실패 원인 분류처럼 Agent 가 쓰는 본문을 다시 파싱해야 하는 사유 코드는
    검사하지 않는다. 파서가 하나 더 생기면 그 파서가 오탐의 원인이 된다.
    """
    violations = []
    evidence = artifacts.evidence(STATE_FILE)
    blocked_reason = state.get("blocked_reason")

    if blocked_reason not in BLOCKED_REASONS:
        violations.append(
            Violation(
                "G14",
                "blocked_reason 이 patchpilot.md §10 의 사유 코드 중 하나",
                repr(blocked_reason),
                evidence,
            )
        )

    if blocked_reason == REASON_RETRY_BUDGET_EXCEEDED:
        retry_count = state.get("retry_count")
        retry_budget = state.get("retry_budget")
        if _is_integer(retry_count) and _is_integer(retry_budget):
            if retry_count < retry_budget:
                violations.append(
                    Violation(
                        "G15",
                        "RETRY_BUDGET_EXCEEDED 이면 retry_count >= retry_budget",
                        "retry_count={0} / retry_budget={1}".format(
                            retry_count, retry_budget
                        ),
                        evidence,
                    )
                )

    if blocked_reason == REASON_REVIEW_NO_BUDGET:
        line, problem = artifacts.first_line(REVIEW_FILE)
        if problem == MISSING:
            violations.append(
                Violation(
                    "G16",
                    "REVIEW_CHANGES_REQUESTED_NO_BUDGET 이면 review.md 존재",
                    "없음",
                    artifacts.evidence(REVIEW_FILE),
                )
            )
        elif problem is None and line != VERDICT_CHANGES_REQUESTED:
            violations.append(
                Violation(
                    "G16",
                    "review.md 첫 줄이 " + VERDICT_CHANGES_REQUESTED,
                    repr(line),
                    artifacts.evidence(REVIEW_FILE),
                )
            )

    if blocked_reason == REASON_REVIEWER_INVALID:
        line, problem = artifacts.first_line(REVIEW_FILE)
        if problem is None and line in (VERDICT_APPROVED, VERDICT_CHANGES_REQUESTED):
            violations.append(
                Violation(
                    "G17",
                    "REVIEWER_INVALID_VERDICT 이면 review.md 첫 줄이 기계 판정 가능한 값이 아님",
                    repr(line),
                    artifacts.evidence(REVIEW_FILE),
                )
            )

    if blocked_reason == REASON_PLANNER_NO_OUTPUT:
        if artifacts.exists(PLAN_FILE) is True:
            violations.append(
                Violation(
                    "G18",
                    "PLANNER_NO_OUTPUT 이면 plan.md 가 없음",
                    "존재함",
                    artifacts.evidence(PLAN_FILE),
                )
            )

    review = state.get("review")
    if isinstance(review, dict) and review.get("verdict") == "APPROVED":
        # `patchpilot.md §7-1` 에서 APPROVED 는 Tester PASS 이후에만 나온다.
        # 그 상태는 `§8` 의 SUCCESS 조건 두 개를 모두 만족하므로 BLOCKED 와 공존할 수 없다.
        violations.append(
            Violation(
                "G19",
                "BLOCKED 종료에서 review.verdict 가 APPROVED 가 아님",
                '"APPROVED"',
                evidence,
            )
        )

    return violations


NEXT_ACTIONS = (
    "위 불변식과 관련된 산출물만 확인한다.",
    "사실과 다른 state.json / report.md 값을 임의로 맞추지 않는다.",
    "필요한 단계가 누락됐다면 해당 단계를 수행한다."
    " (Reviewer 미호출 -> patchpilot.md §7, Tester 재실행 -> §4)",
    "교정이 불가능하면 SUCCESS 를 유지하지 말고"
    " CLAUDE.md §19 / patchpilot.md §8 의 규칙에 따라 최종 상태를 다시 판정한다.",
    "사용자에게 최종 보고할 때 Stop Gate 가 발견한 불일치를 숨기지 않는다.",
)

# 재진입 호출에서는 재검사 없이 통과하므로, 교정 기회가 이번 턴뿐이라는 사실을
# 모델에게 명시한다. 이 문장이 없으면 "다음에 또 검사되겠지" 로 오해할 수 있다.
REENTRY_NOTICE = (
    "참고: 이 게이트는 한 user prompt 안에서 한 번만 차단한다.\n"
    "      이어지는 턴의 종료는 stop_hook_active 재진입 호출에서\n"
    "      재검사 없이 통과하므로, 가능한 교정은 이번 턴에서 완료해야 한다."
)


def build_reason(run_id: str, final_status: str, violations: list) -> str:
    """차단 메시지를 만든다.

    payload 는 넣지 않는다. `transcript_path` / `cwd` / `last_assistant_message`
    는 판정 근거가 아니므로 모델에게 되돌려 줄 이유가 없다.
    """
    lines = [
        "[" + HOOK_ID + "] 종료 상태 불일치",
        "",
        "Run:",
        run_id,
        "",
        "Final status:",
        final_status,
        "",
        "확인된 위반:",
    ]
    for violation in violations:
        lines.append("- [{0}] 기대: {1}".format(violation.gid, violation.expected))
        lines.append("       실제: {0}".format(violation.actual))
        lines.append("       근거: {0}".format(violation.evidence))
    lines.append("")
    lines.append("다음 행동:")
    for index, action in enumerate(NEXT_ACTIONS, start=1):
        lines.append("{0}. {1}".format(index, action))
    lines.append("")
    lines.append(REENTRY_NOTICE)
    return "\n".join(lines)


def decide(payload: dict, root: Path) -> tuple:
    """(결정, reason, 경고 목록) 을 돌려주는 순수 판정 함수.

    파일을 쓰지 않고 시각·난수·네트워크에 의존하지 않는다. 같은 입력이면 항상
    같은 결과다. reason 은 차단할 때만 채워진다.
    """
    notes: list = []

    if common.is_disabled(HOOK_ID):
        return DECISION_ALLOW, None, [common.disabled_notice(HOOK_ID)]

    if payload.get("hook_event_name") != STOP_EVENT:
        return DECISION_ALLOW, None, notes

    if payload.get("stop_hook_active"):
        # 차단 직후의 재진입 호출이다. 여기서 다시 막으면 Stop -> block -> Stop
        # 루프가 끝나지 않는다. 참 같은 값이면 모두 재진입으로 본다.
        return DECISION_ALLOW, None, notes

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return DECISION_ALLOW, None, notes

    matched, unreadable = common.find_run_by_session(root, session_id)
    if unreadable:
        notes.append(
            "[{0}] state.json 을 읽지 못한 run 이 있습니다: {1}".format(
                HOOK_ID, ", ".join(unreadable)
            )
        )
    if not matched:
        return DECISION_ALLOW, None, notes
    if len(matched) > 1:
        names = ", ".join(run_dir.name for run_dir, _ in matched)
        notes.append(
            "[{0}] 같은 session_id 에 귀속되는 run 이 {1}개입니다: {2}"
            " - 검사를 건너뜁니다".format(HOOK_ID, len(matched), names)
        )
        return DECISION_ALLOW, None, notes

    run_dir, state = matched[0]
    final_status = state.get("final_status")
    if final_status is None:
        # 실행 중이거나 아직 마감하지 않은 run 이다. 일반 turn 을 막지 않는다.
        return DECISION_ALLOW, None, notes
    if final_status not in FINAL_STATUSES:
        notes.append(
            "[{0}] {1} 의 final_status 가 계약 밖의 값입니다: {2!r}"
            " - 검사를 건너뜁니다".format(HOOK_ID, run_dir.name, final_status)
        )
        return DECISION_ALLOW, None, notes

    artifacts = RunArtifacts(run_dir)
    violations = _check_common(state, artifacts, notes)
    if final_status == FINAL_SUCCESS:
        violations.extend(_check_success(state, artifacts))
    else:
        violations.extend(_check_blocked(state, artifacts))

    notes.extend("[{0}] {1}".format(HOOK_ID, item) for item in artifacts.skipped)

    if not violations:
        return DECISION_ALLOW, None, notes

    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        run_id = run_dir.name
    return DECISION_BLOCK, build_reason(run_id, final_status, violations), notes


def main() -> int:
    """항상 0 으로 끝난다. 차단은 stdout JSON 으로만 알린다."""
    try:
        payload = common.read_payload(sys.stdin)
        if payload is None:
            return 0
        decision, reason, notes = decide(payload, common.repo_root())
    except Exception as error:
        # 훅의 오류가 세션 종료를 막아서는 안 된다. 숨기지 않고 stderr 로 남긴 뒤
        # 통과시킨다. (`CLAUDE.md §8` - 조용히 무시하지 않는다)
        common.write_stderr(
            "[{0}] 검사를 건너뜁니다 (예상치 못한 오류 {1}: {2})".format(
                HOOK_ID, type(error).__name__, error
            )
        )
        return 0

    for note in notes:
        common.write_stderr(note)
    if decision == DECISION_BLOCK and reason:
        common.write_stdout_json({"decision": "block", "reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
