"""결제 취소 시 환불 금액을 결제 수단별로 나누어 돌려주는 기능."""


def split_refund(amount: int, methods: int) -> list[int]:
    """환불 금액을 결제 수단 수에 맞게 나눈 수단별 환불액 목록을 반환한다.

    반환된 수단별 환불액의 합계는 환불 금액과 항상 같아야 한다.

    Args:
        amount: 환불할 총 금액. 0 이상이어야 한다.
        methods: 환불을 나눠 받을 결제 수단 수. 1 이상이어야 한다.

    Raises:
        ValueError: methods가 1 미만이거나 amount가 음수인 경우.
    """
    if methods <= 0:
        raise ValueError(f"methods는 1 이상이어야 합니다. (입력값: {methods})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")

    return [amount // methods] * methods
