"""PreToolUse 가드 — `sample-project/tests/` 쓰기 권한 집행.

`CLAUDE.md §21` 에 따라 회귀 테스트를 추가할 권한은 Tester 에게만 있다.
Developer·Planner·Reviewer 는 테스트 파일을 쓸 수 없고(`CLAUDE.md §11`),
Orchestrator 도 마찬가지다(`CLAUDE.md §19`).

담당 범위는 `sample-project/tests/` 하위뿐이다. 그 밖의 경로는 판단하지 않는다.
`sample-project/` 의 나머지는 `guard_plan_scope.py` 가 담당하므로 두 가드의
담당 경로는 서로 겹치지 않는다.

종료 코드: 0 = 허용, 2 = 차단.
"""

import sys
from pathlib import Path

# 훅은 패키지가 아니라 단독 스크립트로 실행되므로 형제 모듈을 경로로 찾는다.
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _guard_common as common  # noqa: E402

HOOK_ID = "guard-test-files"


def _reason_lines(who: object) -> list[str]:
    """차단 근거. 주체마다 위반하는 규칙이 다르므로 구분해서 적는다."""
    if who == "developer":
        first = "CLAUDE.md §11 (Developer - 테스트 파일 수정 금지)"
    elif who == "planner":
        first = "CLAUDE.md §11 (Planner - 제품 코드 및 테스트 코드 수정 금지)"
    elif who == "reviewer":
        first = "CLAUDE.md §11 (Reviewer - 코드 수정 금지)"
    elif who is None:
        first = "CLAUDE.md §19 (Orchestrator - 테스트 파일도 수정하지 않는다)"
    else:
        first = "알 수 없는 주체다. 테스트 쓰기 권한을 가진 것은 Tester 뿐이다."
    return [
        first,
        "CLAUDE.md §3-3 (테스트를 통과시키기 위해 테스트를 약화시키지 않는다)",
        "CLAUDE.md §21 (회귀 테스트 추가 권한은 Tester 에게만 있다)",
    ]


def _block_message(payload: dict, target: str, run_name: str, who: object) -> str:
    lines = [
        "[" + HOOK_ID + "] 차단: 테스트 파일 쓰기 권한 없음",
        "  대상  : " + target,
        "  행위자: " + common.actor_label(payload),
        "  실행  : " + run_name,
        "",
        "  근거  :",
    ]
    lines.extend("    " + reason for reason in _reason_lines(who))
    lines.extend(
        [
            "",
            "  다음 행동:",
            "    테스트가 잘못됐다고 판단되면 고치지 말고, 그 사유를",
            "    reports/<run-id>/change-log-N.md 에 기록하고 중단하라. (developer.md §3)",
            "    Tester 가 TEST_DEFECT 로 분류하면 Orchestrator 가 BLOCKED 로 처리한다. (CLAUDE.md §20)",
        ]
    )
    return "\n".join(lines)


def decide(payload: dict, root: Path) -> tuple[int, str | None]:
    """(종료 코드, stderr 메시지) 를 돌려주는 순수 판정 함수.

    파일을 쓰지 않고 시각·난수에 의존하지 않는다. 같은 입력이면 항상 같은 결과다.
    """
    if common.is_disabled(HOOK_ID):
        return common.ALLOW, common.disabled_notice(HOOK_ID)

    file_path = common.target_path(payload)
    if file_path is None:
        return common.ALLOW, None

    parts = common.relative_parts(file_path, root)
    if parts is None:
        return common.ALLOW, None

    if not common.is_under(parts, common.SAMPLE_TESTS):
        return common.ALLOW, None

    who = common.actor(payload)
    if who == "tester":
        return common.ALLOW, None

    run_dir, ambiguity = common.find_active_run(root)

    if who is None:
        # 메인 세션. PatchPilot 실행 중일 때만 막는다. 실행 밖의 일반 저장소 작업까지
        # 막으면 훅이 Harness 개발 자체를 방해한다.
        if ambiguity is not None:
            return common.ALLOW, "[" + HOOK_ID + "] 경고: " + ambiguity + " - 검사를 건너뜁니다"
        if run_dir is None:
            return common.ALLOW, None

    target = common.to_posix(parts)
    run_name = run_dir.name if run_dir is not None else "활성 run 없음"
    return common.BLOCK, _block_message(payload, target, run_name, who)


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
