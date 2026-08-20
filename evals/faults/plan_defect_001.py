"""계획 결함(PLAN_DEFECT) 라우팅 검증용 결함 정의 (plan_defect_001).

Developer 1차가 `plan.md` 의 수정 허용 파일(`service_charge.py`) 안에서 요구사항대로 수정을
마친 직후, **그 허용 목록 밖에 있는** 협력 모듈(`charge_rounding.py`)에 결함을 주입한다.

이렇게 하면 Tester 1차는 실제 pytest 실행으로 `STATUS: FAIL` 을 기록하게 되는데, 그 실패는
다음 성질을 가진다.

* Developer가 바꾼 코드는 계획대로이고 구현 실수가 없다.
* 실패 지점은 `plan.md` 의 수정 허용 파일 목록 밖이다.
* 실패 테스트에는 `tests/test_charge_rounding.py` 가 포함된다. 이 테스트는 helper를 직접
  호출하므로 허용 목록 안에서 무엇을 해도 통과시킬 수 없다.

따라서 같은 `plan.md` 로 Developer만 다시 불러도 해결되지 않고, Planner를 다시 불러 수정
범위를 넓혀야 한다. 이것이 `CLAUDE.md §14` 의 `PLAN_DEFECT` 정의와 일치한다.

주입 방식은 `retry_001` 과 동일하게 파일 끝에 후처리 래퍼를 덧붙이는 것이다. 모듈 최상위의
`round_to_unit` 이름만 존재하면 동작하므로 주입 결과가 결정론적이다.

주입된 결함을 제거하는 주체는 Harness가 아니라 Developer 2차이며, 수정 범위를 넓히는 주체는
Planner 2차다. Harness가 스스로 되돌리면 `FAIL -> 재계획 -> 재수정 -> PASS` 전이의 검증
의미가 사라진다.
"""

FAULT_ID = "plan_defect_001"

TARGET_PATH = "sample-project/src/expense/charge_rounding.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:plan_defect_001"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def round_to_unit("

DESCRIPTION = (
    "round_to_unit 결과를 절상이 아니라 절사로 바꿔 정산 단위 마감 규칙을 깨뜨린다."
)

FAULT_CODE = f'''

# 단위에 못 미치는 단수 금액은 청구하지 않는다는 요구로 추가된 후처리. (ref: {MARKER})
_round_to_unit_before_fraction_discard_rule = round_to_unit


def round_to_unit(amount: int, unit: int) -> int:
    rounded = _round_to_unit_before_fraction_discard_rule(amount, unit)
    if rounded > amount:
        return rounded - unit
    return rounded
'''


def is_applied(source: str) -> bool:
    """대상 파일 내용에 이 결함이 주입되어 있는지 판정한다."""
    return MARKER in source


def precheck(plan_allowed_files: list[str]) -> None:
    """주입 전제 조건을 `plan.md` 의 수정 허용 파일 목록으로 검사한다.

    이 결함은 "계획 범위 밖에서 원인이 발생한다" 는 상황을 만드는 것이 목적이다.
    주입 대상이 이미 허용 목록 안에 있으면 그 상황이 성립하지 않으므로, 주입하지 않고
    실패시켜 eval이 조용히 통과하는 일을 막는다.

    Raises:
        ValueError: 허용 목록이 비어 있거나 주입 대상을 이미 포함하는 경우.
    """
    if not plan_allowed_files:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: plan.md 에서 수정 허용 파일 목록을 찾지 못했습니다."
        )
    if TARGET_PATH in plan_allowed_files:
        raise ValueError(
            f"{FAULT_ID} 주입 전제 조건 위반: 주입 대상 '{TARGET_PATH}' 이(가) 이미 plan.md 의 "
            f"수정 허용 파일 목록에 포함되어 있습니다. 계획 범위 밖 결함이라는 전제가 성립하지 "
            f"않으므로 주입하지 않습니다. (허용 목록: {plan_allowed_files})"
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
