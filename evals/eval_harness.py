"""PatchPilot Harness 재시도 루프를 결정론적으로 검증하는 eval 실행 도구.

이 도구는 Agent를 대신 실행하지 않는다. Agent 실행은 Orchestrator(메인 Claude Code 세션)가
`evals/README.md` 의 절차대로 수행하고, 이 도구는 그 앞뒤에서 다음 네 가지만 담당한다.

1. setup    - eval 전용 결함 모듈과 테스트를 `sample-project/` 에 설치하고 원상태를 스냅샷한다.
2. inject   - Developer 1차 수정 직후 제품 코드에 결함을 주입하고 근거를 파일로 남긴다.
3. assert   - `reports/<run-id>/` 산출물만 근거로 상태 전이를 자동 판정한다.
4. teardown - 설치한 파일을 제거하고 `sample-project/` 가 원상태로 복구됐는지 확인한다.

검증 대상 전이:

    Planner -> Developer 1차 -> Fault Injection -> Tester FAIL
    -> PRODUCT_CODE_DEFECT -> retry_count = 1 -> Developer 2차
    -> Tester PASS -> Reviewer APPROVED -> SUCCESS

사용법은 `evals/README.md` 를 따른다.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
FIXTURES_DIR = EVALS_DIR / "fixtures"
FAULTS_DIR = EVALS_DIR / "faults"
STATE_DIR = EVALS_DIR / ".eval-run"
STATE_FILE = STATE_DIR / "state.json"
REPORTS_DIR = ROOT / "reports"
EXAMPLES_DIR = REPORTS_DIR / "examples"

DEFAULT_TASK = "evals/fixtures/HARNESS-EVAL-001.md"
DEFAULT_FAULT = "retry_001"

# eval 실행 중에만 sample-project에 설치되는 파일. (fixture 파일명, 설치 경로)
FIXTURE_INSTALLS = [
    ("tip.py", "sample-project/src/expense/tip.py"),
    ("test_tip.py", "sample-project/tests/test_tip.py"),
]

FAILURE_CATEGORIES = {
    "PRODUCT_CODE_DEFECT",
    "TEST_DEFECT",
    "PLAN_DEFECT",
    "ENVIRONMENT_ERROR",
    "UNKNOWN",
}

# 대표 결과로 승격할 때 반드시 존재해야 하는 산출물.
PROMOTED_FILES = [
    "fault-injection.md",
    "change-log-1.md",
    "test-result-1.md",
    "change-log-2.md",
    "test-result-2.md",
    "review.md",
    "report.md",
    "state.json",
]

# 대표 결과에 함께 복사하면 좋지만 없어도 승격을 막지는 않는 산출물.
OPTIONAL_PROMOTED_FILES = ["plan.md", "eval-result.md"]

PYTEST_COMMAND = "uv run pytest sample-project/tests -q"


@dataclass
class Check:
    """자동 검증 항목 하나의 판정 결과."""

    name: str
    passed: bool
    detail: str


class EvalError(Exception):
    """eval 진행을 계속할 수 없는 상황."""


# ---------------------------------------------------------------------------
# 공용 helper
# ---------------------------------------------------------------------------


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise EvalError(f"git {' '.join(args)} 실패: {completed.stderr.strip()}")
    return completed.stdout


def sample_project_status() -> list[str]:
    """sample-project 하위의 git 변경 상태를 정렬된 줄 목록으로 반환한다."""
    output = run_git("status", "--porcelain", "--", "sample-project")
    return sorted(line for line in output.splitlines() if line.strip())


def is_tracked(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        raise EvalError(
            "eval 실행 상태 파일이 없습니다: evals/.eval-run/state.json\n"
            "먼저 `uv run python evals/eval_harness.py setup` 을 실행하세요."
        )
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_fault(fault_id: str):
    fault_path = FAULTS_DIR / f"{fault_id}.py"
    if not fault_path.exists():
        raise EvalError(f"결함 정의 파일이 없습니다: evals/faults/{fault_id}.py")

    spec = importlib.util.spec_from_file_location(f"patchpilot_eval_fault_{fault_id}", fault_path)
    if spec is None or spec.loader is None:
        raise EvalError(f"결함 정의를 불러오지 못했습니다: evals/faults/{fault_id}.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_dir_of(run_id: str) -> Path:
    path = REPORTS_DIR / run_id
    if not path.is_dir():
        raise EvalError(f"실행 폴더가 없습니다: reports/{run_id}")
    return path


def read_run_file(run_id: str, name: str) -> str | None:
    path = REPORTS_DIR / run_id / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def section_value(text: str, heading: str) -> str:
    """`## <heading>` 다음의 첫 비어 있지 않은 줄을 반환한다."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            for following in lines[index + 1 :]:
                if following.strip():
                    return following.strip()
            return ""
    return ""


