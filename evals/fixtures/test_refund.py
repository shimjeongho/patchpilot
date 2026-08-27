import pytest

from expense.refund import split_refund


def test_split_refund_preserves_total_when_amount_is_not_evenly_divisible():
    assert sum(split_refund(1000, 3)) == 1000


def test_split_refund_distributes_remainder_to_earlier_methods_first():
    assert split_refund(1000, 3) == [334, 333, 333]


def test_split_refund_returns_equal_shares_when_amount_is_evenly_divisible():
    assert split_refund(900, 3) == [300, 300, 300]


def test_split_refund_returns_one_share_per_method():
    assert len(split_refund(1000, 4)) == 4


def test_split_refund_difference_between_methods_is_at_most_one_won():
    shares = split_refund(1000, 3)
    assert max(shares) - min(shares) <= 1


def test_split_refund_gives_entire_amount_to_single_method():
    assert split_refund(1000, 1) == [1000]


def test_split_refund_returns_zero_share_for_every_method_when_amount_is_zero():
    assert split_refund(0, 3) == [0, 0, 0]


def test_split_refund_spreads_remainder_across_leading_methods():
    assert split_refund(1001, 3) == [334, 334, 333]


def test_split_refund_raises_value_error_when_methods_is_zero():
    with pytest.raises(ValueError):
        split_refund(1000, 0)


def test_split_refund_raises_value_error_when_amount_is_negative():
    with pytest.raises(ValueError):
        split_refund(-1, 3)


def test_split_refund_preserves_total_for_various_amounts_and_methods():
    cases = [(1000, 3), (1001, 3), (900, 3), (1000, 4), (9999, 7), (0, 3)]
    for amount, methods in cases:
        shares = split_refund(amount, methods)
        assert sum(shares) == amount, (amount, methods, shares)
