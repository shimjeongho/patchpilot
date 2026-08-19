"""정산 금액을 여러 명에게 분배하는 기능."""


def split_amount(amount: int, people: int) -> list[int]:
    """금액을 인원수에 맞게 분배한 결과를 사람 수만큼의 리스트로 반환한다.

    나누어떨어지지 않는 나머지는 앞 사람부터 1원씩 배분하므로 전체 합계는 항상 amount와 같다.

    Args:
        amount: 분배할 전체 금액. 0 이상이어야 한다.
        people: 분배 대상 인원수. 1 이상이어야 한다.

    Raises:
        ValueError: people가 1 미만이거나 amount가 음수인 경우.
    """
    if people <= 0:
        raise ValueError(f"people은 1 이상이어야 합니다. (입력값: {people})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")

    amount_per_person = amount // people
    remainder = amount % people

    # 나머지 금액을 앞 사람부터 1원씩 배분해 전체 합계를 보존하고, 사람 간 차이를 최대 1원으로 유지한다.
    return [
        amount_per_person + 1 if index < remainder else amount_per_person
        for index in range(people)
    ]
