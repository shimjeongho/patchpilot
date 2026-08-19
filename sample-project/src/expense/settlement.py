"""정산 금액을 동전 단위에 맞춰 청구하는 기능."""

from expense.allocation import allocate_units


def settle_by_unit(amount: int, people: int, unit: int) -> tuple[list[int], int]:
    """금액을 unit 단위로 각자에게 청구하고 (청구액 목록, 남는 잔돈)을 반환한다.

    각 사람의 청구액은 항상 unit의 배수이며, 청구하고 남은 잔돈은 unit보다 작아야 한다.

    Args:
        amount: 정산할 전체 금액. 0 이상이어야 한다.
        people: 정산 대상 인원수. 1 이상이어야 한다.
        unit: 청구 단위 금액. 1 이상이어야 한다.

    Raises:
        ValueError: people 또는 unit이 1 미만이거나 amount가 음수인 경우.
    """
    if people <= 0:
        raise ValueError(f"people은 1 이상이어야 합니다. (입력값: {people})")
    if unit <= 0:
        raise ValueError(f"unit은 1 이상이어야 합니다. (입력값: {unit})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")

    # 모든 사람이 같은 개수를 부담할 수 있는 만큼만 단위를 배분한다.
    total_units = amount // (unit * people) * people
    unit_counts = allocate_units(total_units, people)

    shares = [unit_count * unit for unit_count in unit_counts]
    change = amount - sum(shares)
    return shares, change
