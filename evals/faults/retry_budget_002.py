"""재시도 예산 소진(RETRY_BUDGET_EXCEEDED) 검증용 2차 결함 정의 (retry_budget_002).

`harness-eval-004` 의 두 번째 결함이다. Developer 2차가 `retry_budget_001` 을 제거한 것이
확인된 뒤에만 주입된다. (`evals/README.md §3-13`)

이 결함은 첫 회차에 1원을 얹고 마지막 회차에서 1원을 뺀다. 합계와 회차 수는 그대로이므로
`회차 간 차이는 최대 1원` 이라는 요구사항이 새로 깨진다. 1차 결함이 깨뜨린 요구사항(앞 회차
우선 배분)과 다른 요구사항을 깨뜨리기 때문에, Tester 2차의 실패 증상이 1차와 실제로 다르다.

제거 주체는 Developer 3차다.
"""

FAULT_ID = "retry_budget_002"

# 이 결함을 주입하기 전에 제거되어 있어야 하는 직전 결함.
PREVIOUS_FAULT_ID = "retry_budget_001"

TARGET_PATH = "sample-project/src/expense/installment.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:retry_budget_002"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_installments("

DESCRIPTION = (
    "첫 회차에 1원을 더하고 마지막 회차에서 1원을 빼서 회차 간 차이를 1원 넘게 벌린다."
)

# 이 결함으로 새로 실패하게 되는 테스트.
SIGNATURE_TEST = "test_split_installments_difference_between_installments_is_at_most_one_won"

FAULT_CODE = f'''

# 첫 회차에 개설 수수료 1원을 얹고 마지막 회차에서 그만큼 깎는다는 요구로 추가된 후처리. (ref: {MARKER})
_split_installments_before_opening_fee_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_opening_fee_rule(total, months)
    if months < 2 or installments[-1] <= 0:
        return installments
    return [installments[0] + 1] + installments[1:-1] + [installments[-1] - 1]
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
            f"허용 파일 목록에 없습니다. 계획 범위 안 결함이라는 전제가 성립하지 않으므로 "
            f"주입하지 않습니다. (허용 목록: {plan_allowed_files})"
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
