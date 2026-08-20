"""각자 이미 낸 금액을 대조해 누가 누구에게 얼마를 보내야 하는지 계산하는 기능."""

from expense.splitter import split_amount


def reconcile_payments(paid: list[int]) -> list[tuple[int, int, int]]:
    """이미 낸 금액 목록을 받아 (보내는 사람, 받는 사람, 금액) 이체 목록을 반환한다.

    사람은 입력 리스트의 인덱스로 식별한다.
    이체를 모두 반영하면 각자의 최종 부담액이 공평하게 나눈 금액과 같아져야 한다.

    Args:
        paid: 사람별로 이미 낸 금액. 비어 있지 않아야 하고 각 값은 0 이상이어야 한다.

    Raises:
        ValueError: paid가 비었거나 음수 금액이 포함된 경우.
    """
    if not paid:
        raise ValueError("paid는 최소 1개 이상이어야 합니다. (입력값: [])")
    if any(amount < 0 for amount in paid):
        raise ValueError(f"paid의 각 값은 0 이상이어야 합니다. (입력값: {paid})")

    total = sum(paid)
    people = len(paid)

    # 공평 부담액을 전원 동일한 한 개 값으로 잡으면 총액이 나누어떨어지지 않을 때 잔액 합계가 0이 되지
    # 않아 이체만으로는 정산이 끝나지 않는다. 1원 단위 차이를 앞 사람부터 부담시키는 프로젝트 공통 규칙을
    # 재사용해 사람별 부담액을 구하면 그 합계가 항상 총액과 같아진다.
    fair_shares = split_amount(total, people)
    balances = [amount - fair_share for amount, fair_share in zip(paid, fair_shares)]

    debtors = [index for index, balance in enumerate(balances) if balance < 0]
    creditors = [index for index, balance in enumerate(balances) if balance > 0]

    # 덜 낸 사람과 더 낸 사람을 앞에서부터 짝짓되, 한 번의 이체로는 잔액이 큰 쪽이 다 상쇄되지 않으므로
    # 잔액이 0이 된 사람만 다음으로 넘긴다. 매 반복마다 최소 한쪽 잔액이 0이 되어 반복은 반드시 끝난다.
    transfers = []
    debtor_index = 0
    creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor = debtors[debtor_index]
        creditor = creditors[creditor_index]

        settled = min(-balances[debtor], balances[creditor])
        transfers.append((debtor, creditor, settled))
        balances[debtor] += settled
        balances[creditor] -= settled

        if balances[debtor] == 0:
            debtor_index += 1
        if balances[creditor] == 0:
            creditor_index += 1

    return transfers
