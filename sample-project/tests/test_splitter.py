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
