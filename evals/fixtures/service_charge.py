"""봉사료를 포함한 청구 총액을 인원수에 맞게 청구하는 기능."""

from expense.charge_rounding import round_to_unit


def split_service_charge(bill: int, people: int, charge_percent: int, unit: int) -> list[int]:
    """봉사료를 더해 정산 단위로 올림한 총액을 인원수에 맞게 나눈 1인당 부담액 목록을 반환한다.

    봉사료는 청구 금액에 charge_percent를 적용해 내림으로 계산하고, 그 합계를 정산 화폐
    단위에 맞춰 올린 금액이 실제로 걷어야 할 총액이다. 반환된 부담액의 합계는 그 총액과
    항상 같아야 한다.

    Args:
        bill: 봉사료를 제외한 청구 금액. 0 이상이어야 한다.
        people: 정산 대상 인원수. 1 이상이어야 한다.
        charge_percent: 청구 금액에 적용할 봉사료 비율(%). 0 이상이어야 한다.
        unit: 정산 화폐 단위. 1 이상이어야 한다.

    Raises:
        ValueError: people 또는 unit이 1 미만이거나 bill 또는 charge_percent가 음수인 경우.
    """
    if people <= 0:
        raise ValueError(f"people은 1 이상이어야 합니다. (입력값: {people})")
    if bill < 0:
        raise ValueError(f"bill은 0 이상이어야 합니다. (입력값: {bill})")
    if charge_percent < 0:
        raise ValueError(f"charge_percent는 0 이상이어야 합니다. (입력값: {charge_percent})")

    service_charge = bill * charge_percent // 100
    total = round_to_unit(bill + service_charge, unit)
    return [total // people] * people
