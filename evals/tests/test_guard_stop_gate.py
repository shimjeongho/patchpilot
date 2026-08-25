"""`guard_stop_gate.py` 판정 검증.

검사 대상은 두 층이다.

1. `decide()` 의 순수 판정 — G1~G19 각각의 정상/위반 경계와 fail-open 조건.
2. `main()` 의 전달 계약 — 차단은 stdout JSON + exit 0 으로만 알리고,
   통과는 stdout 에 아무것도 쓰지 않는다.

payload 구조는 Claude Code 2.1.241 Stop 훅 실측 결과를 그대로 쓴다. 가짜 스키마로
통과하지 않게 하기 위해서다.
"""

import io
import json
import sys

import pytest

SESSION = "adb7baf0-fe0c-4831-9506-ce2f739dec8d"
OTHER_SESSION = "5d00e56a-b552-4380-90e0-76633a8fd611"
RUN_ID = "RUN-20260825-1500-BUG-001"

# 실측 payload 에서 그대로 가져온 값. `transcript_path` / `cwd` /
# `last_assistant_message` 는 reason 정보 누출 검사에도 쓰인다.
TRANSCRIPT_PATH = r"C:\Users\user\.claude\projects\C--Users-user-dev-patchpilot\x.jsonl"
CWD = r"C:\Users\user\dev\patchpilot"
LAST_MESSAGE = "PatchPilot 실행을 마쳤습니다. 최종 상태는 SUCCESS 입니다."


def stop_payload(session_id=SESSION, stop_hook_active=False, event="Stop", drop=()):
    """실측 구조와 같은 Stop payload 를 만든다."""
    payload = {
        "session_id": session_id,
        "transcript_path": TRANSCRIPT_PATH,
        "cwd": CWD,
        "prompt_id": "504af973-5331-498d-ba29-729cca947902",
        "permission_mode": "default",
        "effort": {"level": "high"},
        "hook_event_name": event,
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": LAST_MESSAGE,
        "background_tasks": [],
        "session_crons": [],
    }
    for key in drop:
        payload.pop(key, None)
    return payload


def success_state(**overrides):
    """`patchpilot.md §10` 마감 계약을 모두 만족하는 SUCCESS 상태."""
    state = {
        "run_id": RUN_ID,
        "task": "tasks/BUG-001.md",
        "session_id": SESSION,
        "status": "SUCCESS",
        "current_stage": "DONE",
        "retry_count": 1,
        "retry_budget": 3,
        "unknown_retry_used": False,
        "started_at": "20260825-1500",
        "finished_at": "20260825-1520",
        "start_commit": "a1e7604e343050f84d3fb2394d1b01e2bf13035c",
        "start_dirty_files": [],
        "attempts": [
            {
                "n": 1,
                "change_log": "change-log-1.md",
                "test_result": "test-result-1.md",
                "status": "FAIL",
                "failure_category": "PRODUCT_CODE_DEFECT",
            },
            {
                "n": 2,
                "change_log": "change-log-2.md",
                "test_result": "test-result-2.md",
                "status": "PASS",
                "failure_category": None,
            },
        ],
        "review": {"verdict": "APPROVED", "file": "review.md"},
        "final_status": "SUCCESS",
        "blocked_reason": None,
    }
    state.update(overrides)
    return state


def blocked_state(**overrides):
    """예산 소진으로 끝난 BLOCKED 상태. `reports/examples/EVAL-004` 형태를 따른다."""
    state = {
        "run_id": RUN_ID,
        "task": "tasks/BUG-001.md",
        "session_id": SESSION,
        "status": "BLOCKED",
        "current_stage": "DONE",
        "retry_count": 3,
        "retry_budget": 3,
        "unknown_retry_used": False,
        "started_at": "20260825-1500",
        "finished_at": "20260825-1530",
        "start_commit": "a1e7604e343050f84d3fb2394d1b01e2bf13035c",
        "start_dirty_files": [],
        "attempts": [
            {
                "n": index,
                "change_log": "change-log-{0}.md".format(index),
                "test_result": "test-result-{0}.md".format(index),
                "status": "FAIL",
                "failure_category": "PRODUCT_CODE_DEFECT",
            }
            for index in (1, 2, 3)
        ],
        "review": {"verdict": None, "file": None},
        "final_status": "BLOCKED",
        "blocked_reason": "RETRY_BUDGET_EXCEEDED",
    }
    state.update(overrides)
    return state


