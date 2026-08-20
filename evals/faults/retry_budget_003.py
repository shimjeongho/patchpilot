"""재시도 예산 소진(RETRY_BUDGET_EXCEEDED) 검증용 3차 결함 정의 (retry_budget_003).

`harness-eval-004` 의 마지막 결함이다. Developer 3차가 `retry_budget_002` 를 제거한 것이
확인된 뒤에만 주입된다. (`evals/README.md §3-13`)

이 결함은 마지막 회차를 0원으로 덮어써 총액 보존을 깨뜨린다. 1차(앞 회차 우선 배분),
2차(회차 간 차이 1원)와 또 다른 요구사항을 깨뜨리므로 Tester 3차의 실패 증상도 앞의 두 번과
다르다.

이 결함은 **아무도 제거하지 않는다.** Tester 3차가 실패하는 순간 재시도 예산이 소진되어
Developer 4차가 호출되지 않기 때문이다. 종료 시점까지 이 결함이 대상 파일에 그대로 남아
있다는 사실 자체가 "그 뒤로 아무도 제품 코드를 건드리지 않았다" 는 증거가 된다.
결함은 eval teardown이 fixture 파일과 함께 통째로 제거한다.
"""

FAULT_ID = "retry_budget_003"

# 이 결함을 주입하기 전에 제거되어 있어야 하는 직전 결함.
PREVIOUS_FAULT_ID = "retry_budget_002"

TARGET_PATH = "sample-project/src/expense/installment.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:retry_budget_003"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_installments("

DESCRIPTION = "마지막 회차 청구 금액을 0원으로 덮어써 분납 총액 보존을 깨뜨린다."

# 이 결함으로 새로 실패하게 되는 테스트.
SIGNATURE_TEST = "test_split_installments_preserves_total_when_total_is_not_evenly_divisible"

FAULT_CODE = f'''

# 마지막 회차는 청구하지 않는다는 요구로 추가된 후처리. (ref: {MARKER})
_split_installments_before_last_month_waiver_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_last_month_waiver_rule(total, months)
    return installments[:-1] + [0]
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
