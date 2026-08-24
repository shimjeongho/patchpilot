"""훅의 가정이 Harness 실제 자산과 일치하는지 검증한다.

두 가지 불변식을 지킨다.

1. 훅의 `plan.md` 파서가 `evals/eval_harness.py` 의 파서와 완전히 같은 결과를 낸다.
   `eval_harness.py` 를 리팩터링하지 않기 위해 파서를 따로 구현했으므로, 분기 위험은
   이 테스트로만 막을 수 있다.
2. 훅의 `AGENT_TYPES` 가 `.claude/agents/*.md` 의 frontmatter `name:` 집합과 같다.
   Agent 가 추가·삭제·개명되면 "알 수 없는 주체는 차단" 정책의 전제가 깨진다.
"""

import re

import pytest

_FRONTMATTER_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def _corpus(repo_root):
    """보존된 대표 결과와 로컬 run 의 plan 문서를 모두 모은다."""
    paths = sorted(repo_root.glob("reports/examples/*/plan*.md"))
    paths += sorted(repo_root.glob("reports/RUN-*/plan.md"))
    return paths


def test_corpus_is_not_empty(repo_root):
    """코퍼스가 비면 파서 일치 테스트가 조용히 0건 통과한다."""
    assert _corpus(repo_root), "plan 문서 코퍼스가 비어 있다"


def test_hook_parser_matches_eval_harness(repo_root, guard_common, eval_harness):
    for path in _corpus(repo_root):
        text = path.read_text(encoding="utf-8")
        expected = eval_harness.plan_allowed_files(text)
        actual = guard_common.plan_allowed_files(text)
        assert actual == expected, path.relative_to(repo_root).as_posix()


def test_corpus_contains_a_non_empty_allowlist(repo_root, guard_common):
    """코퍼스가 모두 빈 목록이면 일치 테스트가 사실상 아무것도 검증하지 않는다."""
    parsed = [guard_common.plan_allowed_files(p.read_text(encoding="utf-8")) for p in _corpus(repo_root)]
    assert any(parsed), "코퍼스의 모든 plan 문서에서 허용 목록이 비어 있다"


# --------------------------------------------------------------------------
# 파서 규칙 — 두 구현이 같은 규칙을 따르는지 합성 입력으로도 확인한다
# --------------------------------------------------------------------------

_PROSE_ONLY = """# Plan

## 7. 수정 허용 파일 목록

산문에 `sample-project/src/prose.py` 를 언급하지만 목록 항목이 아니다.

## 8. 구현 단계
"""

_STOPS_AT_NEXT_HEADING = """# Plan

## 7. 수정 허용 파일 목록
- `sample-project/src/inside.py`

## 8. 구현 단계
- `sample-project/src/outside.py`
"""

_DEDUPES_AND_KEEPS_ORDER = """# Plan

## 7. 수정 허용 파일 목록
- `sample-project/src/b.py`
- `sample-project/src/a.py`
* `sample-project/src/b.py`
"""

_IGNORES_PATHS_OUTSIDE_SAMPLE_PROJECT = """# Plan

## 7. 수정 허용 파일 목록
- `sample-project/src/a.py`
- `evals/eval_harness.py`
- `CLAUDE.md`
"""

_EARLIER_SECTION_IS_NOT_READ = """# Plan

## 6. 실제 코드에서 확인한 근거
- `sample-project/src/evidence.py:42`

## 7. 수정 허용 파일 목록
- `sample-project/src/target.py`
"""


@pytest.mark.parametrize(
    "text, expected",
    [
        (_PROSE_ONLY, []),
        (_STOPS_AT_NEXT_HEADING, ["sample-project/src/inside.py"]),
        (_DEDUPES_AND_KEEPS_ORDER, ["sample-project/src/b.py", "sample-project/src/a.py"]),
        (_IGNORES_PATHS_OUTSIDE_SAMPLE_PROJECT, ["sample-project/src/a.py"]),
        (_EARLIER_SECTION_IS_NOT_READ, ["sample-project/src/target.py"]),
    ],
)
def test_parser_rules_agree_on_synthetic_documents(guard_common, eval_harness, text, expected):
    assert guard_common.plan_allowed_files(text) == expected
    assert eval_harness.plan_allowed_files(text) == expected


def test_allowlist_lookup_requires_exact_match(guard_common):
    lookup = guard_common.allowed_lookup(["sample-project/src/expense/service_charge.py"])
    assert guard_common.matches_allowed(
        ("sample-project", "src", "expense", "service_charge.py"), lookup
    )
    assert not guard_common.matches_allowed(
        ("sample-project", "src", "expense", "service_charge.py.bak"), lookup
    )
    assert not guard_common.matches_allowed(("sample-project", "src", "expense"), lookup)


def test_allowlist_lookup_drops_traversal_entries(guard_common):
    """계획 문서도 저장소 안의 텍스트일 뿐이므로 경로를 그대로 믿지 않는다."""
    lookup = guard_common.allowed_lookup(["sample-project/../secrets.txt", "sample-project/ok.py"])
    assert lookup == {("sample-project", "ok.py")}


# --------------------------------------------------------------------------
# AGENT_TYPES 불변식
# --------------------------------------------------------------------------


def test_agent_types_match_the_agent_definition_files(repo_root, guard_common):
    agent_dir = repo_root / ".claude" / "agents"
    names = set()
    for path in sorted(agent_dir.glob("*.md")):
        match = _FRONTMATTER_NAME.search(path.read_text(encoding="utf-8"))
        assert match is not None, path.name + " 에 frontmatter name 이 없다"
        names.add(match.group(1))

    assert names == set(guard_common.AGENT_TYPES)


def test_agent_file_name_matches_its_declared_name(repo_root):
    """payload 의 agent_type 은 파일 이름이 아니라 frontmatter name 과 같다."""
    agent_dir = repo_root / ".claude" / "agents"
    for path in sorted(agent_dir.glob("*.md")):
        match = _FRONTMATTER_NAME.search(path.read_text(encoding="utf-8"))
        assert match is not None
        assert match.group(1) == path.stem