def success_files():
    return {
        "plan.md": "# Plan\n\n## 7. 수정 허용 파일 목록\n- `sample-project/src/expense/tip.py`\n",
        "report.md": "# PatchPilot Report\n\n## 3. 최종 상태\nSUCCESS\n",
        "review.md": "VERDICT: APPROVED\n\n승인한다.\n",
        "change-log-1.md": "# change log 1\n",
        "change-log-2.md": "# change log 2\n",
        "test-result-1.md": "STATUS: FAIL\n",
        "test-result-2.md": "STATUS: PASS\n",
    }


def blocked_files():
    files = {
        "plan.md": "# Plan\n\n## 7. 수정 허용 파일 목록\n- `sample-project/src/expense/tip.py`\n",
        "report.md": "# PatchPilot Report\n\n## 3. 최종 상태\nBLOCKED\n",
    }
    for index in (1, 2, 3):
        files["change-log-{0}.md".format(index)] = "# change log {0}\n".format(index)
        files["test-result-{0}.md".format(index)] = "STATUS: FAIL\n"
    return files


def write_run(root, state, files, name=RUN_ID, state_text=None):
    """가짜 저장소 안에 마감된 run 디렉터리를 만든다."""
    run_dir = root / "reports" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(state, ensure_ascii=False, indent=2) if state_text is None else state_text
    (run_dir / "state.json").write_text(body, encoding="utf-8")
    for file_name, content in files.items():
        (run_dir / file_name).write_text(content, encoding="utf-8")
    return run_dir


def gids(reason):
    """reason 에 나열된 위반 ID 집합."""
    if reason is None:
        return set()
    found = set()
    for line in reason.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [") and "]" in stripped:
            found.add(stripped[3 : stripped.index("]")])
    return found


@pytest.fixture
def judge(guard_stop_gate, fake_root):
    """가짜 저장소를 기준으로 `decide()` 를 호출한다."""

    def call(payload=None):
        return guard_stop_gate.decide(payload or stop_payload(), fake_root)

    return call


# ---------------------------------------------------------------------------
# 정상 종료는 막지 않는다
# ---------------------------------------------------------------------------


def test_consistent_success_run_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(), success_files())
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert notes == []


def test_consistent_blocked_run_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, blocked_state(), blocked_files())
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert notes == []


# ---------------------------------------------------------------------------
# G1~G6 공통 마감 계약
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gid, overrides, removed",
    [
        ("G1", {"status": "BLOCKED"}, None),
        ("G2", {"current_stage": "REPORTING"}, None),
        ("G3", {"finished_at": None}, None),
        ("G3", {"finished_at": "   "}, None),
        ("G4", {}, "report.md"),
        ("G5", {}, "change-log-1.md"),
        ("G5", {}, "test-result-1.md"),
        ("G6", {"retry_count": 4, "retry_budget": 3}, None),
        ("G6", {"retry_count": -1}, None),
    ],
)
def test_common_contract_violation_blocks(guard_stop_gate, fake_root, judge, gid, overrides, removed):
    files = success_files()
    if removed is not None:
        files.pop(removed)
    write_run(fake_root, success_state(**overrides), files)
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert gid in gids(reason)


def test_retry_counters_that_are_not_integers_skip_g6(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(retry_count="1"), success_files())
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert any("G6" in note for note in notes)


def test_attempt_file_name_with_path_segment_is_not_judged(guard_stop_gate, fake_root, judge):
    state = success_state()
    state["attempts"][0]["change_log"] = "../outside.md"
    write_run(fake_root, state, success_files())
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


# ---------------------------------------------------------------------------
# G7~G13 SUCCESS 계약
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gid, overrides, removed, rewritten",
    [
        ("G7", {"blocked_reason": "ENVIRONMENT_ERROR"}, None, None),
        ("G8", {}, "plan.md", None),
        ("G9", {}, "review.md", None),
        ("G10", {}, None, ("review.md", "VERDICT: CHANGES_REQUESTED\n")),
        ("G10", {}, None, ("review.md", "리뷰 결과\n\nVERDICT: APPROVED\n")),
        ("G11", {"review": {"verdict": None, "file": None}}, None, None),
        ("G12", {"attempts": []}, None, None),
        ("G12", {}, "test-result-2.md", None),
        ("G12", {}, None, ("test-result-2.md", "STATUS: FAIL\n")),
        ("G13", {}, None, None),
    ],
)
def test_success_contract_violation_blocks(
    guard_stop_gate, fake_root, judge, gid, overrides, removed, rewritten
):
    state = success_state(**overrides)
    if gid == "G13":
        state["attempts"][-1]["status"] = "FAIL"
    files = success_files()
    if removed is not None:
        files.pop(removed)
    if rewritten is not None:
        files[rewritten[0]] = rewritten[1]
    write_run(fake_root, state, files)
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert gid in gids(reason)


