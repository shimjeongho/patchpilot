import pytest

from expense.settlement import settle_by_unit


def test_settle_returns_equal_shares_when_amount_is_evenly_divisible():
    assert settle_by_unit(900, 3, 100) == ([300, 300, 300], 0)


def test_settle_returns_one_share_per_person():
    shares, _ = settle_by_unit(1400, 4, 100)
    assert len(shares) == 4


def test_settle_gives_every_share_as_multiple_of_unit():
    shares, _ = settle_by_unit(1400, 4, 100)
    assert all(share % 100 == 0 for share in shares)


def test_settle_preserves_total_including_change():
    shares, change = settle_by_unit(1400, 4, 100)
    assert sum(shares) + change == 1400


def test_settle_returns_change_smaller_than_unit_when_amount_is_not_multiple_of_unit():
    assert settle_by_unit(1250, 4, 100)[1] == 50


def test_settle_returns_zero_shares_when_amount_is_smaller_than_unit():
    assert settle_by_unit(50, 3, 100) == ([0, 0, 0], 50)


def test_settle_gives_entire_amount_to_single_person():
    assert settle_by_unit(1000, 1, 100) == ([1000], 0)


def test_settle_raises_value_error_when_people_is_zero():
    with pytest.raises(ValueError):
        settle_by_unit(1000, 0, 100)


def test_settle_raises_value_error_when_unit_is_zero():
    with pytest.raises(ValueError):
        settle_by_unit(1000, 3, 0)


def test_settle_raises_value_error_when_amount_is_negative():
    with pytest.raises(ValueError):
        settle_by_unit(-1, 3, 100)


def test_settle_leaves_change_below_unit_when_units_do_not_divide_evenly():
    assert settle_by_unit(1400, 4, 100)[1] < 100


def test_settle_distributes_remaining_units_to_earlier_people_first():
    assert settle_by_unit(1400, 4, 100)[0] == [400, 400, 300, 300]


def test_settle_distributes_single_remaining_unit_to_first_person():
    assert settle_by_unit(1000, 3, 100) == ([400, 300, 300], 0)


def test_settle_difference_between_people_is_at_most_one_unit():
    shares, _ = settle_by_unit(1400, 4, 100)
    assert max(shares) - min(shares) <= 100


def test_settle_matches_plain_split_when_unit_is_one_won():
    assert settle_by_unit(10, 3, 1) == ([4, 3, 3], 0)
