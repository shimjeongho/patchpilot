import pytest

from expense.splitter import split_amount


def test_split_returns_equal_amounts_when_evenly_divisible():
    assert split_amount(9000, 3) == [3000, 3000, 3000]


def test_split_returns_one_amount_per_person():
    assert len(split_amount(10000, 3)) == 3


def test_split_preserves_total():
    result = split_amount(10000, 3)
    assert sum(result) == 10000


def test_split_difference_between_people_is_at_most_one():
    result = split_amount(10000, 3)
    assert max(result) - min(result) <= 1


def test_split_raises_value_error_when_people_is_zero():
    with pytest.raises(ValueError):
        split_amount(10000, 0)


def test_split_raises_value_error_when_people_is_negative():
    with pytest.raises(ValueError):
        split_amount(10000, -1)


def test_split_raises_value_error_when_amount_is_negative():
    with pytest.raises(ValueError):
        split_amount(-1, 3)


def test_split_preserves_total_when_remainder_is_greater_than_one():
    result = split_amount(10, 4)
    assert sum(result) == 10


def test_split_distributes_remainder_to_earlier_people_first():
    assert split_amount(10000, 3) == [3334, 3333, 3333]


def test_split_gives_entire_amount_to_single_person():
    assert split_amount(10000, 1) == [10000]


def test_split_returns_zero_for_everyone_when_amount_is_zero():
    assert split_amount(0, 3) == [0, 0, 0]
