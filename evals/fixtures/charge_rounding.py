"""청구 총액을 정산 화폐 단위에 맞추는 공용 기능."""


def round_to_unit(amount: int, unit: int) -> int:
    """금액을 정산 화폐 단위에 맞춰 올림한 결과를 반환한다.

    단위에 걸치지 않는 단수 금액은 버리지 않고 올려서 청구한다.

    Args:
        amount: 올림 대상 금액. 0 이상이어야 한다.
        unit: 정산 화폐 단위. 1 이상이어야 한다.

    Raises:
        ValueError: amount가 음수이거나 unit이 1 미만인 경우.
    """
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")
    if unit <= 0:
        raise ValueError(f"unit은 1 이상이어야 합니다. (입력값: {unit})")

    remainder = amount % unit
    if remainder == 0:
        return amount
    return amount + (unit - remainder)
