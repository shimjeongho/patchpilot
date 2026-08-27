import pytest

from expense.coupon import apply_coupon


def test_apply_coupon_preserves_total_when_discount_is_not_evenly_divisible():
    assert sum(apply_coupon(1000, 3)) == 1000


def test_apply_coupon_distributes_remainder_to_earlier_items_first():
    assert apply_coupon(1000, 3) == [334, 333, 333]


def test_apply_coupon_gives_the_remainder_to_the_first_item():
    assert apply_coupon(1000, 3)[0] == 334


def test_apply_coupon_returns_equal_shares_when_discount_is_evenly_divisible():
    assert apply_coupon(900, 3) == [300, 300, 300]


def test_apply_coupon_returns_one_share_per_item():
    assert len(apply_coupon(1000, 4)) == 4


def test_apply_coupon_difference_between_items_is_at_most_one_won():
    shares = apply_coupon(1000, 3)
    assert max(shares) - min(shares) <= 1


def test_apply_coupon_gives_entire_discount_to_single_item():
    assert apply_coupon(1000, 1) == [1000]


def test_apply_coupon_returns_zero_share_for_every_item_when_discount_is_zero():
    assert apply_coupon(0, 3) == [0, 0, 0]


def test_apply_coupon_spreads_remainder_across_leading_items():
    assert apply_coupon(1001, 3) == [334, 334, 333]


def test_apply_coupon_raises_value_error_when_items_is_zero():
    with pytest.raises(ValueError):
        apply_coupon(1000, 0)


def test_apply_coupon_raises_value_error_when_discount_is_negative():
    with pytest.raises(ValueError):
        apply_coupon(-1, 3)


def test_apply_coupon_preserves_total_for_various_discounts_and_items():
    cases = [(1000, 3), (1001, 3), (900, 3), (1000, 4), (9999, 7), (0, 3)]
    for discount, items in cases:
        shares = apply_coupon(discount, items)
        assert sum(shares) == discount, (discount, items, shares)
