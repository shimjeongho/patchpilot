"""Hook 테스트 공용 픽스처.

`.claude/hooks/` 는 패키지가 아니라 단독 스크립트 디렉터리이므로 파일 경로로 로드한다.
`_guard_common` 은 실제 모듈 이름 그대로 등록해서, 가드가 `import _guard_common` 할 때
같은 인스턴스를 재사용하게 한다.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / ".claude" / "hooks"

# 실측 payload 에서 그대로 가져온 값. 테스트가 가짜 스키마로 통과하지 않도록
# Phase 0 관측 결과와 같은 키 구성을 유지한다.
_BASE_PAYLOAD = {
    "session_id": "b336373c-f496-4e0e-aeb2-ddee0ce6531d",
    "prompt_id": "d039d9ca-e22e-4489-8f99-5b242bb2e0de",
    "hook_event_name": "PreToolUse",
    "permission_mode": "auto",
    "tool_use_id": "toolu_01HRcD5hYqn7yBPzgesJqomZ",
    "cwd": "C:\\Users\\user\\dev\\patchpilot",
    "transcript_path": "C:\\Users\\user\\.claude\\projects\\x.jsonl",
    "effort": {"level": "high"},
}

UNSET = object()


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def hooks_dir() -> Path:
    return HOOKS_DIR


@pytest.fixture(scope="session")
def guard_common():
    return _load("_guard_common", HOOKS_DIR / "_guard_common.py")


@pytest.fixture(scope="session")
def guard_test_files(guard_common):
    return _load("guard_test_files", HOOKS_DIR / "guard_test_files.py")


@pytest.fixture(scope="session")
def guard_plan_scope(guard_common):
    return _load("guard_plan_scope", HOOKS_DIR / "guard_plan_scope.py")


@pytest.fixture(scope="session")
def guard_bash_scope(guard_common):
    return _load("guard_bash_scope", HOOKS_DIR / "guard_bash_scope.py")


@pytest.fixture(scope="session")
def eval_harness():
    return _load("patchpilot_eval_harness", ROOT / "evals" / "eval_harness.py")


@pytest.fixture(autouse=True)
def clean_disable_switch(monkeypatch):
    """비활성 스위치가 다른 테스트로 새지 않게 매 테스트마다 지운다."""
    monkeypatch.delenv("PATCHPILOT_DISABLED_HOOKS", raising=False)


@pytest.fixture
def make_payload():
    """실측 구조와 같은 PreToolUse payload 를 만든다.

    `agent_type` 을 넘기지 않으면 키 자체를 넣지 않는다. 메인 세션 payload 에는
    `agent_type` 과 `agent_id` 가 아예 없다는 Phase 0 실측을 그대로 반영한 것이다.
    """

    def build(
        tool_name: str = "Write",
        file_path=None,
        agent_type=UNSET,
        agent_id: str = "a985f0597c0555546",
        tool_input=UNSET,
    ) -> dict:
        payload = dict(_BASE_PAYLOAD)
        payload["tool_name"] = tool_name

        if agent_type is not UNSET:
            payload["agent_type"] = agent_type
            payload["agent_id"] = agent_id

        if tool_input is not UNSET:
            if tool_input is not None:
                payload["tool_input"] = tool_input
        elif tool_name == "Bash":
            payload["tool_input"] = {"command": "echo hi", "description": "probe"}
        elif tool_name == "Edit":
            payload["tool_input"] = {
                "file_path": str(file_path),
                "old_string": "before",
                "new_string": "after",
                "replace_all": False,
            }
        else:
            payload["tool_input"] = {"file_path": str(file_path), "content": "x"}

        return payload

    return build


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """실제 저장소를 건드리지 않기 위한 가짜 저장소 루트."""
    (tmp_path / "sample-project" / "src" / "expense").mkdir(parents=True)
    (tmp_path / "sample-project" / "tests").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    return tmp_path


def _plan_text(allowed: tuple[str, ...]) -> str:
    """`CLAUDE.md §13` 형태의 plan.md. 6절 산문·목록은 파서가 읽으면 안 되는 잡음이다."""
    lines = [
        "# Plan: 관측용 계획",
        "",
        "## 6. 실제 코드에서 확인한 근거",
        "- `sample-project/src/expense/decoy.py:42` - 근거일 뿐 허용 대상이 아니다",
        "",
        "## 7. 수정 허용 파일 목록",
    ]
    lines.extend("- `" + entry + "`" for entry in allowed)
    lines.extend(
        [
            "",
            "이 외의 파일은 수정하지 않는다. `sample-project/src/expense/prose_only.py`",
            "",
            "## 8. 구현 단계",
            "1. 아무 것도 하지 않는다",
        ]
    )
    return "\n".join(lines) + "\n"


@pytest.fixture
def make_run(fake_root: Path):
    """가짜 저장소 안에 run 디렉터리를 만든다."""

    def build(
        name: str = "RUN-20260824-1600-BUG-001",
        status: str = "RUNNING",
        allowed: tuple[str, ...] = ("sample-project/src/expense/service_charge.py",),
        write_plan: bool = True,
        state_text=None,
        plan_text=None,
    ) -> Path:
        run_dir = fake_root / "reports" / name
        run_dir.mkdir(parents=True)

        if state_text is None:
            state_text = (
                '{"run_id": "' + name + '", "status": "' + status + '", '
                '"current_stage": "DEVELOPING", "retry_count": 0, "retry_budget": 3}'
            )
        (run_dir / "state.json").write_text(state_text, encoding="utf-8")

        if write_plan:
            body = _plan_text(allowed) if plan_text is None else plan_text
            (run_dir / "plan.md").write_text(body, encoding="utf-8")

        return run_dir

    return build