# ---------------------------------------------------------------------------
# G14~G19 BLOCKED 계약
# ---------------------------------------------------------------------------


def test_unknown_blocked_reason_blocks(guard_stop_gate, fake_root, judge):
    write_run(fake_root, blocked_state(blocked_reason="TOTALLY_MADE_UP"), blocked_files())
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G14" in gids(reason)


def test_null_blocked_reason_blocks(guard_stop_gate, fake_root, judge):
    write_run(fake_root, blocked_state(blocked_reason=None), blocked_files())
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G14" in gids(reason)


def test_retry_budget_exceeded_without_exhausted_budget_blocks(guard_stop_gate, fake_root, judge):
    write_run(fake_root, blocked_state(retry_count=1), blocked_files())
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G15" in gids(reason)


def test_changes_requested_no_budget_without_review_file_blocks(guard_stop_gate, fake_root, judge):
    state = blocked_state(blocked_reason="REVIEW_CHANGES_REQUESTED_NO_BUDGET")
    write_run(fake_root, state, blocked_files())
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G16" in gids(reason)


def test_changes_requested_no_budget_with_wrong_first_line_blocks(guard_stop_gate, fake_root, judge):
    state = blocked_state(
        blocked_reason="REVIEW_CHANGES_REQUESTED_NO_BUDGET",
        review={"verdict": "CHANGES_REQUESTED", "file": "review.md"},
    )
    files = blocked_files()
    files["review.md"] = "VERDICT: APPROVED\n"
    write_run(fake_root, state, files)
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G16" in gids(reason)


def test_changes_requested_no_budget_consistent_is_allowed(guard_stop_gate, fake_root, judge):
    state = blocked_state(
        blocked_reason="REVIEW_CHANGES_REQUESTED_NO_BUDGET",
        review={"verdict": "CHANGES_REQUESTED", "file": "review.md"},
    )
    files = blocked_files()
    files["review.md"] = "VERDICT: CHANGES_REQUESTED\n\n지적사항\n"
    write_run(fake_root, state, files)
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_reviewer_invalid_verdict_with_machine_readable_line_blocks(guard_stop_gate, fake_root, judge):
    state = blocked_state(blocked_reason="REVIEWER_INVALID_VERDICT")
    files = blocked_files()
    files["review.md"] = "VERDICT: CHANGES_REQUESTED\n"
    write_run(fake_root, state, files)
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G17" in gids(reason)


def test_reviewer_invalid_verdict_with_broken_line_is_allowed(guard_stop_gate, fake_root, judge):
    state = blocked_state(blocked_reason="REVIEWER_INVALID_VERDICT")
    files = blocked_files()
    files["review.md"] = "검토 의견을 남깁니다\n"
    write_run(fake_root, state, files)
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_planner_no_output_with_existing_plan_blocks(guard_stop_gate, fake_root, judge):
    write_run(fake_root, blocked_state(blocked_reason="PLANNER_NO_OUTPUT"), blocked_files())
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G18" in gids(reason)


def test_planner_no_output_without_plan_is_allowed(guard_stop_gate, fake_root, judge):
    files = blocked_files()
    files.pop("plan.md")
    state = blocked_state(
        blocked_reason="PLANNER_NO_OUTPUT",
        retry_count=0,
        attempts=[],
    )
    write_run(fake_root, state, files)
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_blocked_run_with_approved_review_blocks(guard_stop_gate, fake_root, judge):
    state = blocked_state(review={"verdict": "APPROVED", "file": "review.md"})
    files = blocked_files()
    files["review.md"] = "VERDICT: APPROVED\n"
    write_run(fake_root, state, files)
    decision, reason, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    assert "G19" in gids(reason)


# ---------------------------------------------------------------------------
# Run 귀속
# ---------------------------------------------------------------------------


def test_no_matching_run_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(session_id=OTHER_SESSION), {})
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert notes == []


