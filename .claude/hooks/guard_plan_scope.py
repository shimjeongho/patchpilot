"""PreToolUse 가드 — `plan.md` 수정 허용 파일 목록 집행.

`CLAUDE.md §3-2` 는 계획에 없는 파일을 수정하지 못하게 한다. Planner 가 쓴
`plan.md` 의 "수정 허용 파일 목록" 이 Developer 의 화이트리스트이며, 이 가드는
Developer 가 실제로 파일을 쓰는 시점에 그 목록을 집행한다.

`patchpilot.md §2` 는 Planner 직후에 같은 목록을 검사한다(`PLAN_SCOPE_VIOLATION`).
이 가드는 그 검사를 대체하지 않고 쓰기 시점의 두 번째 층으로 동작한다.

담당 범위는 `sample-project/` 하위 중 `sample-project/tests/` 를 뺀 나머지다.
테스트 경로는 `guard_test_files.py` 가 담당하므로 두 가드는 겹치지 않는다.
`reports/` 는 담당 범위가 아니다. Developer 가 `change-log-N.md` 에 사유를 적고
중단하는 경로를 막으면 규칙이 지시하는 다음 행동 자체가 불가능해진다.

종료 코드: 0 = 허용, 2 = 차단.
"""

import sys
from pathlib import Path

# 훅은 패키지가 아니라 단독 스크립트로 실행되므로 형제 모듈을 경로로 찾는다.
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _guard_common as common  # noqa: E402

HOOK_ID = "guard-plan-scope"


def _warning(text: str) -> str:
    return "[" + HOOK_ID + "] 경고: " + text + " - 검사를 건너뜁니다"


def _reason_lines(who: object) -> list[str]:
    """차단 근거. 주체마다 위반하는 규칙이 다르므로 구분해서 적는다."""
    if who == "developer":
        return [
            "CLAUDE.md §3-2 (계획에 없는 파일은 임의로 수정하지 않는다)",
            "CLAUDE.md §17 (최소 변경 원칙)",
        ]
    if who is None:
        return [
            "CLAUDE.md §19 (Orchestrator - 제품 코드를 수정하지 않는다)",
            "patchpilot.md §0-1 (코드 수정은 Developer 만 수행한다)",
        ]
    if who in common.AGENT_TYPES:
        return [
            "CLAUDE.md §11 ({0} - 제품 코드 수정 금지)".format(who),
            "제품 코드를 수정할 수 있는 것은 Developer 뿐이다.",
        ]
    return [
        "알 수 없는 주체다. 제품 코드를 수정할 수 있는 것은 Developer 뿐이다.",
        "CLAUDE.md §11 (Agent별 수정 권한)",
    ]


def _block_message(
    payload: dict,
    target: str,
    run_name: str,
    who: object,
    allowed: list[str] | None,
) -> str:
    lines = [
        "[" + HOOK_ID + "] 차단: 계획 허용 목록 밖 파일 쓰기",
        "  대상  : " + target,
        "  행위자: " + common.actor_label(payload),
        "  실행  : " + run_name,
    ]

    # None = 참조할 계획이 없다, 빈 목록 = 계획과 무관하게 권한이 없다.
    if allowed is None:
        lines.append("  허용 목록: 활성 run 이 없어 참조할 계획이 없다")
    elif not allowed:
        lines.append("  허용 목록: 이 주체는 제품 코드 수정 권한 자체가 없다")
    else:
        lines.append("  허용 목록 (plan.md §7. 수정 허용 파일 목록):")
        lines.extend("    - " + entry for entry in allowed)

    lines.append("")
    lines.append("  근거  :")
    lines.extend("    " + reason for reason in _reason_lines(who))
    lines.extend(
        [
            "",
            "  다음 행동:",
            "    이 파일을 고쳐야 한다고 판단되면 수정하지 말고, 그 이유를",
            "    reports/<run-id>/change-log-N.md 에 기록하고 중단하라. (developer.md §3)",
            "    계획 범위 자체가 틀렸다면 Tester 가 PLAN_DEFECT 로 분류하고",
            "    Orchestrator 가 Planner 를 재호출한다. (CLAUDE.md §20)",
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

    if not common.is_under(parts, common.SAMPLE_PROJECT):
        return common.ALLOW, None
    if common.is_under(parts, common.SAMPLE_TESTS):
        # 테스트 경로는 guard_test_files.py 담당이다.
        return common.ALLOW, None

    target = common.to_posix(parts)
    who = common.actor(payload)
    run_dir, ambiguity = common.find_active_run(root)
    if ambiguity is not None:
        return common.ALLOW, _warning(ambiguity)

    if who is None:
        # 메인 세션. PatchPilot 실행 중일 때만 막는다.
        if run_dir is None:
            return common.ALLOW, None
        return common.BLOCK, _block_message(payload, target, run_dir.name, who, [])

    if who != "developer":
        run_name = run_dir.name if run_dir is not None else "활성 run 없음"
        return common.BLOCK, _block_message(payload, target, run_name, who, [])

    if run_dir is None:
        # Developer 는 PatchPilot 실행 밖에서 제품 코드를 고칠 이유가 없다.
        return common.BLOCK, _block_message(payload, target, "활성 run 없음", who, None)

    plan_file = run_dir / "plan.md"
    try:
        plan_text = plan_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return common.ALLOW, _warning(
            "{0}/plan.md 를 읽지 못했습니다 ({1})".format(run_dir.name, type(error).__name__)
        )

    allowed = common.plan_allowed_files(plan_text)
    if not allowed:
        # 여기까지 왔다는 것은 patchpilot.md §2 의 PLAN_INCOMPLETE 검사가
        # 놓쳤다는 뜻이다. 서식 문제로 실행 전체를 죽이지 않고 통과시키되,
        # 검사를 건너뛴 사실은 반드시 남긴다.
        return common.ALLOW, _warning(
            "{0}/plan.md 에서 수정 허용 파일 목록을 읽지 못했습니다".format(run_dir.name)
        )

    if common.matches_allowed(parts, common.allowed_lookup(allowed)):
        return common.ALLOW, None

    return common.BLOCK, _block_message(payload, target, run_dir.name, who, allowed)


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
