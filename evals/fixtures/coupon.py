"""쿠폰 할인액을 주문 항목별로 나누어 적용하는 기능."""


def apply_coupon(discount: int, items: int) -> list[int]:
    """쿠폰 할인액을 주문 항목 수에 맞게 나눈 항목별 할인액 목록을 반환한다.

    반환된 항목별 할인액의 합계는 쿠폰 할인액과 항상 같아야 한다.

    Args:
        discount: 적용할 쿠폰 할인액. 0 이상이어야 한다.
        items: 할인을 나눠 받을 주문 항목 수. 1 이상이어야 한다.

    Raises:
        ValueError: items가 1 미만이거나 discount가 음수인 경우.
    """
    if items <= 0:
        raise ValueError(f"items는 1 이상이어야 합니다. (입력값: {items})")
    if discount < 0:
        raise ValueError(f"discount는 0 이상이어야 합니다. (입력값: {discount})")

    return [discount // items] * items