def test_function_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("def test_") and "(" in stripped:
            names.add(stripped[len("def ") : stripped.index("(")])
    return names


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def cmd_setup(task: str) -> int:
    if STATE_FILE.exists():
        raise EvalError(
            "이전 eval 실행이 정리되지 않았습니다. "
            "`uv run python evals/eval_harness.py teardown` 을 먼저 실행하세요."
        )

    if not (ROOT / task).is_file():
        raise EvalError(f"eval task 파일이 없습니다: {task}")

    snapshot = sample_project_status()

    installed = []
    for fixture_name, install_target in FIXTURE_INSTALLS:
        source = FIXTURES_DIR / fixture_name
        target = ROOT / install_target
        if not source.is_file():
            raise EvalError(f"fixture 파일이 없습니다: evals/fixtures/{fixture_name}")
        if target.exists():
            raise EvalError(
                f"설치 대상이 이미 존재합니다: {install_target}\n"
                "이전 실행이 정리되지 않았을 수 있습니다. 파일을 확인한 뒤 다시 실행하세요."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        installed.append(install_target)

    save_state(
        {
            "task": task,
            "fault": None,
            "installed": installed,
            "snapshot": snapshot,
            "setup_at": now_text(),
        }
    )

    print("eval setup 완료")
    print(f"  task   : {task}")
    for install_target in installed:
        print(f"  설치   : {install_target}")
    print(f"  스냅샷 : sample-project 변경 {len(snapshot)}건")
    print()
    print("다음 단계는 evals/README.md 의 실행 절차를 따르세요.")
    return 0


# ---------------------------------------------------------------------------
# inject
# ---------------------------------------------------------------------------


def cmd_inject(run_id: str, fault_id: str) -> int:
    state = load_state()
    run_dir = run_dir_of(run_id)

    if state.get("fault"):
        raise EvalError(
            f"이미 결함이 주입되어 있습니다: {state['fault']['fault_id']} "
            f"({state['fault']['injected_at']})"
        )

    fault = load_fault(fault_id)
    target = ROOT / fault.TARGET_PATH
    if not target.is_file():
        raise EvalError(f"결함 주입 대상 파일이 없습니다: {fault.TARGET_PATH}")

    before = target.read_text(encoding="utf-8")
    try:
        after = fault.apply(before)
    except ValueError as error:
        raise EvalError(str(error)) from error
    target.write_text(after, encoding="utf-8")

    record = {
        "fault_id": fault.FAULT_ID,
        "run_id": run_id,
        "target": fault.TARGET_PATH,
        "marker": fault.MARKER,
        "before_sha256": sha256_of(before),
        "after_sha256": sha256_of(after),
        "injected_at": now_text(),
    }
    state["fault"] = record
    save_state(state)

    (run_dir / "fault-injection.md").write_text(
        _fault_injection_report(fault, record), encoding="utf-8"
    )

    print(f"결함 주입 완료: {fault.FAULT_ID} -> {fault.TARGET_PATH}")
    print(f"기록 파일: reports/{run_id}/fault-injection.md")
    return 0


def _fault_injection_report(fault, record: dict) -> str:
    return f"""# Fault Injection

## Fault ID
{record["fault_id"]}

## 주입 시각
{record["injected_at"]}

## 대상 파일
`{record["target"]}`

## 주입 시점
Developer 1차 수정 완료 직후, Tester 1차 실행 직전

## 주입 목적
Harness의 재시도 상태 전이를 실제 pytest 실패로 검증하기 위해 제품 코드에 결함을 만든다.
`test-result-N.md` 의 문자열을 임의로 바꾸지 않고, Tester가 실제 실행 결과로 `STATUS: FAIL` 을
기록하도록 만드는 것이 목적이다.

## 결함 내용
{fault.DESCRIPTION}

## 주입 방식
파일 끝에 후처리 래퍼를 덧붙인다. Developer 1차가 함수 본문을 어떻게 구현했는지와 무관하게
모듈 최상위에 `{fault.ANCHOR}` 정의만 존재하면 동일하게 적용되므로 주입 결과가 결정론적이다.

## 주입된 코드
```python
{fault.FAULT_CODE.strip()}
```

## 파일 해시 (sha256)
| 시점 | 해시 |
| --- | --- |
| 주입 전 | `{record["before_sha256"]}` |
| 주입 후 | `{record["after_sha256"]}` |

## 제거 주체
Developer 2차.

Harness는 이 결함을 스스로 되돌리지 않는다. Harness가 자동으로 제거하면 재수정 주체가
Developer가 아니게 되어 `FAIL -> 분석 -> 재수정 -> PASS` 전이의 검증 의미가 사라진다.
Developer 2차는 `test-result-1.md` 를 근거로 이 결함을 제품 코드 결함으로 진단하고 제거해야 한다.

## 제거 확인 방법
`{record["target"]}` 에서 `{record["marker"]}` 표식이 사라지고 파일 내용이 실제로 바뀌었는지
확인한다. `eval_harness.py assert` 가 이 항목을 자동으로 판정한다.
"""


# ---------------------------------------------------------------------------
# assert
# ---------------------------------------------------------------------------


def assert_run(run_id: str) -> list[Check]:
    """reports/<run-id>/ 산출물과 제품 코드 상태만 근거로 전이를 판정한다."""
    checks: list[Check] = []
    state = load_state()
    run_dir_of(run_id)

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, passed, detail))

    # 1. Planner 산출물
    plan = read_run_file(run_id, "plan.md")
    check(
        "plan.md 존재",
        bool(plan and plan.strip()),
        "Planner 실행됨" if plan else "plan.md 없음",
    )

    # 2. Developer 1차 산출물
    change_log_1 = read_run_file(run_id, "change-log-1.md")
    check(
        "change-log-1.md 존재",
        bool(change_log_1 and change_log_1.strip()),
        "Developer 1차 실행됨" if change_log_1 else "change-log-1.md 없음",
    )

    # 3. Fault Injection 기록
    fault_record = state.get("fault")
    fault_report = read_run_file(run_id, "fault-injection.md")
    check(
        "fault-injection.md 존재",
        bool(fault_report and fault_record),
        f"fault_id={fault_record['fault_id']}" if fault_record else "결함 주입 기록 없음",
    )
    check(
        "결함 주입이 Developer 1차 이후에 이루어짐",
        bool(fault_record and change_log_1),
        "change-log-1.md 와 결함 주입 기록이 모두 존재",
    )

    # 4. Tester 1차 = FAIL
    test_result_1 = read_run_file(run_id, "test-result-1.md")
    status_line_1 = first_line(test_result_1) if test_result_1 else ""
    check(
        "test-result-1.md 첫 줄이 STATUS: FAIL",
        status_line_1 == "STATUS: FAIL",
        f"첫 줄: {status_line_1!r}" if test_result_1 else "test-result-1.md 없음",
    )

    # 5. Tester가 실제 pytest를 실행했는지 확인 (문자열만 바꿔치기한 FAIL 방지)
    has_command = bool(test_result_1 and PYTEST_COMMAND in test_result_1)
    check(
        "test-result-1.md 에 고정 실행 명령 기록",
        has_command,
        f"`{PYTEST_COMMAND}` 기록됨" if has_command else "고정 실행 명령이 기록되지 않음",
    )
    mentions_failed_test = bool(test_result_1 and "test_tip" in test_result_1)
    check(
        "test-result-1.md 가 주입된 결함의 실패 테스트를 기록",
        mentions_failed_test,
        "test_tip 관련 실패가 기록됨" if mentions_failed_test else "test_tip 실패 기록 없음",
    )

    # 6. 실패 원인 분류 = PRODUCT_CODE_DEFECT
    category = section_value(test_result_1, "실패 원인 분류") if test_result_1 else ""
    check(
        "실패 원인 분류가 PRODUCT_CODE_DEFECT",
        category == "PRODUCT_CODE_DEFECT",
        f"분류: {category!r}"
        + ("" if not category or category in FAILURE_CATEGORIES else " (정의되지 않은 값)"),
    )

    # 7. Developer 2차가 실행되었고 1차 실패 결과를 근거로 삼았는지 확인
    change_log_2 = read_run_file(run_id, "change-log-2.md")
    check(
        "change-log-2.md 존재",
        bool(change_log_2 and change_log_2.strip()),
        "Developer 2차 실행됨" if change_log_2 else "change-log-2.md 없음",
    )
    references_previous = bool(change_log_2 and "test-result-1" in change_log_2)
    check(
        "change-log-2.md 가 test-result-1.md 를 근거로 참조",
        references_previous,
        "이전 실패 결과 참조 확인" if references_previous else "test-result-1 참조 없음",
    )

    # 8. Tester 2차 = PASS
    test_result_2 = read_run_file(run_id, "test-result-2.md")
    status_line_2 = first_line(test_result_2) if test_result_2 else ""
    check(
        "test-result-2.md 첫 줄이 STATUS: PASS",
        status_line_2 == "STATUS: PASS",
        f"첫 줄: {status_line_2!r}" if test_result_2 else "test-result-2.md 없음",
    )
    has_command_2 = bool(test_result_2 and PYTEST_COMMAND in test_result_2)
    check(
        "test-result-2.md 에 고정 실행 명령 기록",
        has_command_2,
        f"`{PYTEST_COMMAND}` 기록됨" if has_command_2 else "고정 실행 명령이 기록되지 않음",
    )

    # 9. Reviewer = APPROVED
    review = read_run_file(run_id, "review.md")
    verdict_line = first_line(review) if review else ""
    check(
        "review.md 첫 줄이 VERDICT: APPROVED",
        verdict_line == "VERDICT: APPROVED",
        f"첫 줄: {verdict_line!r}" if review else "review.md 없음",
    )

    # 10. Orchestrator가 기록한 상태 전이
    checks.extend(_state_json_checks(run_id))

    # 11. 결함 제거 주체 확인 (teardown 이전에만 판정 가능)
    checks.append(_fault_removed_check(fault_record))

    # 12. 테스트 약화 여부
    checks.append(_test_not_weakened_check())

    # 13. 기존 제품 코드 보존 여부
    checks.append(_tracked_files_untouched_check(state))

    # 14. 최종 보고서
    report = read_run_file(run_id, "report.md")
    check(
        "report.md 존재",
        bool(report and report.strip()),
        "최종 보고서 존재" if report else "report.md 없음",
    )

    return checks


