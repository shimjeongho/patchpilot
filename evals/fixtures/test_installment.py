import pytest

from expense.installment import split_installments


def test_split_installments_preserves_total_when_total_is_not_evenly_divisible():
    assert sum(split_installments(10000, 3)) == 10000


def test_split_installments_distributes_remainder_to_earlier_months_first():
    assert split_installments(10000, 3) == [3334, 3333, 3333]


def test_split_installments_difference_between_installments_is_at_most_one_won():
    installments = split_installments(10000, 3)
    assert max(installments) - min(installments) <= 1


def test_split_installments_returns_one_installment_per_month():
    assert len(split_installments(10000, 7)) == 7


def test_split_installments_returns_equal_amounts_when_total_is_evenly_divisible():
    assert split_installments(9000, 3) == [3000, 3000, 3000]


def test_split_installments_charges_entire_total_in_a_single_month():
    assert split_installments(10000, 1) == [10000]


def test_split_installments_returns_zero_for_every_month_when_total_is_zero():
    assert split_installments(0, 3) == [0, 0, 0]


def test_split_installments_raises_value_error_when_months_is_zero():
    with pytest.raises(ValueError):
        split_installments(10000, 0)


def test_split_installments_raises_value_error_when_months_is_negative():
    with pytest.raises(ValueError):
        split_installments(10000, -1)


def test_split_installments_raises_value_error_when_total_is_negative():
    with pytest.raises(ValueError):
        split_installments(-1, 3)


def test_split_installments_preserves_total_for_various_totals_and_months():
    cases = [
        (10000, 3),
        (10000, 7),
        (9999, 4),
        (12345, 5),
        (100, 3),
        (0, 3),
    ]
    for total, months in cases:
        installments = split_installments(total, months)
        assert sum(installments) == total, (total, months, installments)
