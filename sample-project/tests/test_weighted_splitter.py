import pytest

from expense.weighted_splitter import split_by_weights


def test_split_by_weights_returns_exact_shares_when_evenly_divisible():
    assert split_by_weights(100, [1, 1, 2]) == [25, 25, 50]


def test_split_by_weights_returns_one_amount_per_weight():
    assert len(split_by_weights(11, [0, 1, 2])) == 3


def test_split_by_weights_gives_nothing_to_person_with_zero_weight():
    assert split_by_weights(11, [0, 1, 2])[0] == 0


def test_split_by_weights_does_not_exceed_ideal_share_by_more_than_one_won():
    weights = [1, 2, 4]
    total_weight = sum(weights)
    result = split_by_weights(10, weights)
    for share, weight in zip(result, weights):
        assert share <= 10 * weight // total_weight + 1


def test_split_by_weights_raises_value_error_when_weights_are_empty():
    with pytest.raises(ValueError):
        split_by_weights(10000, [])


def test_split_by_weights_raises_value_error_when_weight_is_negative():
    with pytest.raises(ValueError):
        split_by_weights(10000, [1, -1])


def test_split_by_weights_raises_value_error_when_total_weight_is_zero():
    with pytest.raises(ValueError):
        split_by_weights(10000, [0, 0])


def test_split_by_weights_raises_value_error_when_amount_is_negative():
    with pytest.raises(ValueError):
        split_by_weights(-1, [1, 2])


def test_split_by_weights_preserves_total_when_not_evenly_divisible():
    assert sum(split_by_weights(10, [1, 2, 4])) == 10


def test_split_by_weights_preserves_total_when_someone_has_zero_weight():
    assert sum(split_by_weights(11, [0, 1, 2])) == 11


def test_split_by_weights_gives_remainder_to_largest_fraction_first():
    assert split_by_weights(10, [1, 2, 4]) == [1, 3, 6]


def test_split_by_weights_gives_remainder_to_earlier_person_when_fractions_tie():
    assert split_by_weights(10, [1, 1, 1]) == [4, 3, 3]


def test_split_by_weights_returns_all_zero_shares_when_amount_is_zero():
    assert split_by_weights(0, [1, 2, 4]) == [0, 0, 0]