def test_run_without_session_id_is_not_judged(guard_stop_gate, fake_root, judge):
    state = success_state()
    del state["session_id"]
    write_run(fake_root, state, {})
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_two_matching_runs_are_allowed_with_warning(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(), {}, name="RUN-20260825-1500-BUG-001")
    write_run(fake_root, success_state(run_id="RUN-20260825-1600-BUG-002"), {},
              name="RUN-20260825-1600-BUG-002")
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert any("2개" in note for note in notes)


def test_preserved_examples_are_never_scanned(guard_stop_gate, fake_root, judge):
    """`reports/examples/EVAL-*` 는 glob 대상이 아니다."""
    example = fake_root / "reports" / "examples" / "EVAL-20260820-1318-HARNESS-EVAL-001"
    example.mkdir(parents=True)
    (example / "state.json").write_text(
        json.dumps(success_state(current_stage="REPORTING")), encoding="utf-8"
    )
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_directory_not_named_run_is_not_scanned(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(current_stage="REPORTING"), {},
              name="EVAL-20260825-1500-BUG-001")
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_unparsable_state_json_is_allowed_with_warning(guard_stop_gate, fake_root, judge):
    write_run(fake_root, {}, {}, state_text="{ not json ")
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert any("state.json" in note for note in notes)


def test_missing_reports_directory_is_allowed(guard_stop_gate, fake_root, judge):
    (fake_root / "reports").rmdir()
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert notes == []


# ---------------------------------------------------------------------------
# fail-open
# ---------------------------------------------------------------------------


def test_reentry_call_is_always_allowed(guard_stop_gate, fake_root, judge):
    """`stop_hook_active` 재진입 호출은 무조건 통과. 무한 루프 방지의 핵심이다."""
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, reason, _ = judge(stop_payload(stop_hook_active=True))
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None


