"""총액을 분납 회차별 청구 금액으로 나누는 기능."""


def split_installments(total: int, months: int) -> list[int]:
    """총액을 분납 회차 수에 맞게 나눈 회차별 청구 금액 목록을 반환한다.

    나누어떨어지지 않는 나머지는 앞 회차부터 1원씩 배분하므로 회차별 청구 금액의 합계는
    항상 total과 같아야 한다.

    Args:
        total: 분납 대상 총액. 0 이상이어야 한다.
        months: 분납 회차 수. 1 이상이어야 한다.

    Raises:
        ValueError: months가 1 미만이거나 total이 음수인 경우.
    """
    if months <= 0:
        raise ValueError(f"months는 1 이상이어야 합니다. (입력값: {months})")
    if total < 0:
        raise ValueError(f"total은 0 이상이어야 합니다. (입력값: {total})")

    amount_per_month = total // months
    return [amount_per_month] * months
