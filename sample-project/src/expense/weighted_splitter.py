"""정산 금액을 가중치 비율에 따라 분배하는 기능."""


def split_by_weights(amount: int, weights: list[int]) -> list[int]:
    """금액을 가중치 비율에 따라 분배한 결과를 가중치 개수만큼의 리스트로 반환한다.

    내림으로 버려진 나머지는 이상적인 몫의 소수부가 큰 사람부터 1원씩 배분하므로
    전체 합계는 항상 amount와 같다.

    Args:
        amount: 분배할 전체 금액. 0 이상이어야 한다.
        weights: 사람별 가중치. 비어 있지 않아야 하고 각 값은 0 이상이며 총합은 1 이상이어야 한다.

    Raises:
        ValueError: weights가 비었거나 음수 가중치가 있거나 총 가중치가 0인 경우, amount가 음수인 경우.
    """
    if not weights:
        raise ValueError("weights는 최소 1개 이상이어야 합니다. (입력값: [])")
    if any(weight < 0 for weight in weights):
        raise ValueError(f"weights의 각 값은 0 이상이어야 합니다. (입력값: {weights})")
    if amount < 0:
        raise ValueError(f"amount는 0 이상이어야 합니다. (입력값: {amount})")

    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError(f"weights의 총합은 1 이상이어야 합니다. (입력값: {weights})")

    base_shares = [amount * weight // total_weight for weight in weights]
    remainder = amount - sum(base_shares)

    # 내림으로 버려진 금액은 소수부(amount * weight % total_weight)가 큰 사람부터 1원씩 돌려주어
    # 전체 합계를 보존하고 각 사람의 초과분을 최대 1원으로 제한한다.
    # 소수부가 같으면 앞 사람이 먼저 받는다. 소수부가 0인 사람(가중치 0 포함)은
    # remainder가 소수부 0이 아닌 사람 수보다 항상 작으므로 배분 대상이 되지 않는다.
    receiving_order = sorted(
        range(len(weights)),
        key=lambda index: (-(amount * weights[index] % total_weight), index),
    )
    for index in receiving_order[:remainder]:
        base_shares[index] += 1

    return base_shares
