"""분배 개수를 인원수에 맞게 나누는 공용 기능."""


def allocate_units(unit_count: int, people: int) -> list[int]:
    """분배 단위 개수를 인원수에 맞게 나눈 결과를 사람 수만큼의 리스트로 반환한다.

    사람 간 개수 차이는 최대 1개를 넘지 않으며, 전체 합계는 항상 unit_count와 같다.

    Args:
        unit_count: 분배할 단위의 총 개수. 0 이상이어야 한다.
        people: 분배 대상 인원수. 1 이상이어야 한다.
    """
    units_per_person = unit_count // people
    allocated = [units_per_person] * people

    # 남는 개수를 앞 사람부터 1개씩 배분해 전체 개수를 보존하고, 사람 간 차이를 최대 1개로 유지한다.
    remaining_units = unit_count - units_per_person * people
    for index in range(remaining_units):
        allocated[index] += 1

    return allocated
