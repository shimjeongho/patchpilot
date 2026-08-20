"""재시도 예산 소진(RETRY_BUDGET_EXCEEDED) 검증용 1차 결함 정의 (retry_budget_001).

`harness-eval-004` 는 결함을 세 번 연쇄로 주입한다. 이 모듈은 그중 첫 번째다.

    Developer 1차(버그 A 수정) -> [retry_budget_001] -> Tester 1차 FAIL
    Developer 2차(001 제거)    -> [retry_budget_002] -> Tester 2차 FAIL
    Developer 3차(002 제거)    -> [retry_budget_003] -> Tester 3차 FAIL -> 예산 소진

같은 결함을 반복 주입하지 않는 이유는 `evals/README.md §3-12` 에 있다. 같은 결함을 다시
주입하면 Developer가 무엇을 고쳤는지와 무관하게 매번 같은 실패가 나므로, "Harness가
Developer의 수정을 몰래 되돌리는 구조" 와 구분되지 않는다.

이 결함은 회차별 청구 금액 목록의 순서를 뒤집는다. 합계·회차 수·회차 간 차이는 그대로
유지되므로 `나머지는 앞 회차부터 배분한다` 는 요구사항 하나만 깨진다. 실패 테스트가 하나로
좁혀지기 때문에 Tester가 원인을 제품 코드 한 곳으로 특정할 수 있다.

주입 방식은 `retry_001` 과 같다. 파일 끝에 후처리 래퍼를 덧붙이므로 Developer 1차가 함수
본문을 어떻게 구현했는지와 무관하게 결과가 결정론적이다.

제거 주체는 Developer 2차다. Harness는 이 결함을 스스로 되돌리지 않고, 다음 결함
(`retry_budget_002`)을 주입하기 전에 **제거되었는지만 확인** 한다. 제거되지 않았으면 다음
결함을 주입하지 않고 즉시 실패시킨다. (`evals/README.md §3-13`)
"""

FAULT_ID = "retry_budget_001"

TARGET_PATH = "sample-project/src/expense/installment.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:retry_budget_001"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_installments("

DESCRIPTION = (
    "split_installments 결과의 순서를 뒤집어 나머지 금액이 앞 회차가 아니라 뒤 회차부터 "
    "배분되게 만든다."
)

# 이 결함으로 새로 실패하게 되는 테스트.
SIGNATURE_TEST = "test_split_installments_distributes_remainder_to_earlier_months_first"

FAULT_CODE = f'''

# 최근 회차일수록 청구액이 커야 한다는 요구로 추가된 후처리. (ref: {MARKER})
_split_installments_before_recent_month_priority_rule = split_installments


def split_installments(total: int, months: int) -> list[int]:
    installments = _split_installments_before_recent_month_priority_rule(total, months)
    return installments[::-1]
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def precheck(plan_allowed_files: list[str]) -> None:
    """주입 대상이 `plan.md` 의 수정 허용 파일 목록 **안** 인지 검사한다.

    `plan_defect_001` 의 정확한 반대 조건이다. 이 시나리오의 세 FAIL은 모두
    `PRODUCT_CODE_DEFECT` 로 분류되어야 하므로, 주입 대상이 Developer가 고칠 수 있는 계획
    범위 안에 있어야 한다. 범위 밖이라면 `PLAN_DEFECT` 로 분류하는 것이 옳은 판정이 되어
    검증하려는 경로를 지나가지 못한다.

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
