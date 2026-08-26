"""PatchPilot Harness Audit — 저장소의 통제 계약을 결정론적으로 채점하는 엔진.

Audit 이 답하는 질문은 하나다.

    "저장소가 지금 이 상태로, PatchPilot 이 선언한 통제 계약을 실제로 갖추고 있고
     그 선언이 서로 모순되지 않는가."

평가 대상은 `sample-project/` 가 아니라 Harness(`CLAUDE.md`, `.claude/`, `evals/`,
`reports/examples/`) 다. 애플리케이션 코드 품질은 검사 대상이 아니다.

세 검증 층의 분업은 다음과 같다.

* `PreToolUse` / `Stop` Hook — Agent 의 **실시간 행위**
* `evals/eval_harness.py`   — Harness 의 **실행 결과 상태 전이**
* 이 파일                    — 저장소의 **정지 상태 구조 계약**

핵심 설계 원칙

1. 점수는 "느낌" 이 아니다. 모든 check 는 저장소 파일에서 기계적으로 증명 가능한
   사실 하나에 대응한다. LLM 판단·네트워크·시각·난수를 쓰지 않는다.
2. 모든 check 는 **이진** 이다. PASS 면 만점, FAIL 이면 0점. 부분 점수를 두는 순간
   원칙 1이 무너진다. `eval_harness.Check` 와 같은 규율이다.
3. 상수를 **재선언하지 않는다.** `AGENT_TYPES` / `BLOCKED_REASONS` /
   `FAILURE_CATEGORIES` / `PYTEST_COMMAND` / Stop Gate 의 `check_run()` 은 전부
   실제 구현에서 import 한다. Audit 이 세 번째 정본이 되면 그 자체가 드리프트다.
4. 산문을 해석하지 않는다. 코드펜스·Markdown 표·고정 heading 아래 checklist·
   Python/TS 상수처럼 **고정 앵커** 만 파싱한다. fuzzy matching 을 하지 않는다.

## 판단 불가 시의 기본값 — Guard 와 정반대다

`_guard_common.py` 는 "판단할 수 없으면 통과시킨다" 를 명시한다. Audit 은 반대로
**판단할 수 없으면 FAIL** 이다.

|          | Guard                          | Audit                     |
| -------- | ------------------------------ | ------------------------- |
| 실행 위치 | 실시간 도구 호출 경로            | 오프라인                   |
| 오탐 비용 | 정상 실행이 죽는다               | 없다                      |
| 미탐 비용 | 위반 1회 누락 (뒤에서 재포착)     | **감사 도구 자체의 신뢰 상실** |

단, 두 가지를 구분한다.

* 기대한 파일이 **없다** → 그 check 만 FAIL. 근거를 evidence 에 남긴다.
* 파일이 있는데 **읽거나 파싱할 수 없다** → `AuditError`. 검사 결과가 아니라
  검사 자체를 수행하지 못한 것이다. (CLI 에서 exit 2 가 된다)

"검사 결과 FAIL" 과 "검사를 못 했음" 을 섞으면 CI 가 Audit 고장을 통과로 오독한다.

## Critical Hard Gate

모든 결함을 감점으로 처리하지 않는다. 기준선은 하나다.

    **거짓말이면 Critical, 미완성이면 감점.**

Guard 가 등록되지 않았는데 문서가 등록됐다고 말하면 그것은 거짓말이다. 종료 경로
eval 이 7개 중 4개뿐인 것은 미완성이다. 앞은 게이트, 뒤는 감점이다.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import re
import sys
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 버전 계약
#
# 셋은 바뀌는 이유와 소비자가 다르므로 따로 둔다.
#   schema_version - JSON 봉투 구조.        소비자: Dashboard / CI 파서
#   rubric_version - 채점 계약(id·배점·Critical). 소비자: 점수 비교
#   audit_version  - 구현.                  소비자: 재현 추적
# 점수는 같은 rubric_version 안에서만 비교할 수 있다.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
RUBRIC_VERSION = "1.0.0"
AUDIT_VERSION = "1.0.0"

# `sorted((check_id, max_score, is_critical))` 를 직렬화한 값의 sha256.
# rubric 을 버전 상승 없이 몰래 고치면 G3 가 Audit 자기 자신을 FAIL 시킨다.
RUBRIC_DIGEST = "sha256:2d63e22b8c5dab0e3852cbd48723f536edfbba9cfbd31d1b0b3d8a3ab7690edd"

MAX_SCORE = 100

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"

RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"


class AuditError(Exception):
    """Audit 을 수행할 수 없다. 검사 결과가 아니라 검사의 실패다. (CLI exit 2)"""


# ---------------------------------------------------------------------------
# rubric 이 소유하는 상수
#
# 코드 어디에도 정본이 없는 값만 여기서 선언한다. 나머지는 전부 import 한다.
# 이 둘도 그냥 두지 않고 다른 check 가 역검증한다.
#   LEAST_PRIVILEGE  <- A3(frontmatter) 과 F3(README 표) 이 서로 다른 문서로 삼각 검증
#   TERMINAL_ROUTES  <- E4a 가 BLOCKED_REASONS / FAILURE_CATEGORIES 로 근거 확인
# ---------------------------------------------------------------------------

# `CLAUDE.md §11` 이 산문으로 정한 Agent 별 최소 권한. 초과도 부족도 위반이다.
LEAST_PRIVILEGE = {
    "planner": ("Glob", "Grep", "Read", "Write"),
    "developer": ("Edit", "Glob", "Grep", "Read", "Write"),
    "tester": ("Bash", "Glob", "Grep", "Read", "Write"),
    "reviewer": ("Bash", "Glob", "Grep", "Read", "Write"),
}

# `CLAUDE.md §16` / `§20` 이 정의하는 종료 경로 전체.
# (route id, 근거 종류, 근거 값) — 근거 종류에 따라 어느 집합에 속해야 하는지가 다르다.
TERMINAL_ROUTES = (
    ("PRODUCT_CODE_DEFECT_RETRY", "category", "PRODUCT_CODE_DEFECT"),
    ("PLAN_DEFECT_REPLAN", "category", "PLAN_DEFECT"),
    ("ENVIRONMENT_ERROR", "blocked_reason", "ENVIRONMENT_ERROR"),
    ("RETRY_BUDGET_EXCEEDED", "blocked_reason", "RETRY_BUDGET_EXCEEDED"),
    ("TEST_DEFECT_NEEDS_HUMAN", "blocked_reason", "TEST_DEFECT_NEEDS_HUMAN"),
    ("UNKNOWN_TWICE", "blocked_reason", "UNKNOWN_TWICE"),
    ("REVIEW_CHANGES_REQUESTED_NO_BUDGET", "blocked_reason", "REVIEW_CHANGES_REQUESTED_NO_BUDGET"),
)

# Guard 파일과 그 등록 형태. B3 가 양방향으로 대조한다.
# matcher 가 None 인 것은 Stop 처럼 matcher 를 쓰지 않는 이벤트다.
GUARD_REGISTRATION = {
    "guard_test_files.py": ("PreToolUse", "Write|Edit"),
    "guard_plan_scope.py": ("PreToolUse", "Write|Edit"),
    "guard_bash_scope.py": ("PreToolUse", "Bash"),
    "guard_stop_gate.py": ("Stop", None),
}

AGENT_NAMES = ("developer", "planner", "reviewer", "tester")

# `CLAUDE.md §14` / `§15` 의 기계 판정 첫 줄. C5 가 드리프트를 본다.
CANONICAL_STATUS = ("FAIL", "PASS")
CANONICAL_VERDICT = ("APPROVED", "CHANGES_REQUESTED")

CATEGORIES = (
    ("agent-isolation", "A. Agent Role Isolation"),
    ("guard-enforcement", "B. Guard Registration & Enforcement"),
    ("contract-consistency", "C. Control Contract Consistency"),
    ("artifact-evidence", "D. Artifact & Evidence Contract"),
    ("eval-coverage", "E. Eval Coverage & Replay"),
    ("doc-consistency", "F. Documentation Consistency"),
    ("automation", "G. Reproducibility & Automation"),
)

# Critical check -> Hard Gate 이름. 5개 게이트 / 7개 check.
# 여기에 항목을 더하는 것은 rubric_version major 상승 사유다.
CRITICAL_GATES = {
    "A3": "ROLE_PRIVILEGE_DRIFT",
    "B3": "GUARD_NOT_ENFORCED",
    "B4": "STOP_GATE_SHAPE_INVALID",
    "C1": "CONTRACT_DIVERGENCE",
    "C2": "CONTRACT_DIVERGENCE",
    "D3": "EVIDENCE_INVALID",
    "D4": "EVIDENCE_INVALID",
}


# ---------------------------------------------------------------------------
# 파싱 도우미 — 고정 앵커만 읽는다
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.S | re.M)
_BACKTICK = re.compile(r"`([^`]+)`")
_UPPER_TOKEN = re.compile(r"[A-Z][A-Z_]*")
_PY_FILE = re.compile(r"([A-Za-z0-9_]+\.py)")


def markdown_sections(text: str) -> list[tuple[str, str]]:
    """`## ` heading 단위로 (heading, body) 목록을 만든다. 등장 순서를 유지한다."""
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading:
                sections.append((heading, "\n".join(body)))
            heading = line
            body = []
            continue
        if heading:
            body.append(line)
    if heading:
        sections.append((heading, "\n".join(body)))
    return sections


def section_body(text: str, keyword: str) -> str | None:
    """heading 에 `keyword` 가 들어간 첫 절의 본문. 없으면 None."""
    for heading, body in markdown_sections(text):
        if keyword in heading:
            return body
    return None


def fenced_lines(text: str) -> list[list[str]]:
    """코드펜스마다 비어 있지 않은 줄 목록을 돌려준다."""
    blocks = []
    for match in _FENCE.finditer(text):
        blocks.append([line.strip() for line in match.group(1).splitlines() if line.strip()])
    return blocks


def uppercase_token_fence(text: str) -> list[str] | None:
    """모든 줄이 `UPPER_SNAKE_CASE` 토큰 하나인 코드펜스의 내용.

    그런 펜스가 정확히 하나가 아니면 None 을 돌려준다. 두 개 이상이면 어느 쪽이
    계약인지 판단할 수 없고, Audit 은 판단할 수 없으면 FAIL 이다.
    """
    found = [
        lines
        for lines in fenced_lines(text)
        if len(lines) >= 2 and all(_UPPER_TOKEN.fullmatch(line) for line in lines)
    ]
    return found[0] if len(found) == 1 else None


def markdown_table(text: str, header_keyword: str) -> list[list[str]] | None:
    """header 행에 `header_keyword` 가 들어간 표의 데이터 행 목록. 없으면 None.

    구분선(`| --- |`)을 만난 다음부터 표가 끝날 때까지의 행만 모은다. README 에는
    같은 모양의 표가 여러 개 있으므로 heading 이 아니라 header 행으로 앵커한다.
    """
    rows: list[list[str]] = []
    state = "search"
    for line in text.splitlines():
        stripped = line.strip()
        if state == "search":
            if stripped.startswith("|") and header_keyword in stripped:
                state = "separator"
            continue
        if not stripped.startswith("|"):
            break
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if state == "separator":
            state = "rows"
            continue
        rows.append(cells)
    return rows if state == "rows" else None


def backtick_tokens(text: str) -> list[str]:
    return [token.strip() for token in _BACKTICK.findall(text)]


def parse_frontmatter(text: str, where: str) -> dict[str, str]:
    """`---` 로 감싼 YAML 유사 frontmatter 를 읽는다.

    형태가 깨져 있으면 FAIL 이 아니라 `AuditError` 다. 읽지 못한 파일을 "계약 위반"
    으로 보고하면 Audit 이 사실이 아닌 판정을 내놓게 된다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AuditError("{0}: frontmatter 가 `---` 로 시작하지 않습니다".format(where))
    fields: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return fields
        if not line.strip():
            continue
        if ":" not in line:
            raise AuditError(
                "{0}:{1}: frontmatter 항목이 `key: value` 형태가 아닙니다".format(where, index)
            )
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    raise AuditError("{0}: frontmatter 를 닫는 `---` 가 없습니다".format(where))