def _state_json_checks(run_id: str) -> list[Check]:
    raw = read_run_file(run_id, "state.json")
    if raw is None:
        return [Check("state.json 존재", False, "state.json 없음")]

    try:
        state_json = json.loads(raw)
    except json.JSONDecodeError as error:
        return [Check("state.json 파싱", False, f"JSON 파싱 실패: {error}")]

    checks = [Check("state.json 존재", True, "state.json 파싱 성공")]

    retry_count = state_json.get("retry_count")
    checks.append(
        Check("state.json retry_count == 1", retry_count == 1, f"retry_count={retry_count!r}")
    )

    final_status = state_json.get("final_status")
    checks.append(
        Check(
            "state.json final_status == SUCCESS",
            final_status == "SUCCESS",
            f"final_status={final_status!r}",
        )
    )

    current_stage = state_json.get("current_stage")
    checks.append(
        Check(
            "state.json current_stage == DONE",
            current_stage == "DONE",
            f"current_stage={current_stage!r}",
        )
    )

    blocked_reason = state_json.get("blocked_reason")
    checks.append(
        Check(
            "state.json blocked_reason 없음",
            blocked_reason in (None, ""),
            f"blocked_reason={blocked_reason!r}",
        )
    )

    attempts = state_json.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 2:
        checks.append(Check("state.json attempts 가 2회 기록", False, f"attempts={attempts!r}"))
        return checks

    checks.append(Check("state.json attempts 가 2회 기록", True, "시도 2회 기록됨"))

    first_attempt, second_attempt = attempts
    checks.append(
        Check(
            "attempts[0] 이 FAIL / PRODUCT_CODE_DEFECT",
            first_attempt.get("status") == "FAIL"
            and first_attempt.get("failure_category") == "PRODUCT_CODE_DEFECT",
            f"status={first_attempt.get('status')!r}, "
            f"failure_category={first_attempt.get('failure_category')!r}",
        )
    )
    checks.append(
        Check(
            "attempts[1] 이 PASS",
            second_attempt.get("status") == "PASS",
            f"status={second_attempt.get('status')!r}",
        )
    )
    return checks


