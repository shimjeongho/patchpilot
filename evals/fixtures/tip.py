"""청구 금액과 팁을 합한 총액을 인원수에 맞게 청구하는 기능."""


def split_tip(bill: int, people: int, tip_percent: int) -> list[int]:
    """청구 금액과 팁을 합한 총액을 인원수에 맞게 나눈 1인당 부담액 목록을 반환한다.

    팁은 청구 금액에 tip_percent를 적용해 계산하며, 반환된 부담액의 합계는
    청구 금액과 팁을 합한 총액과 항상 같아야 한다.

    Args:
        bill: 팁을 제외한 청구 금액. 0 이상이어야 한다.
        people: 정산 대상 인원수. 1 이상이어야 한다.
        tip_percent: 청구 금액에 적용할 팁 비율(%). 0 이상이어야 한다.

    Raises:
        ValueError: people가 1 미만이거나 bill 또는 tip_percent가 음수인 경우.
    """
    if people <= 0:
        raise ValueError(f"people은 1 이상이어야 합니다. (입력값: {people})")
    if bill < 0:
        raise ValueError(f"bill은 0 이상이어야 합니다. (입력값: {bill})")
    if tip_percent < 0:
        raise ValueError(f"tip_percent는 0 이상이어야 합니다. (입력값: {tip_percent})")

    bill_share = bill // people
    tip_share = bill_share * tip_percent // 100
    return [bill_share + tip_share] * people
