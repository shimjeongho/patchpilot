import pytest

from expense.reconciliation import reconcile_payments


def apply_transfers(paid, transfers):
    """이체 목록을 반영한 뒤 각자의 최종 부담액을 반환한다."""
    final_burden = list(paid)
    for sender, receiver, amount in transfers:
        final_burden[sender] += amount
        final_burden[receiver] -= amount
    return final_burden


def test_reconcile_returns_no_transfer_when_everyone_paid_the_same():
    assert reconcile_payments([1000, 1000, 1000]) == []


def test_reconcile_returns_no_transfer_for_single_person():
    assert reconcile_payments([5000]) == []


def test_reconcile_raises_value_error_when_paid_is_empty():
    with pytest.raises(ValueError):
        reconcile_payments([])


def test_reconcile_raises_value_error_when_paid_contains_negative_amount():
    with pytest.raises(ValueError):
        reconcile_payments([1000, -1])


def test_reconcile_moves_every_owed_amount_to_the_overpayer():
    transfers = reconcile_payments([9000, 0, 0])
    assert sum(amount for _, _, amount in transfers) == 6000


def test_reconcile_settles_all_balances_between_two_overpayers():
    assert reconcile_payments([4000, 2000, 0, 0]) == [(2, 0, 1500), (3, 0, 1000), (3, 1, 500)]


def test_reconcile_keeps_total_paid_unchanged():
    paid = [4000, 2000, 0, 0]
    assert sum(apply_transfers(paid, reconcile_payments(paid))) == sum(paid)


def test_reconcile_keeps_final_burden_difference_at_most_one_won():
    paid = [6, 0, 0, 0]
    final_burden = apply_transfers(paid, reconcile_payments(paid))
    assert max(final_burden) - min(final_burden) <= 1


def test_reconcile_gives_extra_won_to_earlier_people_when_total_is_not_evenly_divisible():
    paid = [6, 0, 0, 0]
    assert apply_transfers(paid, reconcile_payments(paid)) == [2, 2, 1, 1]


def test_reconcile_keeps_every_transfer_amount_positive():
    transfers = reconcile_payments([4000, 2000, 0, 0])
    assert all(amount > 0 for _, _, amount in transfers)


def test_reconcile_uses_fewer_transfers_than_people():
    paid = [4000, 2000, 0, 0]
    assert len(reconcile_payments(paid)) <= len(paid) - 1


def test_reconcile_settles_every_balance_for_various_payment_combinations():
    cases = [
        ([9000, 0, 0], [3000, 3000, 3000]),
        ([4000, 2000, 0, 0], [1500, 1500, 1500, 1500]),
        ([6, 0, 0, 0], [2, 2, 1, 1]),
        ([0, 1], [1, 0]),
        ([10000, 0, 0], [3334, 3333, 3333]),
        ([1, 2, 3], [2, 2, 2]),
        ([100, 0, 0, 0, 0], [20, 20, 20, 20, 20]),
        ([7, 0, 0], [3, 2, 2]),
    ]
    for paid, expected_burden in cases:
        transfers = reconcile_payments(paid)
        assert apply_transfers(paid, transfers) == expected_burden, (paid, transfers)