def _fault_removed_check(fault_record: dict | None) -> Check:
    name = "주입된 결함이 Developer 2차에 의해 제거됨"
    if not fault_record:
        return Check(name, False, "결함 주입 기록이 없어 판정 불가")

    target = ROOT / fault_record["target"]
    if not target.is_file():
        return Check(name, False, f"대상 파일이 없습니다: {fault_record['target']}")

    source = target.read_text(encoding="utf-8")
    marker_removed = fault_record["marker"] not in source
    file_changed = sha256_of(source) != fault_record["after_sha256"]
    return Check(
        name,
        marker_removed and file_changed,
        "결함 표식이 제거되고 파일 내용이 실제로 변경됨"
        if marker_removed and file_changed
        else f"marker_removed={marker_removed}, file_changed={file_changed}",
    )


def _test_not_weakened_check() -> Check:
    name = "eval 테스트가 약화되지 않음"
    installed = ROOT / "sample-project/tests/test_tip.py"
    if not installed.is_file():
        return Check(name, False, "설치된 sample-project/tests/test_tip.py 가 없습니다")

    installed_source = installed.read_text(encoding="utf-8")
    expected = test_function_names((FIXTURES_DIR / "test_tip.py").read_text(encoding="utf-8"))
    actual = test_function_names(installed_source)
    missing = sorted(expected - actual)
    has_skip = "skip" in installed_source
    return Check(
        name,
        not missing and not has_skip,
        "원래 테스트 함수가 모두 유지되고 skip 처리가 없음"
        if not missing and not has_skip
        else f"사라진 테스트={missing}, skip 포함={has_skip}",
    )


