import pytest

from expense.tip import split_tip


def test_split_tip_preserves_total_when_total_is_not_evenly_divisible():
    assert sum(split_tip(10000, 3, 10)) == 11000


def test_split_tip_distributes_remainder_to_earlier_people_first():
    assert split_tip(10000, 3, 10) == [3667, 3667, 3666]


def test_split_tip_returns_equal_shares_when_total_is_evenly_divisible():
    assert split_tip(9000, 3, 10) == [3300, 3300, 3300]


def test_split_tip_returns_one_share_per_person():
    assert len(split_tip(10000, 4, 15)) == 4


def test_split_tip_difference_between_people_is_at_most_one_won():
    shares = split_tip(10000, 3, 10)
    assert max(shares) - min(shares) <= 1


def test_split_tip_splits_bill_only_when_tip_percent_is_zero():
    assert split_tip(10000, 3, 0) == [3334, 3333, 3333]


def test_split_tip_gives_entire_total_to_single_person():
    assert split_tip(10000, 1, 10) == [11000]


def test_split_tip_returns_zero_share_for_every_person_when_bill_is_zero():
    assert split_tip(0, 3, 10) == [0, 0, 0]


def test_split_tip_discards_fractional_tip_below_one_won():
    # 팁은 내림으로 계산하므로 1원 미만은 청구하지 않는다.
    assert sum(split_tip(9, 3, 10)) == 9


def test_split_tip_raises_value_error_when_people_is_zero():
    with pytest.raises(ValueError):
        split_tip(10000, 0, 10)


def test_split_tip_raises_value_error_when_bill_is_negative():
    with pytest.raises(ValueError):
        split_tip(-1, 3, 10)


def test_split_tip_raises_value_error_when_tip_percent_is_negative():
    with pytest.raises(ValueError):
        split_tip(10000, 3, -1)


def test_split_tip_preserves_total_for_various_bills_and_people():
    cases = [
        (10000, 3, 10),
        (10000, 4, 15),
        (9999, 7, 13),
        (12345, 5, 20),
        (100, 3, 1),
        (0, 3, 10),
    ]
    for bill, people, tip_percent in cases:
        shares = split_tip(bill, people, tip_percent)
        assert sum(shares) == bill + bill * tip_percent // 100, (bill, people, tip_percent, shares)
