"""Reviewer 지적으로 예산이 소진되는 경로 검증용 2차 결함 정의 (review_budget_002).

`harness-eval-006` 의 두 번째 결함이다. Developer 2차가 `review_budget_001` 을 제거한 것이
확인된 뒤에만 주입된다. (`evals/README.md §3-13`)

1차와 마찬가지로 동작을 바꾸지 않지만 **다른 규칙** 을 어긴다. 여기서는 아무 데서도 호출되지
않는 죽은 코드를 남긴다. `CLAUDE.md §9` 는 "사용하지 않는 코드가 남아 있지 않은가" 를 작업
완료 전 확인 항목으로 두고 있고, `CLAUDE.md §17` 의 최소 변경 원칙과도 어긋난다.

같은 결함을 반복 주입하지 않는 이유는 `evals/README.md §3-12` 에 있다. 매 회차 같은 지적이
반복되면 Reviewer 가 실제로 그 회차의 코드를 다시 검토했는지, 아니면 직전 판정을 그대로
되풀이한 것인지 구분할 수 없다.

제거 주체는 Developer 3차다.
"""

FAULT_ID = "review_budget_002"

# 이 결함을 주입하기 전에 제거되어 있어야 하는 직전 결함.
PREVIOUS_FAULT_ID = "review_budget_001"

TARGET_PATH = "sample-project/src/expense/refund.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:review_budget_002"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_refund("

DESCRIPTION = (
    "어디에서도 호출되지 않는 죽은 helper 를 남겨 동작은 그대로 두고 최소 변경 원칙만 어긴다."
)

# 이 결함이 어기는 규칙. Reviewer 가 어떤 근거로 지적하게 되는지 기록해 둔다.
VIOLATED_RULE = "CLAUDE.md §9 — 사용하지 않는 코드가 남아 있지 않은가"

FAULT_CODE = f'''

# 나중에 수단별 상한을 걸 때 쓰려고 미리 만들어 둔 helper. 아직 아무 데서도 부르지 않는다.
# (ref: {MARKER})
def _cap_refund_share_for_future_use(share: int, limit: int) -> int:
    if share > limit:
        return limit
    return share


def _describe_refund_share_for_future_use(share: int) -> str:
    return "share=" + str(share)
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def precheck(plan_allowed_files: list[str]) -> None:
    """주입 대상이 `plan.md` 의 수정 허용 파일 목록 **안** 인지 검사한다.

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
            f"허용 파일 목록에 없습니다. (허용 목록: {plan_allowed_files})"
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
