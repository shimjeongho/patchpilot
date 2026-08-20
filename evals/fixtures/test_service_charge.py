import pytest

from expense.service_charge import split_service_charge


def test_split_service_charge_preserves_total_when_total_is_not_evenly_divisible():
    assert sum(split_service_charge(10000, 3, 10, 1)) == 11000


def test_split_service_charge_distributes_remainder_to_earlier_people_first():
    assert split_service_charge(10000, 3, 10, 1) == [3667, 3667, 3666]


def test_split_service_charge_returns_equal_shares_when_total_is_evenly_divisible():
    assert split_service_charge(9000, 3, 10, 100) == [3300, 3300, 3300]


def test_split_service_charge_preserves_total_rounded_up_to_the_settlement_unit():
    assert sum(split_service_charge(10050, 3, 0, 100)) == 10100


def test_split_service_charge_distributes_the_total_rounded_up_to_the_settlement_unit():
    assert split_service_charge(10050, 3, 0, 100) == [3367, 3367, 3366]


def test_split_service_charge_returns_one_share_per_person():
    assert len(split_service_charge(10000, 4, 15, 100)) == 4


def test_split_service_charge_difference_between_people_is_at_most_one_won():
    shares = split_service_charge(10050, 3, 10, 100)
    assert max(shares) - min(shares) <= 1


def test_split_service_charge_splits_bill_only_when_charge_percent_is_zero():
    assert split_service_charge(10000, 3, 0, 1) == [3334, 3333, 3333]


def test_split_service_charge_gives_entire_total_to_single_person():
    assert split_service_charge(10000, 1, 10, 100) == [11000]


def test_split_service_charge_returns_zero_share_for_every_person_when_bill_is_zero():
    assert split_service_charge(0, 3, 10, 100) == [0, 0, 0]


def test_split_service_charge_discards_fractional_charge_below_one_won():
    # 봉사료는 내림으로 계산하므로 1원 미만은 청구하지 않는다.
    assert sum(split_service_charge(9, 3, 10, 1)) == 9


def test_split_service_charge_raises_value_error_when_people_is_zero():
    with pytest.raises(ValueError):
        split_service_charge(10000, 0, 10, 100)


def test_split_service_charge_raises_value_error_when_bill_is_negative():
    with pytest.raises(ValueError):
        split_service_charge(-1, 3, 10, 100)


def test_split_service_charge_raises_value_error_when_charge_percent_is_negative():
    with pytest.raises(ValueError):
        split_service_charge(10000, 3, -1, 100)


def test_split_service_charge_raises_value_error_when_unit_is_zero():
    with pytest.raises(ValueError):
        split_service_charge(10000, 3, 10, 0)