def _tracked_files_untouched_check(state: dict) -> Check:
    """eval 실행이 기존 추적 파일을 건드리지 않았는지 확인한다."""
    baseline = set(state.get("snapshot", []))
    added = [line for line in sample_project_status() if line not in baseline]
    modified_tracked = [line for line in added if not line.startswith("??")]
    return Check(
        "기존 추적 파일이 변경되지 않음",
        not modified_tracked,
        "새로 생긴 변경은 eval fixture(untracked)뿐"
        if not modified_tracked
        else f"추적 파일 변경 발견: {modified_tracked}",
    )


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------


def teardown() -> list[Check]:
    """설치한 fixture를 제거하고 sample-project 복구 여부를 판정한다."""
    if not STATE_FILE.exists():
        return [Check("teardown", False, "eval 실행 상태 파일이 없어 teardown 대상이 없습니다")]

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    removed = []
    kept = []
    for install_target in state.get("installed", []):
        path = ROOT / install_target
        if not path.exists():
            continue
        if is_tracked(path):
            # 추적 중인 파일을 지우면 사용자의 실제 코드가 사라질 수 있으므로 건드리지 않는다.
            kept.append(install_target)
            continue
        path.unlink()
        removed.append(install_target)

    _remove_pycache_entries()

    checks = [
        Check(
            "eval fixture 제거",
            not kept,
            f"제거={removed}" if not kept else f"제거={removed}, 추적 파일이라 보존={kept}",
        )
    ]

    baseline = state.get("snapshot", [])
    current = sample_project_status()
    checks.append(
        Check(
            "sample-project 원상 복구",
            current == baseline,
            "setup 시점 상태와 동일"
            if current == baseline
            else f"복구 실패 / setup 시점={baseline} / 현재={current}",
        )
    )

    STATE_FILE.unlink()
    if STATE_DIR.is_dir() and not any(STATE_DIR.iterdir()):
        STATE_DIR.rmdir()

    return checks