def test_truthy_non_boolean_stop_hook_active_is_treated_as_reentry(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, _, _ = judge(stop_payload(stop_hook_active="true"))
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_other_hook_event_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, _, _ = judge(stop_payload(event="PreToolUse"))
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_missing_session_id_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, _, _ = judge(stop_payload(drop=("session_id",)))
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_non_string_session_id_is_allowed(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, _, _ = judge(stop_payload(session_id=42))
    assert decision == guard_stop_gate.DECISION_ALLOW


def test_running_run_is_allowed(guard_stop_gate, fake_root, judge):
    """`final_status` 가 아직 null 이면 일반 turn 종료를 막지 않는다."""
    state = success_state(status="RUNNING", current_stage="TESTING", final_status=None,
                          finished_at=None)
    write_run(fake_root, state, {})
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert notes == []


def test_unknown_final_status_is_allowed_with_warning(guard_stop_gate, fake_root, judge):
    write_run(fake_root, success_state(final_status="PARTIAL"), success_files())
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert any("final_status" in note for note in notes)


def test_unreadable_artifact_skips_only_its_own_check(guard_stop_gate, fake_root, judge):
    """읽지 못한 파일을 "없음" 으로 취급하지 않는다. 다른 확실한 위반은 계속 잡는다."""
    files = success_files()
    files.pop("report.md")
    run_dir = write_run(fake_root, success_state(), files)
    (run_dir / "review.md").write_bytes(b"\xff\xfe\x00\x01 broken")
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK
    found = gids(reason)
    assert "G4" in found
    assert "G9" not in found and "G10" not in found
    assert any("review.md" in note for note in notes)


@pytest.mark.parametrize("switch", ["guard-stop-gate", "all", " GUARD-STOP-GATE , other "])
def test_disable_switch_allows(guard_stop_gate, fake_root, judge, monkeypatch, switch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", switch)
    write_run(fake_root, success_state(current_stage="REPORTING"), {})
    decision, reason, notes = judge()
    assert decision == guard_stop_gate.DECISION_ALLOW
    assert reason is None
    assert any("비활성화됨" in note for note in notes)


def test_unrelated_disable_switch_still_judges(guard_stop_gate, fake_root, judge, monkeypatch):
    monkeypatch.setenv("PATCHPILOT_DISABLED_HOOKS", "guard-bash-scope")
    write_run(fake_root, success_state(current_stage="REPORTING"), success_files())
    decision, _, _ = judge()
    assert decision == guard_stop_gate.DECISION_BLOCK


# ---------------------------------------------------------------------------
# reason 계약
# ---------------------------------------------------------------------------


def test_reason_contains_required_sections(guard_stop_gate, fake_root, judge):
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    _, reason, _ = judge()
    assert reason.startswith("[guard-stop-gate] 종료 상태 불일치")
    assert "Run:" in reason and RUN_ID in reason
    assert "Final status:" in reason and "SUCCESS" in reason
    assert "확인된 위반:" in reason
    assert "기대:" in reason and "실제:" in reason and "근거:" in reason
    assert "reports/{0}/review.md".format(RUN_ID) in reason
    assert "다음 행동:" in reason


def test_reason_states_the_single_block_limit(guard_stop_gate, fake_root, judge):
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    _, reason, _ = judge()
    assert "한 user prompt 안에서 한 번만 차단한다" in reason
    assert "stop_hook_active 재진입 호출" in reason


def test_reason_lists_every_violation(guard_stop_gate, fake_root, judge):
    """첫 위반에서 멈추지 않는다. 재차단 기회가 없으므로 한 번에 모두 전달해야 한다."""
    files = success_files()
    files.pop("review.md")
    files.pop("report.md")
    state = success_state(current_stage="REPORTING", finished_at=None)
    write_run(fake_root, state, files)
    _, reason, _ = judge()
    assert {"G2", "G3", "G4", "G9"} <= gids(reason)


def test_reason_does_not_leak_payload_fields(guard_stop_gate, fake_root, judge):
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    _, reason, _ = judge()
    assert TRANSCRIPT_PATH not in reason
    assert CWD not in reason
    assert LAST_MESSAGE not in reason
    assert "transcript_path" not in reason
    assert "last_assistant_message" not in reason


def test_reason_does_not_decide_the_final_status(guard_stop_gate, fake_root, judge):
    """Gate 는 모순만 보고한다. SUCCESS / BLOCKED 결론을 대신 내리지 않는다."""
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    _, reason, _ = judge()
    assert "SUCCESS 로 바꿔라" not in reason
    assert "BLOCKED 로 바꿔라" not in reason
    assert "다시 판정한다" in reason


# ---------------------------------------------------------------------------
# main() 전달 계약
# ---------------------------------------------------------------------------


class _FakeStream:
    """`.buffer` 를 가진 최소 스트림. UTF-8 바이트 출력을 그대로 확인한다."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text):
        self.buffer.write(text.encode("utf-8"))

    def flush(self):
        pass

    def value(self) -> bytes:
        return self.buffer.getvalue()


@pytest.fixture
def run_main(guard_stop_gate, guard_common, fake_root, monkeypatch):
    """`main()` 을 가짜 저장소·가짜 스트림으로 실행하고 (종료 코드, stdout, stderr) 를 준다."""

    def call(payload=None):
        stdout, stderr = _FakeStream(), _FakeStream()
        monkeypatch.setattr(guard_common, "repo_root", lambda: fake_root)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload or stop_payload())))
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        code = guard_stop_gate.main()
        return code, stdout.value(), stderr.value()

    return call


def test_main_writes_nothing_to_stdout_when_allowing(fake_root, run_main):
    write_run(fake_root, success_state(), success_files())
    code, out, _ = run_main()
    assert code == 0
    assert out == b""


def test_main_emits_block_json_and_exits_zero(fake_root, run_main):
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    code, out, _ = run_main()
    assert code == 0
    document = json.loads(out.decode("utf-8"))
    assert set(document) == {"decision", "reason"}
    assert document["decision"] == "block"
    assert "G9" in gids(document["reason"])


def test_main_keeps_korean_reason_intact_as_utf8(fake_root, run_main):
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    _, out, _ = run_main()
    assert "종료 상태 불일치".encode("utf-8") in out
    assert json.loads(out.decode("utf-8"))["reason"].startswith(
        "[guard-stop-gate] 종료 상태 불일치"
    )


def test_main_survives_unexpected_errors(guard_stop_gate, fake_root, run_main, monkeypatch):
    def boom(payload, root):
        raise RuntimeError("판정 중 예상치 못한 오류")

    monkeypatch.setattr(guard_stop_gate, "decide", boom)
    files = success_files()
    files.pop("review.md")
    write_run(fake_root, success_state(), files)
    code, out, err = run_main()
    assert code == 0
    assert out == b""
    assert b"guard-stop-gate" in err


def test_main_allows_on_empty_stdin(guard_stop_gate, guard_common, fake_root, monkeypatch):
    stdout, stderr = _FakeStream(), _FakeStream()
    monkeypatch.setattr(guard_common, "repo_root", lambda: fake_root)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    assert guard_stop_gate.main() == 0
    assert stdout.value() == b""
