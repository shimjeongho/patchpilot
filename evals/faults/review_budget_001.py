"""Reviewer 지적으로 예산이 소진되는 경로 검증용 1차 결함 정의 (review_budget_001).

`harness-eval-006` 의 첫 번째 결함이다. `harness-eval-004` 의 결함들과 결정적으로 다른 점은
**테스트를 깨뜨리지 않는다** 는 것이다.

`harness-eval-004` 는 Tester 를 실패시켜 예산을 소비한다. 이 시나리오가 검증하는 것은 그
반대 경로다. 테스트는 계속 통과하는데 **Reviewer 의 `CHANGES_REQUESTED` 만으로** 예산이
소비되어 종료되는가. (`CLAUDE.md §16`, `patchpilot.md §7-2`)

그래서 주입되는 결함은 동작을 바꾸지 않고 품질 기준만 어긴다. 여기서는 제품 코드에 디버깅용
`print()` 를 남긴다. `CLAUDE.md §9` 는 작업 완료 전 확인 항목으로 "디버깅용 print() 가 남아
있지 않은가" 를 명시하고 있고, `reviewer.md §15` 의 5번(불필요한 변경)·6번(코드 컨벤션)
항목이 이를 검토 대상으로 삼는다.

반환값은 그대로이므로 `uv run pytest sample-project/tests -q` 는 전부 통과한다. pytest 는
stdout 을 캡처하므로 출력이 늘어도 판정이 달라지지 않는다.

Reviewer 에게 이 결함의 존재나 기대 판정을 알려주지 않는다. Reviewer 는 실제 diff 와
`plan.md` 만 보고 `reviewer.md` 계약대로 스스로 판단해야 한다. (`evals/README.md §3-18`)

제거 주체는 Developer 2차다. 주입 대상이 `plan.md` 의 수정 허용 파일 목록 **안** 이므로
`guard_plan_scope.py` 가 제거를 막지 않는다. 이것이 전제이며 `precheck` 가 직접 검사한다.
"""

FAULT_ID = "review_budget_001"

TARGET_PATH = "sample-project/src/expense/refund.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:review_budget_001"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_refund("

DESCRIPTION = (
    "제품 코드에 디버깅용 print() 를 남겨 동작은 그대로 두고 코드 품질 기준만 어긴다."
)

# 이 결함이 어기는 규칙. Reviewer 가 어떤 근거로 지적하게 되는지 기록해 둔다.
VIOLATED_RULE = "CLAUDE.md §9 — 디버깅용 print() 가 남아 있지 않은가"

FAULT_CODE = f'''

# 환불 분배 결과를 확인하려고 넣어 둔 임시 출력. (ref: {MARKER})
_split_refund_before_debug_output = split_refund


def split_refund(amount: int, methods: int) -> list[int]:
    shares = _split_refund_before_debug_output(amount, methods)
    print("[debug] split_refund", amount, methods, shares)
    return shares
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def precheck(plan_allowed_files: list[str]) -> None:
    """주입 대상이 `plan.md` 의 수정 허용 파일 목록 **안** 인지 검사한다.

    이 전제가 깨지면 Developer 가 결함을 제거하려 할 때 `guard_plan_scope.py` 가 쓰기를
    차단하고, 그 순간 실행은 `patchpilot.md §3` 의 `SCOPE_OUT_OF_PLAN` 으로 종료된다.
    검증하려는 종료 경로가 아니므로 주입하지 않고 실패시킨다.

    Raises:
        ValueError: 허용 목록이 비어 있거나 주입 대상을 포함하지 않는 경우.
    """
    if not plan_allowed_files:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: plan.md 에서 수정 허용 파일 목록을 찾지 못했습니다."
        )
    if TARGET_PATH not in plan_allowed_files:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 주입 대상 '{TARGET_PATH}' 이(가) plan.md 의 수정 "
            f"허용 파일 목록에 없습니다. Developer 가 제거할 수 없는 위치에 결함을 두면 "
            f"REVIEW_CHANGES_REQUESTED_NO_BUDGET 이 아니라 SCOPE_OUT_OF_PLAN 으로 끝납니다. "
            f"(허용 목록: {plan_allowed_files})"
        )


def apply(source: str) -> str:
    """대상 파일 내용에 결함을 주입한 새 내용을 반환한다.

    Raises:
        ValueError: 주입 전제 조건을 만족하지 못하거나 이미 주입되어 있는 경우.
    """
    if is_applied(source):
        raise ValueError(f"{FAULT_ID} 결함이 이미 주입되어 있습니다.")
    if ANCHOR not in source:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 대상 파일에서 '{ANCHOR}' 를 찾지 못했습니다."
        )

    return source.rstrip("\n") + "\n" + FAULT_CODE