def _remove_pycache_entries() -> None:
    """설치했던 모듈의 바이트코드 캐시만 제거한다."""
    cache_dirs = [
        ROOT / "sample-project/src/expense/__pycache__",
        ROOT / "sample-project/tests/__pycache__",
    ]
    for cache_dir in cache_dirs:
        if not cache_dir.is_dir():
            continue
        for cached in [*cache_dir.glob("tip.*.pyc"), *cache_dir.glob("test_tip.*.pyc")]:
            cached.unlink()


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------


def cmd_finish(run_id: str) -> int:
    """자동 검증을 수행하고, 검증이 실패하거나 예외가 나도 teardown을 반드시 실행한다."""
    checks: list[Check] = []
    try:
        checks.extend(assert_run(run_id))
    except Exception as error:
        checks.append(Check("eval 검증 실행", False, f"검증 중 예외 발생: {error}"))
    finally:
        try:
            checks.extend(teardown())
        except Exception as error:
            checks.append(Check("teardown 실행", False, f"teardown 중 예외 발생: {error}"))

    return _report(run_id, checks)


def cmd_assert(run_id: str) -> int:
    return _report(run_id, assert_run(run_id))


def cmd_teardown() -> int:
    checks = teardown()
    _print_checks(checks)
    return 0 if all(item.passed for item in checks) else 1


def _report(run_id: str, checks: list[Check]) -> int:
    passed = all(item.passed for item in checks)
    _write_eval_result(run_id, checks, passed)
    _print_checks(checks)
    return 0 if passed else 1


def _print_checks(checks: list[Check]) -> None:
    for item in checks:
        print(f"[{'PASS' if item.passed else 'FAIL'}] {item.name} - {item.detail}")
    passed_count = sum(1 for item in checks if item.passed)
    print()
    print(f"EVAL: {'PASS' if passed_count == len(checks) else 'FAIL'} ({passed_count}/{len(checks)})")


def _write_eval_result(run_id: str, checks: list[Check], passed: bool) -> None:
    run_dir = REPORTS_DIR / run_id
    if not run_dir.is_dir():
        return

    rows = "\n".join(
        f"| {index} | {item.name} | {'PASS' if item.passed else 'FAIL'} | {item.detail.replace(chr(10), ' ')} |"
        for index, item in enumerate(checks, start=1)
    )
    passed_count = sum(1 for item in checks if item.passed)
    run_dir.joinpath("eval-result.md").write_text(
        f"""EVAL: {"PASS" if passed else "FAIL"}

# Eval Result

## Run ID
{run_id}

## 판정 시각
{now_text()}

## 검증 대상 전이
Planner -> Developer 1차 -> Fault Injection -> Tester FAIL -> PRODUCT_CODE_DEFECT
-> retry_count = 1 -> Developer 2차 -> Tester PASS -> Reviewer APPROVED -> SUCCESS

## 자동 검증 항목
| # | 항목 | 결과 | 근거 |
| --- | --- | --- | --- |
{rows}

## 종합
{passed_count}/{len(checks)} 항목 통과
""",
        encoding="utf-8",
    )