def tools_of(frontmatter: dict[str, str], where: str) -> tuple[str, ...]:
    raw = frontmatter.get("tools")
    if raw is None:
        raise AuditError("{0}: frontmatter 에 `tools` 가 없습니다".format(where))
    return tuple(sorted(item.strip() for item in raw.split(",") if item.strip()))


# ---------------------------------------------------------------------------
# 감사 대상 저장소 접근
# ---------------------------------------------------------------------------


def _module_alias(root: Path, stem: str) -> str:
    """감사 대상 root 마다 다른 모듈 이름. 서로 다른 root 의 모듈이 섞이지 않게 한다."""
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
    return "_pp_audit_{0}_{1}".format(digest, stem)


def _import_from_path(module_name: str, path: Path, where: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AuditError("{0}: 모듈로 읽을 수 없습니다".format(where))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - 원인 종류와 무관하게 실행 오류다
        sys.modules.pop(module_name, None)
        raise AuditError(
            "{0}: import 에 실패했습니다 ({1}: {2})".format(where, type(error).__name__, error)
        ) from error
    return module


@contextlib.contextmanager
def _bound_guard_common(module):
    """`guard_stop_gate` 가 `import _guard_common` 할 때 볼 모듈을 잠시 고정한다.

    가드는 패키지가 아니라 단독 스크립트라 형제 모듈을 sys.path 로 찾는다. 감사
    대상 root 의 `_guard_common` 을 쓰게 하려면 import 하는 동안만 이름을 잡아야
    한다. 실제 저장소를 감사할 때 이미 로드돼 있는 모듈을 덮어쓰지 않도록 복원한다.
    """
    previous = sys.modules.get("_guard_common")
    sys.modules["_guard_common"] = module
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("_guard_common", None)
        else:
            sys.modules["_guard_common"] = previous


class Repo:
    """감사 대상 저장소. 읽기 전용이며 파일을 하나도 쓰지 않는다."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise AuditError("감사 대상 경로가 디렉터리가 아닙니다: {0}".format(root))
        self._text: dict[str, str | None] = {}
        self._modules: dict[str, object] = {}

    # -- 파일 --------------------------------------------------------------

    def path(self, relative: str) -> Path:
        return self.root.joinpath(*relative.split("/"))

    def exists(self, relative: str) -> bool:
        return self.path(relative).exists()

    def is_file(self, relative: str) -> bool:
        return self.path(relative).is_file()

    def text(self, relative: str) -> str | None:
        """파일 내용. 없으면 None. 읽지 못하면 `AuditError`.

        개행은 LF 로 통일한다. 산출물이 Windows 에서 생성되어 CRLF 가 섞여 있고,
        정규화하지 않으면 첫 줄 판정과 코드펜스 파싱이 어긋난다.
        """
        if relative in self._text:
            return self._text[relative]
        target = self.path(relative)
        if not target.is_file():
            self._text[relative] = None
            return None
        try:
            body = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError) as error:
            raise AuditError(
                "{0}: 읽지 못했습니다 ({1})".format(relative, type(error).__name__)
            ) from error
        self._text[relative] = body
        return body

    def json(self, relative: str):
        """JSON 파일. 없으면 None. 있는데 파싱되지 않으면 `AuditError`."""
        body = self.text(relative)
        if body is None:
            return None
        try:
            return json.loads(body)
        except ValueError as error:
            raise AuditError("{0}: JSON 파싱에 실패했습니다 ({1})".format(relative, error)) from error

    def listdir(self, relative: str) -> list[str]:
        target = self.path(relative)
        if not target.is_dir():
            return []
        return sorted(entry.name for entry in target.iterdir())

    # -- 실제 구현 모듈 ----------------------------------------------------

    def guard_common(self):
        """`.claude/hooks/_guard_common.py`. 파일이 없으면 None."""
        return self._module("_guard_common", ".claude/hooks/_guard_common.py")

    def stop_gate(self):
        """`.claude/hooks/guard_stop_gate.py`. 파일이 없으면 None."""
        if "guard_stop_gate" in self._modules:
            return self._modules["guard_stop_gate"]
        relative = ".claude/hooks/guard_stop_gate.py"
        target = self.path(relative)
        if not target.is_file():
            self._modules["guard_stop_gate"] = None
            return None
        common = self.guard_common()
        if common is None:
            raise AuditError(
                "{0}: `_guard_common.py` 가 없어 import 할 수 없습니다".format(relative)
            )
        with _bound_guard_common(common):
            module = _import_from_path(
                _module_alias(self.root, "guard_stop_gate"), target, relative
            )
        self._modules["guard_stop_gate"] = module
        return module

    def eval_harness(self):
        """`evals/eval_harness.py`. 파일이 없으면 None."""
        return self._module("eval_harness", "evals/eval_harness.py")

    def _module(self, key: str, relative: str):
        if key in self._modules:
            return self._modules[key]
        target = self.path(relative)
        if not target.is_file():
            self._modules[key] = None
            return None
        module = _import_from_path(_module_alias(self.root, key), target, relative)
        self._modules[key] = module
        return module

    # -- 자주 쓰는 파생 값 --------------------------------------------------

    def example_dirs(self) -> list[str]:
        """`reports/examples/` 의 대표 결과 디렉터리 이름. 항상 정렬된 순서."""
        base = self.path("reports/examples")
        if not base.is_dir():
            return []
        return sorted(entry.name for entry in base.iterdir() if entry.is_dir())

    def agent_frontmatter(self) -> dict[str, dict[str, str]]:
        """존재하는 Agent 정의의 frontmatter. 파일이 없는 Agent 는 키가 없다."""
        parsed: dict[str, dict[str, str]] = {}
        for name in AGENT_NAMES:
            relative = ".claude/agents/{0}.md".format(name)
            body = self.text(relative)
            if body is None:
                continue
            parsed[name] = parse_frontmatter(body, relative)
        return parsed

    def guard_files(self) -> list[str]:
        """`.claude/hooks/` 의 guard 파일 이름. 공통 모듈은 제외한다."""
        return [
            name
            for name in self.listdir(".claude/hooks")
            if name.startswith("guard_") and name.endswith(".py")
        ]


# ---------------------------------------------------------------------------
# check 결과
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """check 하나의 판정. 점수는 rubric 이 정하므로 여기에 없다."""

    passed: bool
    evidence: tuple[str, ...]


def ok(*evidence: str) -> Outcome:
    return Outcome(True, tuple(evidence))


def bad(*evidence: str) -> Outcome:
    return Outcome(False, tuple(evidence))


def _render(values) -> str:
    return ", ".join(str(value) for value in values) if values else "(없음)"


# ---------------------------------------------------------------------------
# A. Agent Role Isolation
# ---------------------------------------------------------------------------


def check_a1(repo: Repo) -> Outcome:
    missing = [name for name in AGENT_NAMES if not repo.is_file(".claude/agents/{0}.md".format(name))]
    if missing:
        return bad("정의 파일 없음: {0}".format(_render(missing)))
    incomplete = []
    for name, front in sorted(repo.agent_frontmatter().items()):
        absent = [key for key in ("name", "description", "tools") if key not in front]
        if absent:
            incomplete.append("{0}: {1} 없음".format(name, _render(absent)))
    if incomplete:
        return bad(*incomplete)
    return ok(
        ".claude/agents/: {0}".format(_render(AGENT_NAMES)),
        "각 frontmatter 에 name / description / tools 존재",
    )


def check_a2(repo: Repo) -> Outcome:
    common = repo.guard_common()
    if common is None:
        return bad(".claude/hooks/_guard_common.py 가 없어 AGENT_TYPES 를 대조할 수 없습니다")
    declared = tuple(sorted(common.AGENT_TYPES))
    front = repo.agent_frontmatter()
    actual = tuple(sorted(value.get("name", "") for value in front.values()))
    if actual != declared:
        return bad(
            "_guard_common.AGENT_TYPES = {0}".format(_render(declared)),
            "frontmatter name = {0}".format(_render(actual)),
        )
    return ok(
        "_guard_common.AGENT_TYPES = {0}".format(_render(declared)),
        "frontmatter name 집합 일치",
    )


def check_a3(repo: Repo) -> Outcome:
    """최소 권한 행렬 일치. 초과 권한도 부족 권한도 위반이다.

    Developer 가 Bash 를 얻는 순간 "Developer 는 테스트를 실행할 수 없다" 는 README
    의 핵심 주장이 거짓이 된다. 미완성이 아니라 거짓말이므로 Critical 이다.

    **정의 파일이 없는 Agent 는 여기서 판정하지 않는다.** 없는 선언은 거짓말이
    아니라 미완성이며, 그것은 A1 이 감점으로 잡는다. 파일 부재를 Critical 로
    올리면 "거짓말이면 Critical, 미완성이면 감점" 기준선이 무너진다. 다만 정의가
    **하나도** 없으면 최소 권한 주장을 뒷받침할 근거가 아예 없으므로 FAIL 이다.
    """
    front = repo.agent_frontmatter()
    if not front:
        return bad("Agent 정의가 하나도 없어 최소 권한 행렬을 확인할 수 없습니다")
    problems = []
    evidence = []
    for name in sorted(front):
        expected = LEAST_PRIVILEGE.get(name)
        if expected is None:
            problems.append("{0}: 최소 권한 행렬에 없는 Agent 입니다".format(name))
            continue
        actual = tools_of(front[name], ".claude/agents/{0}.md".format(name))
        evidence.append("{0}: {1}".format(name, _render(actual)))
        if actual != expected:
            extra = sorted(set(actual) - set(expected))
            lack = sorted(set(expected) - set(actual))
            problems.append(
                "{0}: 기대={1} / 실제={2}{3}{4}".format(
                    name,
                    _render(expected),
                    _render(actual),
                    " / 초과={0}".format(_render(extra)) if extra else "",
                    " / 부족={0}".format(_render(lack)) if lack else "",
                )
            )
    if problems:
        return bad(*problems)
    return ok(*evidence)


def check_a4(repo: Repo) -> Outcome:
    required = ("## 5. 금지 사항", "## 6. 종료 전 체크리스트")
    problems = []
    for name in AGENT_NAMES:
        relative = ".claude/agents/{0}.md".format(name)
        body = repo.text(relative)
        if body is None:
            problems.append("{0}: 정의 파일 없음".format(name))
            continue
        absent = [heading for heading in required if heading not in body]
        if absent:
            problems.append("{0}: {1} 절 없음".format(name, _render(absent)))
    if problems:
        return bad(*problems)
    return ok("4개 Agent 정의 모두 금지 사항 / 종료 전 체크리스트 절 보유")


# ---------------------------------------------------------------------------
# B. Guard Registration & Enforcement
# ---------------------------------------------------------------------------


def check_b1(repo: Repo) -> Outcome:
    required = ["_guard_common.py"] + sorted(GUARD_REGISTRATION)
    missing = [name for name in required if not repo.is_file(".claude/hooks/{0}".format(name))]
    if missing:
        return bad("없음: {0}".format(_render(missing)))
    return ok(".claude/hooks/: {0}".format(_render(required)))


def check_b2(repo: Repo) -> Outcome:
    pattern = re.compile(r'^HOOK_ID\s*=\s*"([^"]+)"', re.M)
    ids: dict[str, str] = {}
    problems = []
    for name in sorted(GUARD_REGISTRATION):
        body = repo.text(".claude/hooks/{0}".format(name))
        if body is None:
            problems.append("{0}: 파일 없음".format(name))
            continue
        match = pattern.search(body)
        if match is None:
            problems.append("{0}: HOOK_ID 상수 없음".format(name))
            continue
        expected = name[: -len(".py")].replace("_", "-")
        ids[name] = match.group(1)
        if match.group(1) != expected:
            problems.append(
                "{0}: HOOK_ID={1!r} / 파일명 기준 기대={2!r}".format(name, match.group(1), expected)
            )
    if len(set(ids.values())) != len(ids):
        problems.append("HOOK_ID 가 중복됩니다: {0}".format(_render(sorted(ids.values()))))
    if problems:
        return bad(*problems)
    return ok(*["{0} -> {1}".format(name, ids[name]) for name in sorted(ids)])


def _settings_registrations(settings) -> dict[str, tuple[str, object]]:
    """settings.json 에 등록된 {훅 파일명: (이벤트, matcher)}."""
    found: dict[str, tuple[str, object]] = {}
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        return found
    for event, entries in sorted(hooks.items()):
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher")
            commands = entry.get("hooks")
            if not isinstance(commands, list):
                continue
            for command in commands:
                if not isinstance(command, dict):
                    continue
                line = command.get("command")
                if not isinstance(line, str):
                    continue
                for name in _PY_FILE.findall(line):
                    found[name] = (event, matcher)
    return found


def check_b3(repo: Repo) -> Outcome:
    """등록 집합 양방향 일치 + matcher 대조.

    파일은 있는데 등록이 없으면 통제는 0% 동작한다. 문서와 코드가 모두 거짓이
    되므로 Critical 이다. "등록 누락" 과 "등록됐지만 파일 없음" 은 같은 실패이므로
    check 를 쪼개지 않는다. 쪼개면 한쪽만 Critical 이 되어 게이트가 샌다.
    """
    settings = repo.json(".claude/settings.json")
    if settings is None:
        return bad(".claude/settings.json 이 없습니다")
    registered = _settings_registrations(settings)
    on_disk = set(repo.guard_files())
    declared = set(registered)

    problems = []
    unregistered = sorted(on_disk - declared)
    if unregistered:
        problems.append("가드 파일이 있는데 settings.json 에 등록되지 않음: {0}".format(_render(unregistered)))
    orphan = sorted(declared - on_disk)
    if orphan:
        problems.append("settings.json 에 등록됐는데 파일이 없음: {0}".format(_render(orphan)))

    for name in sorted(GUARD_REGISTRATION):
        expected = GUARD_REGISTRATION[name]
        if name not in registered:
            if name not in orphan and name not in unregistered:
                problems.append("{0}: 등록 없음".format(name))
            continue
        if registered[name] != expected:
            problems.append(
                "{0}: 기대 등록={1} / 실제={2}".format(name, expected, registered[name])
            )
    if problems:
        return bad(*problems)
    return ok(
        *[
            "{0} -> {1} matcher={2}".format(name, registered[name][0], registered[name][1])
            for name in sorted(registered)
        ]
    )


def check_b4(repo: Repo) -> Outcome:
    """Stop 등록이 중첩형인가.

    평면형(`"Stop": [{"type": "command", ...}]`)은 파싱 오류 없이 **조용히 무시**
    된다. 존재 검사만으로는 잡히지 않는 무증상 실패 모드라 별도 Critical 이다.
    """
    settings = repo.json(".claude/settings.json")
    if settings is None:
        return bad(".claude/settings.json 이 없습니다")
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    entries = hooks.get("Stop") if isinstance(hooks, dict) else None
    if not isinstance(entries, list) or not entries:
        return bad("settings.json 에 Stop 훅 등록이 없습니다")
    flat = [entry for entry in entries if not isinstance(entry, dict) or "hooks" not in entry]
    if flat:
        return bad(
            "Stop 등록이 평면형입니다 - 파싱 오류 없이 무시됩니다",
            'Stop[0] 키={0}'.format(_render(sorted(flat[0])) if isinstance(flat[0], dict) else type(flat[0]).__name__),
        )
    return ok("Stop 등록이 중첩형 (hooks 배열을 감싼 형태) 입니다: {0}건".format(len(entries)))


def check_b5(repo: Repo) -> Outcome:
    missing = []
    present = []
    for name in sorted(GUARD_REGISTRATION):
        relative = "evals/tests/test_{0}".format(name)
        if repo.is_file(relative):
            present.append(relative)
        else:
            missing.append(relative)
    if missing:
        return bad("단위 테스트 없음: {0}".format(_render(missing)))
    return ok(*present)


# ---------------------------------------------------------------------------
# C. Control Contract Consistency
#
# Audit 의 정체성이다. 같은 상수가 여러 곳에 독립 선언되어 있고, 한 곳만 바뀌어도
# 어떤 테스트도 깨지지 않은 채 라우팅이 갈라진다.
# ---------------------------------------------------------------------------


def _claude_failure_categories(repo: Repo) -> tuple[str, ...] | None:
    body = repo.text("CLAUDE.md")
    if body is None:
        return None
    part = section_body(body, "14.")
    if part is None:
        return None
    lines = uppercase_token_fence(part)
    return tuple(sorted(lines)) if lines else None


def _tester_failure_categories(repo: Repo) -> tuple[str, ...] | None:
    body = repo.text(".claude/agents/tester.md")
    if body is None:
        return None
    part = section_body(body, "3. 작업 절차")
    if part is None:
        return None
    found = []
    for line in part.splitlines():
        stripped = line.strip()
        if not stripped.startswith("* "):
            continue
        tokens = backtick_tokens(stripped)
        if tokens and _UPPER_TOKEN.fullmatch(tokens[0]):
            found.append(tokens[0])
    return tuple(sorted(found)) if found else None


def _types_failure_categories(repo: Repo) -> tuple[str, ...] | None:
    body = repo.text("dashboard/lib/types.ts")
    if body is None:
        return None
    match = re.search(r"export const FAILURE_CATEGORIES\s*=\s*\[(.*?)\]", body, re.S)
    if match is None:
        return None
    found = re.findall(r"'([A-Z][A-Z_]*)'", match.group(1))
    return tuple(sorted(found)) if found else None


def check_c1(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    sources = {
        "CLAUDE.md §14": _claude_failure_categories(repo),
        ".claude/agents/tester.md": _tester_failure_categories(repo),
        "evals/eval_harness.py FAILURE_CATEGORIES": (
            tuple(sorted(harness.FAILURE_CATEGORIES)) if harness is not None else None
        ),
        "dashboard/lib/types.ts": _types_failure_categories(repo),
    }
    unreadable = sorted(name for name, value in sources.items() if value is None)
    if unreadable:
        return bad("실패 분류를 추출하지 못한 소스: {0}".format(_render(unreadable)))
    distinct = {value for value in sources.values()}
    if len(distinct) != 1:
        return bad(*["{0} = {1}".format(name, _render(sources[name])) for name in sorted(sources)])
    agreed = next(iter(distinct))
    return ok(
        "4개 소스 일치: {0}".format(_render(agreed)),
        *sorted(sources),
    )


def _patchpilot_blocked_reasons(repo: Repo) -> tuple[str, ...] | None:
    body = repo.text(".claude/commands/patchpilot.md")
    if body is None:
        return None
    lines = uppercase_token_fence(body)
    return tuple(sorted(lines)) if lines else None


def check_c2(repo: Repo) -> Outcome:
    gate = repo.stop_gate()
    document = _patchpilot_blocked_reasons(repo)
    if gate is None:
        return bad(".claude/hooks/guard_stop_gate.py 가 없어 BLOCKED_REASONS 를 대조할 수 없습니다")
    if document is None:
        return bad(".claude/commands/patchpilot.md 에서 사유 코드 목록을 추출하지 못했습니다")
    code = tuple(sorted(gate.BLOCKED_REASONS))
    if document != code:
        return bad(
            "patchpilot.md §10 = {0}개 {1}".format(len(document), _render(document)),
            "guard_stop_gate.BLOCKED_REASONS = {0}개 {1}".format(len(code), _render(code)),
            "문서에만 있음: {0}".format(_render(sorted(set(document) - set(code)))),
            "코드에만 있음: {0}".format(_render(sorted(set(code) - set(document)))),
        )
    return ok("patchpilot.md §10 == guard_stop_gate.BLOCKED_REASONS ({0}개)".format(len(code)))


_PYTEST_COMMAND = re.compile(r"uv run pytest [^`\"'\n)]*")


def check_c3(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    if harness is None:
        return bad("evals/eval_harness.py 가 없어 PYTEST_COMMAND 를 대조할 수 없습니다")
    canonical = harness.PYTEST_COMMAND

    sources: dict[str, tuple[str, ...] | None] = {}
    for relative in ("CLAUDE.md", ".claude/agents/tester.md", ".claude/commands/patchpilot.md"):
        body = repo.text(relative)
        if body is None:
            sources[relative] = None
            continue
        found = {match.strip() for match in _PYTEST_COMMAND.findall(body)}
        sources[relative] = tuple(sorted(found)) if found else None

    bash_scope = repo.text(".claude/hooks/guard_bash_scope.py")
    if bash_scope is None:
        sources[".claude/hooks/guard_bash_scope.py"] = None
    else:
        match = re.search(r"TESTER_PYTEST_TOKENS\s*=\s*\((.*?)\)", bash_scope, re.S)
        tokens = re.findall(r'"([^"]+)"', match.group(1)) if match else []
        sources[".claude/hooks/guard_bash_scope.py"] = (" ".join(tokens),) if tokens else None

    unreadable = sorted(name for name, value in sources.items() if value is None)
    if unreadable:
        return bad("고정 테스트 명령을 추출하지 못한 소스: {0}".format(_render(unreadable)))
    divergent = {
        name: value for name, value in sources.items() if value != (canonical,)
    }
    if divergent:
        return bad(
            "evals/eval_harness.py PYTEST_COMMAND = {0!r}".format(canonical),
            *["{0} = {1}".format(name, _render(divergent[name])) for name in sorted(divergent)],
        )
    return ok(
        "5개 소스 모두 {0!r}".format(canonical),
        *sorted(list(sources) + ["evals/eval_harness.py PYTEST_COMMAND"]),
    )


# `retry_budget` 추출 앵커. 산문을 해석하지 않고 토큰 옆의 숫자만 읽는다.
_BUDGET_CLAUDE = re.compile(r"`retry_budget`\s*이\s*(\d+)")
_BUDGET_COMMAND = re.compile(r'"retry_budget"\s*:\s*(\d+)|retry_budget\s*=\s*(\d+)')


def check_c4(repo: Repo) -> Outcome:
    found: dict[str, tuple[int, ...]] = {}

    body = repo.text("CLAUDE.md")
    if body is not None:
        part = section_body(body, "16.")
        values = _BUDGET_CLAUDE.findall(part or "")
        found["CLAUDE.md §16"] = tuple(sorted({int(value) for value in values}))

    body = repo.text(".claude/commands/patchpilot.md")
    if body is not None:
        values = [
            int(first or second) for first, second in _BUDGET_COMMAND.findall(body)
        ]
        found[".claude/commands/patchpilot.md"] = tuple(sorted(set(values)))

    harness = repo.eval_harness()
    if harness is not None:
        import dataclasses

        defaults = [
            field.default
            for field in dataclasses.fields(harness.Scenario)
            if field.name == "expected_retry_budget"
        ]
        scenario_values = {scenario.expected_retry_budget for scenario in harness.SCENARIOS.values()}
        found["evals/eval_harness.py Scenario"] = tuple(sorted(set(defaults) | scenario_values))

    example_values = set()
    for name in repo.example_dirs():
        state = repo.json("reports/examples/{0}/state.json".format(name))
        if isinstance(state, dict) and "retry_budget" in state:
            example_values.add(state["retry_budget"])
    if example_values:
        found["reports/examples/*/state.json"] = tuple(sorted(example_values))

    empty = sorted(name for name, value in found.items() if not value)
    if empty or len(found) < 4:
        return bad(
            "retry_budget 을 추출하지 못한 소스: {0}".format(
                _render(empty or ["소스 {0}개만 확인됨".format(len(found))])
            )
        )
    distinct = {value for value in found.values()}
    if len(distinct) != 1 or next(iter(distinct)) != (3,):
        return bad(*["{0} = {1}".format(name, _render(found[name])) for name in sorted(found)])
    return ok("4개 소스 모두 retry_budget = 3", *sorted(found))


_STATUS_TOKEN = re.compile(r"STATUS: ([A-Z_]+)")
_VERDICT_TOKEN = re.compile(r"VERDICT: ([A-Z_]+)")


def check_c5(repo: Repo) -> Outcome:
    sources = (
        ".claude/hooks/guard_stop_gate.py",
        "evals/eval_harness.py",
        "dashboard/lib/parse.ts",
    )
    seen_status: set[str] = set()
    seen_verdict: set[str] = set()
    problems = []
    evidence = []
    for relative in sources:
        body = repo.text(relative)
        if body is None:
            problems.append("{0}: 파일 없음".format(relative))
            continue
        statuses = set(_STATUS_TOKEN.findall(body))
        verdicts = set(_VERDICT_TOKEN.findall(body))
        if not statuses and not verdicts:
            problems.append("{0}: 기계 판정 첫 줄 리터럴이 하나도 없습니다".format(relative))
            continue
        stray_status = sorted(statuses - set(CANONICAL_STATUS))
        stray_verdict = sorted(verdicts - set(CANONICAL_VERDICT))
        if stray_status or stray_verdict:
            problems.append(
                "{0}: 계약 밖 토큰 STATUS={1} VERDICT={2}".format(
                    relative, _render(stray_status), _render(stray_verdict)
                )
            )
        seen_status |= statuses
        seen_verdict |= verdicts
        evidence.append(
            "{0}: STATUS={1} / VERDICT={2}".format(
                relative, _render(sorted(statuses)), _render(sorted(verdicts))
            )
        )
    missing_status = sorted(set(CANONICAL_STATUS) - seen_status)
    missing_verdict = sorted(set(CANONICAL_VERDICT) - seen_verdict)
    if missing_status or missing_verdict:
        problems.append(
            "세 소스를 합쳐도 나타나지 않는 토큰 STATUS={0} VERDICT={1}".format(
                _render(missing_status), _render(missing_verdict)
            )
        )
    if problems:
        return bad(*problems)
    return ok(*evidence)


# ---------------------------------------------------------------------------
# D. Artifact & Evidence Contract
# ---------------------------------------------------------------------------


def check_d1(repo: Repo) -> Outcome:
    names = repo.example_dirs()
    if not names:
        return bad("reports/examples/ 에 보존된 대표 결과가 없습니다")
    problems = []
    for name in names:
        for required in ("state.json", "report.md"):
            relative = "reports/examples/{0}/{1}".format(name, required)
            if not repo.is_file(relative):
                problems.append("{0} 없음".format(relative))
    if problems:
        return bad(*problems)
    return ok("대표 결과 {0}건: {1}".format(len(names), _render(names)))


def check_d2(repo: Repo) -> Outcome:
    """state.json 의 스키마와 enum.

    승격 이후 도입된 필드(`session_id` 등)는 검사하지 않는다. 보존된 증거는 승격
    시점의 계약으로만 판정한다. 현재 계약을 옛 증거에 소급 적용하면 정상 저장소에
    첫 실행부터 오탐이 뜬다.
    """
    gate = repo.stop_gate()
    harness = repo.eval_harness()
    if gate is None or harness is None:
        return bad("BLOCKED_REASONS / FAILURE_CATEGORIES 를 제공하는 모듈이 없어 판정할 수 없습니다")
    names = repo.example_dirs()
    if not names:
        return bad("reports/examples/ 에 보존된 대표 결과가 없습니다")

    problems = []
    for name in names:
        relative = "reports/examples/{0}/state.json".format(name)
        state = repo.json(relative)
        if state is None:
            problems.append("{0} 없음".format(relative))
            continue
        if not isinstance(state, dict):
            problems.append("{0}: 최상위가 객체가 아닙니다".format(relative))
            continue
        final_status = state.get("final_status")
        if final_status not in gate.FINAL_STATUSES:
            problems.append("{0}: final_status={1!r}".format(relative, final_status))
        reason = state.get("blocked_reason")
        if reason is not None and reason not in gate.BLOCKED_REASONS:
            problems.append("{0}: blocked_reason={1!r}".format(relative, reason))
        attempts = state.get("attempts")
        if not isinstance(attempts, list):
            problems.append("{0}: attempts 가 배열이 아닙니다".format(relative))
        else:
            for index, attempt in enumerate(attempts, start=1):
                if not isinstance(attempt, dict):
                    problems.append("{0}: attempts[{1}] 이 객체가 아닙니다".format(relative, index))
                    continue
                category = attempt.get("failure_category")
                if category is not None and category not in harness.FAILURE_CATEGORIES:
                    problems.append(
                        "{0}: attempts[{1}].failure_category={2!r}".format(relative, index, category)
                    )
        count = state.get("retry_count")
        budget = state.get("retry_budget")
        if not isinstance(count, int) or isinstance(count, bool):
            problems.append("{0}: retry_count={1!r}".format(relative, count))
        elif not isinstance(budget, int) or isinstance(budget, bool):
            problems.append("{0}: retry_budget={1!r}".format(relative, budget))
        elif not 0 <= count <= budget:
            problems.append("{0}: retry_count={1} / retry_budget={2}".format(relative, count, budget))
    if problems:
        return bad(*problems)
    return ok("대표 결과 {0}건의 state.json 이 스키마와 enum 계약을 만족".format(len(names)))


def check_d3(repo: Repo) -> Outcome:
    """Stop Gate 불변식 G1~G19 를 보존된 증거에 오프라인으로 재적용한다.

    **판정을 재구현하지 않는다.** `guard_stop_gate.check_run()` 을 그대로 호출한다.
    같은 규칙의 판정 코드가 두 벌이 되면 그 순간부터 둘은 갈라진다.
    """
    gate = repo.stop_gate()
    if gate is None:
        return bad(".claude/hooks/guard_stop_gate.py 가 없어 replay 할 수 없습니다")
    if not hasattr(gate, "check_run"):
        return bad("guard_stop_gate 에 공개 진입점 check_run() 이 없습니다")
    names = repo.example_dirs()
    if not names:
        return bad("reports/examples/ 에 보존된 대표 결과가 없습니다")

    problems = []
    evidence = []
    for name in names:
        relative = "reports/examples/{0}/state.json".format(name)
        state = repo.json(relative)
        if not isinstance(state, dict):
            problems.append("{0}: state.json 을 읽지 못했습니다".format(name))
            continue
        if state.get("final_status") not in gate.FINAL_STATUSES:
            # check_run() 의 전제를 만족하지 못한다. 판단 불가는 FAIL 이다.
            problems.append(
                "{0}: final_status={1!r} 이라 G1~G19 를 적용할 수 없습니다".format(
                    name, state.get("final_status")
                )
            )
            continue
        result = gate.check_run(state, repo.path("reports/examples/{0}".format(name)))
        if result.violations:
            problems.append(
                "{0}: 위반 {1}".format(
                    name,
                    _render(
                        [
                            "[{0}] 기대={1} / 실제={2}".format(item.gid, item.expected, item.actual)
                            for item in result.violations
                        ]
                    ),
                )
            )
        else:
            evidence.append(
                "{0}: {1} / 위반 0건{2}".format(
                    name,
                    state.get("final_status"),
                    " / 건너뛴 검사 {0}건".format(len(result.notes)) if result.notes else "",
                )
            )
    if problems:
        return bad(*problems)
    return ok("guard_stop_gate.check_run() replay", *evidence)


def check_d4(repo: Repo) -> Outcome:
    names = repo.example_dirs()
    if not names:
        return bad("reports/examples/ 에 보존된 대표 결과가 없습니다")
    problems = []
    for name in names:
        relative = "reports/examples/{0}/eval-result.md".format(name)
        body = repo.text(relative)
        if body is None:
            problems.append("{0} 없음".format(relative))
            continue
        first = next((line.strip() for line in body.splitlines() if line.strip()), "")
        if first != "EVAL: PASS":
            problems.append("{0}: 첫 줄={1!r}".format(relative, first))
    if problems:
        return bad(*problems)
    return ok("대표 결과 {0}건 모두 첫 줄이 'EVAL: PASS'".format(len(names)))


def check_d5(repo: Repo) -> Outcome:
    body = repo.text(".gitignore")
    if body is None:
        return bad(".gitignore 가 없습니다")
    lines = {line.strip() for line in body.splitlines()}
    required = ("reports/*", "!reports/examples/", "!reports/examples/**")
    missing = [item for item in required if item not in lines]
    if missing:
        return bad("gitignore 규칙 없음: {0}".format(_render(missing)))
    return ok("reports/* 무시 + reports/examples/** 보존")


# ---------------------------------------------------------------------------
# E. Eval Coverage & Replay
# ---------------------------------------------------------------------------


def _scenario_route(harness, scenario) -> str | None:
    """시나리오가 검증하는 종료 경로 id. 결정론적 매핑이며 추측하지 않는다."""
    if scenario.outcome == harness.OUTCOME_SUCCESS_AFTER_RETRY:
        for route, kind, value in TERMINAL_ROUTES:
            if kind == "category" and value == scenario.expected_category:
                return route
        return None
    reason = scenario.expected_blocked_reason
    for route, kind, value in TERMINAL_ROUTES:
        if kind == "blocked_reason" and value == reason:
            return route
    return None


def check_e1(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    if harness is None:
        return bad("evals/eval_harness.py 가 없습니다")
    problems = []
    evidence = []
    for scenario_id, scenario in sorted(harness.SCENARIOS.items()):
        if not repo.is_file(scenario.task):
            problems.append("{0}: task 없음 {1}".format(scenario_id, scenario.task))
        for fixture_name, _install_path in scenario.installs:
            relative = "evals/fixtures/{0}".format(fixture_name)
            if not repo.is_file(relative):
                problems.append("{0}: install fixture 없음 {1}".format(scenario_id, relative))
        evidence.append(
            "{0}: task + fixture {1}개".format(scenario_id, len(scenario.installs))
        )
    if problems:
        return bad(*problems)
    return ok(*evidence)


def check_e2(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    if harness is None:
        return bad("evals/eval_harness.py 가 없습니다")
    problems = []
    evidence = []
    for scenario_id, example_name, _golden in harness.REGRESSION_EXAMPLES:
        relative = "reports/examples/{0}".format(example_name)
        if repo.path(relative).is_dir():
            evidence.append("{0} -> {1}".format(scenario_id, relative))
        else:
            problems.append("{0}: 회귀 기준 대표 결과 없음 {1}".format(scenario_id, relative))
    if problems:
        return bad(*problems)
    return ok(*evidence)


_SUMMARY = re.compile(r"(\d+)\s*/\s*(\d+)\s*항목 통과")


def check_e3(repo: Repo) -> Outcome:
    names = repo.example_dirs()
    if not names:
        return bad("reports/examples/ 에 보존된 대표 결과가 없습니다")
    problems = []
    evidence = []
    for name in names:
        relative = "reports/examples/{0}/eval-result.md".format(name)
        body = repo.text(relative)
        if body is None:
            problems.append("{0} 없음".format(relative))
            continue
        summary_body = section_body(body, "종합")
        match = _SUMMARY.search(summary_body or "")
        if match is None:
            problems.append("{0}: '## 종합' 에서 N/M 을 읽지 못했습니다".format(relative))
            continue
        passed, total = int(match.group(1)), int(match.group(2))
        table = markdown_table(body, "항목")
        rows = len(table) if table is not None else None
        if rows is None:
            problems.append("{0}: 자동 검증 항목 표를 읽지 못했습니다".format(relative))
            continue
        if passed != total or total != rows:
            problems.append(
                "{0}: 종합={1}/{2} / 표 행 수={3}".format(relative, passed, total, rows)
            )
            continue
        evidence.append("{0}: {1}/{2} 항목 (표 {3}행)".format(name, passed, total, rows))
    if problems:
        return bad(*problems)
    return ok(*evidence)


def _covered_routes(repo: Repo) -> tuple[set[str], list[str]]:
    """(검증된 종료 경로 집합, 문제 목록)."""
    harness = repo.eval_harness()
    if harness is None:
        return set(), ["evals/eval_harness.py 가 없습니다"]
    gate = repo.stop_gate()
    problems = []

    # TERMINAL_ROUTES 는 rubric 이 소유하는 상수다. 그대로 믿지 않고 실제 구현의
    # 집합으로 근거를 확인한다. 근거가 없으면 경로 수를 셀 자격이 없다.
    for route, kind, value in TERMINAL_ROUTES:
        if kind == "blocked_reason":
            if gate is None:
                problems.append("guard_stop_gate 가 없어 {0} 의 근거를 확인할 수 없습니다".format(route))
            elif value not in gate.BLOCKED_REASONS:
                problems.append("{0}: {1} 이 BLOCKED_REASONS 에 없습니다".format(route, value))
        elif value not in harness.FAILURE_CATEGORIES:
            problems.append("{0}: {1} 이 FAILURE_CATEGORIES 에 없습니다".format(route, value))

    covered = set()
    for scenario_id, scenario in sorted(harness.SCENARIOS.items()):
        route = _scenario_route(harness, scenario)
        if route is None:
            problems.append("{0}: 종료 경로를 특정하지 못했습니다".format(scenario_id))
            continue
        covered.add(route)
    return covered, problems


def check_e4a(repo: Repo) -> Outcome:
    covered, problems = _covered_routes(repo)
    if problems:
        return bad(*problems)
    if len(covered) < 4:
        return bad("검증된 종료 경로 {0}개: {1}".format(len(covered), _render(sorted(covered))))
    return ok(
        "검증된 종료 경로 {0}/{1}개".format(len(covered), len(TERMINAL_ROUTES)),
        _render(sorted(covered)),
    )


def check_e4b(repo: Repo) -> Outcome:
    covered, problems = _covered_routes(repo)
    if problems:
        return bad(*problems)
    missing = sorted({route for route, _kind, _value in TERMINAL_ROUTES} - covered)
    if missing:
        return bad(
            "검증되지 않은 종료 경로 {0}개: {1}".format(len(missing), _render(missing)),
            "검증됨: {0}".format(_render(sorted(covered))),
        )
    return ok("종료 경로 {0}개 전부 결정론적 eval 보유".format(len(TERMINAL_ROUTES)))


def check_e5(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    if harness is None:
        return bad("evals/eval_harness.py 가 없습니다")
    problems = []
    referenced = set()
    for scenario_id, scenario in sorted(harness.SCENARIOS.items()):
        for fault_id in scenario.fault_ids:
            referenced.add(fault_id)
            relative = "evals/faults/{0}.py".format(fault_id)
            if not repo.is_file(relative):
                problems.append("{0}: 결함 모듈 없음 {1}".format(scenario_id, relative))
    if problems:
        return bad(*problems)
    return ok("참조된 결함 모듈 {0}개 모두 존재: {1}".format(len(referenced), _render(sorted(referenced))))


def check_e6(repo: Repo) -> Outcome:
    harness = repo.eval_harness()
    if harness is None:
        return bad("evals/eval_harness.py 가 없습니다")
    problems = []
    evidence = []
    for scenario_id, scenario in sorted(harness.SCENARIOS.items()):
        ids = scenario.fault_ids
        if len(set(ids)) != len(ids):
            problems.append("{0}: 같은 결함이 반복 주입됩니다 {1}".format(scenario_id, _render(ids)))
        elif scenario.is_chained:
            evidence.append("{0}: 연쇄 {1}개 모두 서로 다름".format(scenario_id, len(ids)))
    if problems:
        return bad(*problems)
    return ok(*(evidence or ["연쇄 주입 시나리오 없음 - 중복 주입도 없음"]))


# ---------------------------------------------------------------------------
# F. Documentation Consistency
# ---------------------------------------------------------------------------


def check_f1(repo: Repo) -> Outcome:
    """`CLAUDE.md §22` 의 `[x]` 항목이 지목하는 파일이 실재하는가.

    백틱 토큰 중 `.py` 로 끝나는 것과 `/` 로 끝나는 것만 해석한다. `tasks/BUG-XXX.md`
    같은 패턴이나 `/patchpilot` 같은 커맨드 이름은 파일 경로가 아니므로 건드리지
    않는다. 산문을 해석하지 않는다는 원칙 그대로다.
    """
    body = repo.text("CLAUDE.md")
    if body is None:
        return bad("CLAUDE.md 가 없습니다")
    part = section_body(body, "22.")
    if part is None:
        return bad("CLAUDE.md 에서 §22 절을 찾지 못했습니다")
    done = [line for line in part.splitlines() if line.strip().startswith("* [x]")]
    if not done:
        return bad("CLAUDE.md §22 에서 완료(`[x]`) 항목을 찾지 못했습니다")

    problems = []
    resolved = []
    for line in done:
        for token in backtick_tokens(line):
            if token.endswith(".py"):
                relative = ".claude/hooks/{0}".format(token)
            elif token.endswith("/"):
                relative = token.rstrip("/")
            else:
                continue
            if repo.exists(relative):
                resolved.append(relative)
            else:
                problems.append("{0}: 없음 (근거: {1})".format(relative, token))
    if problems:
        return bad(*problems)
    return ok(
        "§22 완료 항목 {0}개".format(len(done)),
        "확인된 경로: {0}".format(_render(sorted(set(resolved)))),
    )


def check_f2(repo: Repo) -> Outcome:
    body = repo.text("README.md")
    if body is None:
        return bad("README.md 가 없습니다")
    rows = markdown_table(body, "Hook")
    if rows is None:
        return bad("README.md 에서 Hook 표를 찾지 못했습니다")
    documented = set()
    for row in rows:
        if not row:
            continue
        documented.update(
            token for token in backtick_tokens(row[0]) if token.endswith(".py")
        )
    settings = repo.json(".claude/settings.json")
    if settings is None:
        return bad(".claude/settings.json 이 없습니다")
    registered = set(_settings_registrations(settings))
    if documented != registered:
        return bad(
            "README Hook 표 = {0}".format(_render(sorted(documented))),
            "settings.json 등록 = {0}".format(_render(sorted(registered))),
            "문서에만 있음: {0}".format(_render(sorted(documented - registered))),
            "등록에만 있음: {0}".format(_render(sorted(registered - documented))),
        )
    return ok("README Hook 표 {0}행 == settings.json 등록".format(len(documented)))


def check_f3(repo: Repo) -> Outcome:
    body = repo.text("README.md")
    if body is None:
        return bad("README.md 가 없습니다")
    rows = markdown_table(body, "허용 도구")
    if rows is None:
        return bad("README.md 에서 Agent 권한 표를 찾지 못했습니다")
    front = repo.agent_frontmatter()
    documented: dict[str, tuple[str, ...]] = {}
    for row in rows:
        if len(row) < 2:
            continue
        name = row[0].strip().lower()
        if name not in AGENT_NAMES:
            continue
        documented[name] = tuple(sorted(backtick_tokens(row[1])))

    problems = []
    evidence = []
    for name in AGENT_NAMES:
        if name not in documented:
            problems.append("{0}: README 권한 표에 행이 없습니다".format(name))
            continue
        if name not in front:
            problems.append("{0}: 정의 파일이 없어 대조할 수 없습니다".format(name))
            continue
        actual = tools_of(front[name], ".claude/agents/{0}.md".format(name))
        if documented[name] != actual:
            problems.append(
                "{0}: README={1} / frontmatter={2}".format(
                    name, _render(documented[name]), _render(actual)
                )
            )
        else:
            evidence.append("{0}: {1}".format(name, _render(actual)))
    if problems:
        return bad(*problems)
    return ok(*evidence)


_GID_RANGE = re.compile(r"G1~G(\d+)")
_GID = re.compile(r'"G(\d+)"')


def check_f4(repo: Repo) -> Outcome:
    gate_source = repo.text(".claude/hooks/guard_stop_gate.py")
    if gate_source is None:
        return bad(".claude/hooks/guard_stop_gate.py 가 없습니다")
    gids = {int(value) for value in _GID.findall(gate_source)}
    if not gids:
        return bad("guard_stop_gate.py 에서 위반 ID 를 찾지 못했습니다")
    actual_max = max(gids)

    claims: dict[str, tuple[int, ...]] = {}
    for relative in ("README.md", "CLAUDE.md"):
        body = repo.text(relative)
        if body is None:
            continue
        values = {int(value) for value in _GID_RANGE.findall(body)}
        if values:
            claims[relative] = tuple(sorted(values))
    if not claims:
        return bad("README.md / CLAUDE.md 에서 `G1~GN` 형태의 주장을 찾지 못했습니다")
    wrong = {name: values for name, values in claims.items() if values != (actual_max,)}
    if wrong:
        return bad(
            "guard_stop_gate.py 의 최대 위반 ID = G{0} (총 {1}개)".format(actual_max, len(gids)),
            *["{0} 주장 = {1}".format(name, _render(["G{0}".format(v) for v in wrong[name]])) for name in sorted(wrong)],
        )
    return ok(
        "guard_stop_gate.py = G1~G{0} ({1}개)".format(actual_max, len(gids)),
        "문서 주장 일치: {0}".format(_render(sorted(claims))),
    )


# ---------------------------------------------------------------------------
# G. Reproducibility & Automation
# ---------------------------------------------------------------------------

# CI 가 실행해야 하는 세 검증기. 역할이 겹치지 않는다.
#   단위(Hook 판정 로직) / 회귀(판정 코드 replay) / 구조(계약 정합성)
CI_COMMANDS = ("pytest evals/tests", "eval_harness.py selftest", "harness_audit.py")


def check_g1(repo: Repo) -> Outcome:
    names = [
        name
        for name in repo.listdir(".github/workflows")
        if name.endswith(".yml") or name.endswith(".yaml")
    ]
    if not names:
        return bad(".github/workflows/ 에 워크플로가 없습니다")
    for name in names:
        body = repo.text(".github/workflows/{0}".format(name))
        if body is None:
            continue
        if all(command in body for command in CI_COMMANDS):
            return ok(
                ".github/workflows/{0} 가 세 검증기를 모두 실행".format(name),
                _render(CI_COMMANDS),
            )
    return bad(
        "세 검증기를 모두 실행하는 워크플로가 없습니다",
        "필요: {0}".format(_render(CI_COMMANDS)),
        "확인한 워크플로: {0}".format(_render(names)),
    )


def check_g2(repo: Repo) -> Outcome:
    problems = []
    for relative in ("uv.lock", ".python-version", "pyproject.toml"):
        if not repo.is_file(relative):
            problems.append("{0} 없음".format(relative))
    if problems:
        return bad(*problems)
    body = repo.text("pyproject.toml")
    try:
        project = tomllib.loads(body or "")
    except tomllib.TOMLDecodeError as error:
        raise AuditError("pyproject.toml: TOML 파싱에 실패했습니다 ({0})".format(error)) from error
    dev = project.get("dependency-groups", {}).get("dev", [])
    if not any(isinstance(item, str) and item.startswith("pytest") for item in dev):
        return bad("pyproject.toml [dependency-groups] dev 에 pytest 선언이 없습니다")
    return ok("uv.lock / .python-version / pyproject.toml dev pytest 선언 확인")


def check_g3(repo: Repo, rubric) -> Outcome:
    """Audit 자기 검증. 테스트 모듈 존재 + rubric 무결성.

    rubric 을 버전 상승 없이 몰래 고치면 여기서 걸린다. 감사 도구가 자기 자신을
    감사하지 못하면 나머지 32개 판정의 근거도 없다.
    """
    problems = []
    if not repo.is_file("evals/tests/test_harness_audit.py"):
        problems.append("evals/tests/test_harness_audit.py 가 없습니다")
    digest = rubric_digest(rubric)
    if digest != RUBRIC_DIGEST:
        problems.append("rubric_digest 불일치: 계산={0} / 핀={1}".format(digest, RUBRIC_DIGEST))
    if problems:
        return bad(*problems)
    return ok(
        "evals/tests/test_harness_audit.py 존재",
        "rubric_digest = {0}".format(digest),
        "rubric_version = {0} / check {1}개".format(RUBRIC_VERSION, len(rubric)),
    )


# ---------------------------------------------------------------------------
# rubric
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckSpec:
    """채점 계약 한 줄. 배점과 Critical 여부는 여기에만 있다."""

    id: str
    category: str
    title: str
    max_score: int
    contract: str
    remediation: str
    run: object

    @property
    def critical(self) -> bool:
        return self.id in CRITICAL_GATES

    @property
    def gate(self) -> str | None:
        return CRITICAL_GATES.get(self.id)


RUBRIC: tuple[CheckSpec, ...] = (
    # A. Agent Role Isolation — 13
    CheckSpec(
        "A1", "agent-isolation", "Agent 정의 4개와 frontmatter 3키 존재", 3,
        "CLAUDE.md §11",
        ".claude/agents/ 에 4개 Agent 정의를 두고 name / description / tools 를 채운다.",
        check_a1,
    ),
    CheckSpec(
        "A2", "agent-isolation", "frontmatter name 집합이 AGENT_TYPES 와 일치", 3,
        "CLAUDE.md §11",
        "Agent 정의의 name 과 _guard_common.AGENT_TYPES 를 같은 집합으로 맞춘다.",
        check_a2,
    ),
    CheckSpec(
        "A3", "agent-isolation", "Agent tools 가 최소 권한 행렬과 일치", 4,
        "CLAUDE.md §11",
        "Agent frontmatter 의 tools 를 최소 권한 행렬대로 되돌린다. 초과 권한이 하나라도 있으면 역할 분리 주장이 거짓이 된다.",
        check_a3,
    ),
    CheckSpec(
        "A4", "agent-isolation", "Agent 정의에 금지 사항 / 종료 전 체크리스트 존재", 3,
        "CLAUDE.md §11",
        "각 Agent 정의에 `## 5. 금지 사항` 과 `## 6. 종료 전 체크리스트` 절을 둔다.",
        check_a4,
    ),
    # B. Guard Registration & Enforcement — 20
    CheckSpec(
        "B1", "guard-enforcement", "Guard 구현 파일과 공통 모듈 존재", 3,
        "CLAUDE.md §22",
        ".claude/hooks/ 에 공통 모듈과 Guard 4종을 둔다.",
        check_b1,
    ),
    CheckSpec(
        "B2", "guard-enforcement", "HOOK_ID 가 파일명 규약과 일치하고 서로 다름", 3,
        "CLAUDE.md §22, §25",
        "각 Guard 의 HOOK_ID 를 파일명의 kebab 변환과 같게 맞춘다. 비활성 스위치가 이 값으로 동작한다.",
        check_b2,
    ),
    CheckSpec(
        "B3", "guard-enforcement", "settings.json 등록 집합이 Guard 파일 집합과 양방향 일치", 8,
        "CLAUDE.md §22",
        "Guard 파일과 settings.json 등록을 1:1 로 맞추고 matcher 를 담당 도구에 맞춘다. 등록되지 않은 Guard 는 전혀 동작하지 않는다.",
        check_b3,
    ),
    CheckSpec(
        "B4", "guard-enforcement", "Stop 훅이 중첩형으로 등록됨", 3,
        "CLAUDE.md §25",
        'settings.json 의 Stop 등록을 `[{"hooks": [...]}]` 중첩형으로 되돌린다. 평면형은 오류 없이 무시된다.',
        check_b4,
    ),
    CheckSpec(
        "B5", "guard-enforcement", "Guard 마다 단위 테스트 모듈 존재", 3,
        "CLAUDE.md §22",
        "evals/tests/ 에 Guard 별 test_<guard>.py 를 둔다.",
        check_b5,
    ),
    # C. Control Contract Consistency — 19
    CheckSpec(
        "C1", "contract-consistency", "실패 원인 분류 5종이 4개 소스에서 일치", 5,
        "CLAUDE.md §14",
        "CLAUDE.md §14 / tester.md / eval_harness.FAILURE_CATEGORIES / dashboard types.ts 의 분류 집합을 같게 맞춘다. 갈라지면 라우팅이 소스마다 달라진다.",
        check_c1,
    ),
    CheckSpec(
        "C2", "contract-consistency", "BLOCKED 사유 코드가 문서와 구현에서 일치", 5,
        "CLAUDE.md §19, §20",
        "patchpilot.md §10 의 사유 코드 목록과 guard_stop_gate.BLOCKED_REASONS 를 같게 맞춘다.",
        check_c2,
    ),
    CheckSpec(
        "C3", "contract-consistency", "고정 테스트 명령이 5개 소스에서 동일", 4,
        "CLAUDE.md §10",
        "CLAUDE.md §10 / tester.md / patchpilot.md / PYTEST_COMMAND / TESTER_PYTEST_TOKENS 의 명령을 한 문자열로 통일한다.",
        check_c3,
    ),
    CheckSpec(
        "C4", "contract-consistency", "retry_budget = 3 이 4개 소스에서 일치", 3,
        "CLAUDE.md §16",
        "CLAUDE.md §16 / patchpilot.md §6 / Scenario.expected_retry_budget / 대표 결과 state.json 의 예산을 같게 맞춘다.",
        check_c4,
    ),
    CheckSpec(
        "C5", "contract-consistency", "기계 판정 첫 줄 토큰이 판정 코드 3곳에서 동일", 2,
        "CLAUDE.md §14, §15",
        "STATUS: PASS / FAIL 과 VERDICT: APPROVED / CHANGES_REQUESTED 이외의 토큰을 판정 코드에서 없앤다.",
        check_c5,
    ),
    # D. Artifact & Evidence Contract — 13
    CheckSpec(
        "D1", "artifact-evidence", "보존된 대표 결과에 state.json 과 report.md 존재", 3,
        "CLAUDE.md §12",
        "reports/examples/ 의 각 실행에 state.json 과 report.md 를 함께 보존한다.",
        check_d1,
    ),
    CheckSpec(
        "D2", "artifact-evidence", "대표 결과 state.json 의 스키마와 enum 유효", 3,
        "CLAUDE.md §19",
        "final_status / blocked_reason / failure_category / retry 값을 계약 안의 값으로 되돌린다.",
        check_d2,
    ),
    CheckSpec(
        "D3", "artifact-evidence", "Stop Gate 불변식 G1~G19 replay 위반 0건", 4,
        "CLAUDE.md §25",
        "대표 결과가 Stop Gate 불변식을 위반한다. 증거를 수정하지 말고 왜 어긋났는지 먼저 규명한다.",
        check_d3,
    ),
    CheckSpec(
        "D4", "artifact-evidence", "대표 결과 eval-result.md 첫 줄이 EVAL: PASS", 2,
        "evals/README.md §8",
        "FAIL 인 실행을 대표 결과로 두지 않는다. 검증에 통과한 실행만 승격한다.",
        check_d4,
    ),
    CheckSpec(
        "D5", "artifact-evidence", "gitignore 가 실행 산출물을 무시하고 대표 결과를 보존", 1,
        "CLAUDE.md §12",
        ".gitignore 에 reports/* 무시와 !reports/examples/** 예외를 함께 둔다.",
        check_d5,
    ),
    # E. Eval Coverage & Replay — 17
    CheckSpec(
        "E1", "eval-coverage", "시나리오 정의의 task 와 install fixture 실재", 4,
        "evals/README.md §12",
        "Scenario 가 가리키는 task 와 fixture 파일을 evals/ 아래에 둔다.",
        check_e1,
    ),
    CheckSpec(
        "E2", "eval-coverage", "회귀 기준 대표 결과가 전부 보존됨", 3,
        "evals/README.md §10",
        "REGRESSION_EXAMPLES 의 각 항목을 reports/examples/ 로 승격한다.",
        check_e2,
    ),
    CheckSpec(
        "E3", "eval-coverage", "eval-result.md 의 종합 수치와 표 행 수가 일치", 2,
        "evals/README.md §8",
        "eval-result.md 를 손으로 고치지 않는다. eval_harness 가 쓴 원본을 그대로 보존한다.",
        check_e3,
    ),
    CheckSpec(
        "E4a", "eval-coverage", "검증된 종료 경로가 4개 이상", 2,
        "CLAUDE.md §20",
        "결정론적 eval 로 검증된 종료 경로를 4개 이상으로 만든다.",
        check_e4a,
    ),
    CheckSpec(
        "E4b", "eval-coverage", "종료 경로 7개 전부에 결정론적 eval 존재", 2,
        "CLAUDE.md §20",
        "TEST_DEFECT / UNKNOWN 2회 / Reviewer CHANGES_REQUESTED 경로의 eval 시나리오를 추가한다.",
        check_e4b,
    ),
    CheckSpec(
        "E5", "eval-coverage", "시나리오가 참조하는 결함 모듈이 전부 존재", 2,
        "evals/README.md §11",
        "Scenario 가 참조하는 fault id 마다 evals/faults/<id>.py 를 둔다.",
        check_e5,
    ),
    CheckSpec(
        "E6", "eval-coverage", "연쇄 주입 시나리오의 결함이 서로 다름", 2,
        "evals/README.md §3-12",
        "같은 결함을 반복 주입하지 않는다. fault_sequence 항목을 서로 다르게 만든다.",
        check_e6,
    ),
    # F. Documentation Consistency — 10
    CheckSpec(
        "F1", "doc-consistency", "CLAUDE.md §22 완료 항목이 지목하는 파일 실재", 3,
        "CLAUDE.md §22",
        "§22 의 `[x]` 항목이 가리키는 파일을 실제로 두거나, 구현되지 않았다면 `[ ]` 로 되돌린다.",
        check_f1,
    ),
    CheckSpec(
        "F2", "doc-consistency", "README Hook 표가 settings.json 등록과 일치", 3,
        "CLAUDE.md §22",
        "README 의 Hook 표를 실제 등록 집합과 같게 맞춘다.",
        check_f2,
    ),
    CheckSpec(
        "F3", "doc-consistency", "README 권한 표가 Agent frontmatter 와 일치", 2,
        "CLAUDE.md §11",
        "README 의 Agent 권한 표를 frontmatter 의 tools 와 같게 맞춘다.",
        check_f3,
    ),
    CheckSpec(
        "F4", "doc-consistency", "문서의 Stop Gate 불변식 개수 주장이 구현과 일치", 2,
        "CLAUDE.md §25",
        "문서의 `G1~GN` 주장을 guard_stop_gate.py 의 실제 위반 ID 수와 맞춘다.",
        check_f4,
    ),
    # G. Reproducibility & Automation — 8
    CheckSpec(
        "G1", "automation", "CI 워크플로가 세 검증기를 모두 실행", 4,
        "CLAUDE.md §22",
        ".github/workflows/ 에 단위 테스트 / selftest / audit 을 모두 실행하는 워크플로를 추가한다.",
        check_g1,
    ),
    CheckSpec(
        "G2", "automation", "uv 잠금 파일과 Python 버전 고정", 2,
        "CLAUDE.md §24",
        "uv.lock 과 .python-version 을 커밋하고 pyproject.toml dev 그룹에 pytest 를 선언한다.",
        check_g2,
    ),
    CheckSpec(
        "G3", "automation", "Audit 자기 검증 테스트와 rubric 무결성", 2,
        "CLAUDE.md §22",
        "rubric 을 바꿨다면 RUBRIC_VERSION 과 RUBRIC_DIGEST 를 함께 갱신한다.",
        check_g3,
    ),
)


def rubric_digest(rubric: tuple[CheckSpec, ...] = RUBRIC) -> str:
    """`sorted((check_id, max_score, is_critical))` 의 sha256.

    선언 순서를 바꿔도 값이 변하지 않는다. 배점이나 Critical 여부를 바꾸면 변한다.
    """
    payload = "\n".join(
        "{0}|{1}|{2}".format(spec.id, spec.max_score, 1 if spec.critical else 0)
        for spec in sorted(rubric, key=lambda item: item.id)
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def _warnings(repo: Repo) -> list[dict]:
    """점수와 verdict 에 영향을 주지 않는 관측치. 항상 같은 순서로 만든다."""
    notes: list[dict] = []
    harness = repo.eval_harness()
    if harness is None:
        return notes

    covered, problems = _covered_routes(repo)
    if not problems:
        missing = sorted({route for route, _kind, _value in TERMINAL_ROUTES} - covered)
        if missing:
            notes.append(
                {
                    "id": "W-EVAL-ROUTES",
                    "summary": "결정론적 eval 이 없는 종료 경로 {0}개".format(len(missing)),
                    "detail": missing,
                }
            )

    referenced = {
        fault_id
        for scenario in harness.SCENARIOS.values()
        for fault_id in scenario.fault_ids
    }
    on_disk = {
        name[: -len(".py")]
        for name in repo.listdir("evals/faults")
        if name.endswith(".py") and not name.startswith("_")
    }
    orphan = sorted(on_disk - referenced)
    if orphan:
        notes.append(
            {
                "id": "W-FAULT-ORPHAN",
                "summary": "어떤 시나리오도 참조하지 않는 결함 모듈 {0}개".format(len(orphan)),
                "detail": orphan,
            }
        )
    return notes


def run_audit(root, rubric: tuple[CheckSpec, ...] = RUBRIC) -> dict:
    """감사를 수행하고 JSON 직렬화 가능한 결과를 돌려준다.

    파일을 하나도 쓰지 않는다. 시각·난수·git·네트워크에 의존하지 않으므로 같은
    저장소 상태면 항상 같은 결과다.
    """
    repo = Repo(Path(root))

    results: dict[str, dict] = {}
    for spec in rubric:
        outcome = spec.run(repo, rubric) if spec.id == "G3" else spec.run(repo)
        results[spec.id] = {
            "id": spec.id,
            "title": spec.title,
            "result": RESULT_PASS if outcome.passed else RESULT_FAIL,
            "score": spec.max_score if outcome.passed else 0,
            "max_score": spec.max_score,
            "critical": spec.critical,
            "contract": spec.contract,
            "evidence": list(outcome.evidence),
            "remediation": spec.remediation,
        }

    by_category: dict[str, list[CheckSpec]] = {}
    for spec in rubric:
        by_category.setdefault(spec.category, []).append(spec)

    categories = []
    for category_id, title in CATEGORIES:
        specs = sorted(by_category.get(category_id, []), key=lambda item: item.id)
        checks = [results[spec.id] for spec in specs]
        categories.append(
            {
                "id": category_id,
                "title": title,
                "score": sum(check["score"] for check in checks),
                "max_score": sum(check["max_score"] for check in checks),
                "checks": checks,
            }
        )

    score = sum(category["score"] for category in categories)
    max_score = sum(category["max_score"] for category in categories)

    failing = [spec for spec in rubric if results[spec.id]["result"] == RESULT_FAIL]
    critical_failures = [
        {
            "gate": spec.gate,
            "check_id": spec.id,
            "summary": spec.title,
            "evidence": results[spec.id]["evidence"],
        }
        for spec in sorted(
            (item for item in failing if item.critical), key=lambda item: item.id
        )
    ]
    next_actions = [
        {
            "check_id": spec.id,
            "category": spec.category,
            "critical": spec.critical,
            "max_score": spec.max_score,
            "action": spec.remediation,
        }
        # Critical 우선, 그다음 배점 큰 순, 마지막은 id 순. 동점에 삽입 순서가
        # 섞이지 않도록 세 키를 모두 명시한다.
        for spec in sorted(
            failing, key=lambda item: (not item.critical, -item.max_score, item.id)
        )
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "audit_version": AUDIT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "rubric_digest": rubric_digest(rubric),
        "verdict": VERDICT_FAIL if critical_failures else VERDICT_PASS,
        "score": score,
        "max_score": max_score,
        "categories": categories,
        "critical_failures": critical_failures,
        "warnings": _warnings(repo),
        "next_actions": next_actions,
    }


def to_json(report: dict) -> str:
    """결정론적 JSON 문자열. 같은 입력이면 바이트까지 같다."""
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


# ---------------------------------------------------------------------------
# 사람이 읽는 렌더링
#
# 렌더러는 `run_audit()` 결과를 **표현만** 한다. 점수·verdict·정렬 순서를 새로
# 계산하지 않는다. 렌더러가 판정을 한 번이라도 하면 JSON 과 text 가 서로 다른
# 결론을 낼 수 있고, 그 순간 어느 쪽이 정본인지 알 수 없게 된다.
# ---------------------------------------------------------------------------

# 감사 범위 밖. 이 목록이 없으면 "94/100" 을 "Harness 가 94% 옳다" 로 오독한다.
# 점수는 정지 상태 계약의 정합성이지 Harness 의 효과가 아니다.
NOT_AUDITED = (
    "Agent 의 실시간 행위. `PreToolUse` / `Stop` Hook 의 담당이다.",
    "Harness 실행의 상태 전이. `evals/eval_harness.py` 의 담당이다.",
    "`sample-project/` 의 애플리케이션 코드 품질. 감사 대상은 Harness 다.",
    "LLM 출력의 내용적 타당성. 기계로 증명할 수 없는 판단은 채점하지 않는다.",
    "git 상태와 커밋 이력.",
    "계획 범위와 실제 diff 의 대조. 오탐 위험 때문에 Stop Gate 도 검사하지 않는다.",
    "점수가 높다는 사실 자체. 계약이 정합적이라는 것과 Harness 가 유효하다는 것은 다르다.",
)


def _failing_checks(report: dict) -> list[dict]:
    """FAIL 인 check. category 순서와 id 순서를 그대로 따르므로 항상 같은 순서다."""
    return [
        check
        for category in report["categories"]
        for check in category["checks"]
        if check["result"] == RESULT_FAIL
    ]


def _min_score_note(report: dict, min_score: int | None) -> str | None:
    if min_score is None:
        return None
    met = "충족" if report["score"] >= min_score else "미달"
    return "{0} 이상 요구 - {1} (score {2})".format(min_score, met, report["score"])


def to_text(report: dict, min_score: int | None = None) -> str:
    """터미널용 요약. 첫 줄은 기계 판정 토큰이다."""
    lines = [
        "AUDIT: {0}".format(report["verdict"]),
        "",
        "Score: {0} / {1}".format(report["score"], report["max_score"]),
        "Critical: {0}".format(len(report["critical_failures"])),
        "Rubric: {0}".format(report["rubric_version"]),
        "Digest: {0}".format(report["rubric_digest"]),
    ]
    note = _min_score_note(report, min_score)
    if note is not None:
        lines.append("Min score: {0}".format(note))

    lines.extend(["", "Category:"])
    for category in report["categories"]:
        lines.append(
            "- {0}: {1}/{2}".format(
                category["title"], category["score"], category["max_score"]
            )
        )

    if report["critical_failures"]:
        lines.extend(["", "Critical hard gate:"])
        for failure in report["critical_failures"]:
            lines.append(
                "- [{0}] {1} {2}".format(
                    failure["gate"], failure["check_id"], failure["summary"]
                )
            )
            for evidence in failure["evidence"]:
                lines.append("    {0}".format(evidence))

    failures = _failing_checks(report)
    lines.append("")
    if failures:
        lines.append("Failures:")
        for check in failures:
            lines.append(
                "- {0} ({1}점{2}) {3}".format(
                    check["id"],
                    check["max_score"],
                    ", Critical" if check["critical"] else "",
                    check["title"],
                )
            )
            for evidence in check["evidence"]:
                lines.append("    {0}".format(evidence))
    else:
        lines.append("Failures: 없음")

    lines.append("")
    if report["next_actions"]:
        lines.append("Next actions:")
        for index, action in enumerate(report["next_actions"], start=1):
            lines.append(
                "{0}. {1} ({2}점{3}) {4}".format(
                    index,
                    action["check_id"],
                    action["max_score"],
                    ", Critical" if action["critical"] else "",
                    action["action"],
                )
            )
    else:
        lines.append("Next actions: 없음")

    if report["warnings"]:
        lines.extend(["", "Warnings (점수 미반영):"])
        for warning in report["warnings"]:
            lines.append("- {0}: {1}".format(warning["id"], warning["summary"]))
            for item in warning["detail"]:
                lines.append("    {0}".format(item))

    return "\n".join(lines) + "\n"


def to_markdown(report: dict, min_score: int | None = None) -> str:
    """보존용 Markdown. 첫 줄은 text 와 같은 기계 판정 토큰이다.

    증거 문자열에는 `|` 가 들어갈 수 있으므로 증거는 표가 아니라 목록으로 낸다.
    """
    lines = ["AUDIT: {0}".format(report["verdict"]), "", "# PatchPilot Harness Audit", ""]

    rows = [
        ("Verdict", report["verdict"]),
        ("Score", "{0} / {1}".format(report["score"], report["max_score"])),
        ("Critical", str(len(report["critical_failures"]))),
        ("schema_version", str(report["schema_version"])),
        ("audit_version", report["audit_version"]),
        ("rubric_version", report["rubric_version"]),
        ("rubric_digest", "`{0}`".format(report["rubric_digest"])),
    ]
    note = _min_score_note(report, min_score)
    if note is not None:
        rows.append(("min_score", note))

    lines.extend(["## 종합", "", "| 항목 | 값 |", "| --- | --- |"])
    lines.extend("| {0} | {1} |".format(label, value) for label, value in rows)

    lines.extend(["", "## Critical Hard Gate", ""])
    if report["critical_failures"]:
        for failure in report["critical_failures"]:
            lines.append(
                "- **{0}** - `{1}` {2}".format(
                    failure["gate"], failure["check_id"], failure["summary"]
                )
            )
            lines.extend("  - {0}".format(item) for item in failure["evidence"])
    else:
        lines.append("Critical 실패 없음. Hard Gate 를 통과했다.")

    lines.extend(
        ["", "## Category 요약", "", "| Category | 점수 | 실패 check |", "| --- | --- | --- |"]
    )
    for category in report["categories"]:
        failed = [
            check["id"] for check in category["checks"] if check["result"] == RESULT_FAIL
        ]
        lines.append(
            "| {0} | {1} / {2} | {3} |".format(
                category["title"],
                category["score"],
                category["max_score"],
                ", ".join(failed) if failed else "-",
            )
        )

    lines.extend(["", "## Check 상세"])
    for category in report["categories"]:
        lines.extend(["", "### {0}".format(category["title"])])
        for check in category["checks"]:
            lines.extend(
                [
                    "",
                    "#### {0} - {1} ({2}/{3}){4}".format(
                        check["id"],
                        check["result"],
                        check["score"],
                        check["max_score"],
                        " **Critical**" if check["critical"] else "",
                    ),
                    "",
                    check["title"],
                    "",
                    "- 계약: {0}".format(check["contract"]),
                    "- 근거:",
                ]
            )
            lines.extend("  - {0}".format(item) for item in check["evidence"])
            if check["result"] == RESULT_FAIL:
                lines.append("- 조치: {0}".format(check["remediation"]))

    lines.extend(["", "## 다음 행동", ""])
    if report["next_actions"]:
        for index, action in enumerate(report["next_actions"], start=1):
            lines.append(
                "{0}. `{1}` ({2}점{3}) - {4}".format(
                    index,
                    action["check_id"],
                    action["max_score"],
                    ", Critical" if action["critical"] else "",
                    action["action"],
                )
            )
    else:
        lines.append("없음.")

    lines.extend(["", "## 경고 (점수 미반영)", ""])
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append("- **{0}** {1}".format(warning["id"], warning["summary"]))
            lines.extend("  - {0}".format(item) for item in warning["detail"])
    else:
        lines.append("없음.")

    lines.extend(["", "## Audit이 검사하지 않는 것", ""])
    lines.extend("- {0}".format(item) for item in NOT_AUDITED)

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
#
# 엔진 위의 얇은 층이다. 하는 일은 넷뿐이다.
#   인자 해석 / `run_audit()` 호출 / 렌더링 / 종료 코드 결정
#
# 종료 코드 계약 (CI 가 의존한다)
#   0 - Audit PASS
#   1 - Audit FAIL (Critical 존재, 또는 --min-score 미달)
#   2 - Audit 을 수행하지 못함 (AuditError / 인자 오류 / 쓰기 실패)
#
# 1 과 2 를 섞으면 CI 가 "감사 도구 고장" 을 "감사 결과 불합격" 으로 오독한다.
# 반대 방향이 더 위험하다. 예외가 그대로 새어 나가면 Python 기본 종료 코드가 1 이라
# 고장이 정상적인 FAIL 로 보인다. 그래서 예상하지 못한 예외까지 2 로 눌러 담는다.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

FORMAT_TEXT = "text"
FORMAT_JSON = "json"
FORMAT_MARKDOWN = "markdown"
FORMATS = (FORMAT_TEXT, FORMAT_JSON, FORMAT_MARKDOWN)

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2

# 대표 결과. 날짜별 파일을 남기지 않는다. 이력은 git 이 이미 갖고 있고,
# 파일을 쌓으면 "어느 것이 현재인가" 라는 질문이 새로 생긴다.
AUDIT_DIR = "reports/audit"
LATEST_JSON = "reports/audit/latest.json"
LATEST_MARKDOWN = "reports/audit/latest.md"


def apply_min_score(report: dict, min_score: int | None) -> dict:
    """`--min-score` 미달을 verdict 에만 반영한 사본.

    `critical_failures` 는 **건드리지 않는다.** 임계값은 호출자의 기준이지 Hard
    Gate 가 아니다. 미달을 Critical 로 위장하면 "거짓말이면 Critical" 이라는
    rubric 의 기준선이 무너지고, 점수 임계값 하나로 게이트 목록이 오염된다.
    """
    if min_score is None or report["score"] >= min_score:
        return report
    if report["verdict"] == VERDICT_FAIL:
        return report
    lowered = dict(report)
    lowered["verdict"] = VERDICT_FAIL
    return lowered


def render(report: dict, output_format: str, min_score: int | None = None) -> str:
    if output_format == FORMAT_JSON:
        return to_json(report)
    if output_format == FORMAT_MARKDOWN:
        return to_markdown(report, min_score)
    return to_text(report, min_score)


def write_representative(root, report: dict, min_score: int | None = None) -> list[str]:
    """대표 결과 두 파일을 갱신한다. 하나라도 실패하면 `AuditError`.

    두 본문을 먼저 전부 만든 뒤에 쓴다. 쓰기가 실패하면 조용히 넘기지 않고 실행
    오류로 올린다. 반쯤 갱신된 대표 결과를 PASS 로 끝내면 그 파일이 저장소의 현재
    상태를 잘못 증언하게 된다.
    """
    bodies = (
        (LATEST_JSON, to_json(report)),
        (LATEST_MARKDOWN, to_markdown(report, min_score)),
    )
    base = Path(root)
    try:
        base.joinpath(*AUDIT_DIR.split("/")).mkdir(parents=True, exist_ok=True)
        for relative, body in bodies:
            base.joinpath(*relative.split("/")).write_text(body, encoding="utf-8")
    except OSError as error:
        raise AuditError(
            "대표 결과를 쓰지 못했습니다 ({0}: {1})".format(type(error).__name__, error)
        ) from error
    return [relative for relative, _body in bodies]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness_audit.py",
        description="PatchPilot Harness 의 정지 상태 통제 계약을 결정론적으로 채점한다",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        default=FORMAT_TEXT,
        choices=FORMATS,
        help="출력 형식 (기본값: {0})".format(FORMAT_TEXT),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="감사 대상 저장소 루트 (기본값: 이 파일이 속한 저장소)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="{0} 와 {1} 를 갱신한다".format(LATEST_JSON, LATEST_MARKDOWN),
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        metavar="N",
        help="score 가 N 미만이면 verdict 를 FAIL 로 내리고 1 로 종료한다",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        # `--help` 는 0, 인자 오류는 argparse 규약대로 2. 어느 쪽이든 예외를 그대로
        # 통과시키지 않고 반환값으로 옮겨서 main() 하나로 종료 코드를 결정한다.
        return int(error.code or EXIT_PASS)

    try:
        report = apply_min_score(run_audit(args.root), args.min_score)
        rendered = render(report, args.output_format, args.min_score)
        written = write_representative(args.root, report, args.min_score) if args.write else []
    except AuditError as error:
        print("ERROR: {0}".format(error), file=sys.stderr)
        return EXIT_ERROR
    except Exception:  # noqa: BLE001 - 예상 못 한 예외도 "감사 실패" 이지 FAIL 이 아니다
        traceback.print_exc()
        print("ERROR: Audit 실행 중 예상하지 못한 예외가 발생했습니다", file=sys.stderr)
        return EXIT_ERROR

    # JSON 은 stdout 을 독점한다. 진단 문구는 전부 stderr 로 보낸다.
    print(rendered, end="")
    for relative in written:
        print("wrote {0}".format(relative), file=sys.stderr)

    return EXIT_PASS if report["verdict"] == VERDICT_PASS else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
