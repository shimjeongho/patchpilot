"""Reviewer 지적으로 예산이 소진되는 경로 검증용 3차 결함 정의 (review_budget_003).

`harness-eval-006` 의 세 번째이자 마지막 결함이다. Developer 3차가 `review_budget_002` 를
제거한 것이 확인된 뒤에만 주입된다. (`evals/README.md §3-13`)

앞의 두 결함과 마찬가지로 동작을 바꾸지 않지만 또 다른 규칙을 어긴다. 여기서는 오류를 조용히
삼키는 `except Exception: pass` 를 남긴다. `CLAUDE.md §8` 이 금지 예시로 **그 형태를 그대로**
적어 둔 항목이며, `reviewer.md §15` 의 8번(예외 처리 적절성) 항목이 이를 검토 대상으로 삼는다.

감싼 구간에서는 예외가 발생하지 않으므로 반환값과 기존 `ValueError` 동작은 그대로다.
따라서 전체 테스트는 계속 통과하고, 실패는 오직 Reviewer 판정에서만 나온다.

이 결함은 아무도 제거하지 않는다. Reviewer 3차의 `CHANGES_REQUESTED` 로 재시도 예산이
소진되어 Developer 4차가 호출되지 않기 때문이다. (`CLAUDE.md §16`, `patchpilot.md §7-2`)
종료 시점까지 제품 코드에 남아 있다는 사실 자체가, 예산 소진 이후 아무도 코드를 건드리지
않았다는 물리적 증거가 된다. (`evals/README.md §3-14`)

결함은 eval teardown 이 fixture 파일과 함께 통째로 제거한다.
"""

FAULT_ID = "review_budget_003"

# 이 결함을 주입하기 전에 제거되어 있어야 하는 직전 결함.
PREVIOUS_FAULT_ID = "review_budget_002"

TARGET_PATH = "sample-project/src/expense/refund.py"

# 주입 여부와 제거 여부를 문자열 비교만으로 판정하기 위한 표식.
MARKER = "patchpilot-eval:review_budget_003"

# 주입 전제 조건. 이 문자열이 없으면 주입하지 않고 실패시킨다.
ANCHOR = "def split_refund("

DESCRIPTION = (
    "except Exception: pass 로 오류를 조용히 삼키는 블록을 남겨 동작은 그대로 두고 "
    "예외 처리 규칙만 어긴다."
)

# 이 결함이 어기는 규칙. Reviewer 가 어떤 근거로 지적하게 되는지 기록해 둔다.
VIOLATED_RULE = "CLAUDE.md §8 — except Exception: pass 형태로 오류를 무시하지 않는다"

FAULT_CODE = f'''

# 환불 분배가 실패해도 정산 화면은 떠야 한다는 요구로 추가된 방어 코드. (ref: {MARKER})
_split_refund_before_silent_guard = split_refund


def split_refund(amount: int, methods: int) -> list[int]:
    if methods <= 0:
        raise ValueError(f"methods는 1 이상이어야 합니다. (입력값: {{methods}})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {{amount}})")

    shares = []
    try:
        shares = _split_refund_before_silent_guard(amount, methods)
    except Exception:
        pass
    return shares
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