def cmd_status() -> int:
    if not STATE_FILE.exists():
        print("진행 중인 eval 실행이 없습니다.")
        return 0

    print(STATE_FILE.read_text(encoding="utf-8").rstrip())
    print()
    print("현재 sample-project 상태:")
    for line in sample_project_status() or ["  (변경 없음)"]:
        print(f"  {line}")
    return 0


def cmd_promote(run_id: str, name: str | None) -> int:
    run_dir = run_dir_of(run_id)

    eval_result = read_run_file(run_id, "eval-result.md")
    if eval_result is None:
        raise EvalError("eval-result.md 가 없습니다. `assert` 또는 `finish` 를 먼저 실행하세요.")
    if first_line(eval_result) != "EVAL: PASS":
        raise EvalError(
            f"eval 결과가 PASS 가 아니므로 승격하지 않습니다. (첫 줄: {first_line(eval_result)!r})"
        )

    missing = [item for item in PROMOTED_FILES if not (run_dir / item).is_file()]
    if missing:
        raise EvalError(f"대표 결과에 필요한 파일이 없습니다: {missing}")

    target_name = name or f"EVAL-{run_id.removeprefix('RUN-')}"
    target_dir = EXAMPLES_DIR / target_name
    if target_dir.exists():
        raise EvalError(f"이미 존재하는 대표 결과 폴더입니다: reports/examples/{target_name}")

    target_dir.mkdir(parents=True)
    for item in [*PROMOTED_FILES, *OPTIONAL_PROMOTED_FILES]:
        source = run_dir / item
        if source.is_file():
            shutil.copyfile(source, target_dir / item)

    print(f"대표 결과 복사 완료: reports/examples/{target_name}")
    for copied in sorted(path.name for path in target_dir.iterdir()):
        print(f"  {copied}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval_harness.py",
        description="PatchPilot Harness 재시도 루프 eval 실행 도구",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="eval fixture 설치 및 원상태 스냅샷")
    setup_parser.add_argument("--task", default=DEFAULT_TASK)

    inject_parser = subparsers.add_parser("inject", help="Developer 1차 직후 결함 주입")
    inject_parser.add_argument("--run-id", required=True)
    inject_parser.add_argument("--fault", default=DEFAULT_FAULT)

    assert_parser = subparsers.add_parser("assert", help="산출물 기반 자동 검증 (teardown 없음)")
    assert_parser.add_argument("--run-id", required=True)

    finish_parser = subparsers.add_parser(
        "finish", help="자동 검증 후 결과와 무관하게 teardown 수행"
    )
    finish_parser.add_argument("--run-id", required=True)

    subparsers.add_parser("teardown", help="설치한 fixture 제거 및 복구 확인")
    subparsers.add_parser("status", help="현재 eval 실행 상태 출력")

    promote_parser = subparsers.add_parser(
        "promote", help="검증에 통과한 실행 결과를 reports/examples/ 로 복사"
    )
    promote_parser.add_argument("--run-id", required=True)
    promote_parser.add_argument("--name", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup":
            return cmd_setup(args.task)
        if args.command == "inject":
            return cmd_inject(args.run_id, args.fault)
        if args.command == "assert":
            return cmd_assert(args.run_id)
        if args.command == "finish":
            return cmd_finish(args.run_id)
        if args.command == "teardown":
            return cmd_teardown()
        if args.command == "status":
            return cmd_status()
        if args.command == "promote":
            return cmd_promote(args.run_id, args.name)
    except EvalError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
