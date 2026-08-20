import pytest

from expense.charge_rounding import round_to_unit


def test_round_to_unit_rounds_up_when_amount_is_not_on_the_unit_boundary():
    assert round_to_unit(10050, 100) == 10100


def test_round_to_unit_rounds_up_even_when_remainder_is_one_won():
    assert round_to_unit(10001, 100) == 10100


def test_round_to_unit_rounds_up_even_when_remainder_is_almost_a_full_unit():
    assert round_to_unit(10099, 100) == 10100


def test_round_to_unit_returns_amount_when_it_is_already_on_the_unit_boundary():
    assert round_to_unit(10100, 100) == 10100


def test_round_to_unit_returns_amount_when_unit_is_one_won():
    assert round_to_unit(10057, 1) == 10057


def test_round_to_unit_returns_zero_when_amount_is_zero():
    assert round_to_unit(0, 100) == 0


def test_round_to_unit_never_returns_less_than_the_original_amount():
    for amount in range(0, 1000, 7):
        assert round_to_unit(amount, 100) >= amount, amount


def test_round_to_unit_raises_value_error_when_unit_is_zero():
    with pytest.raises(ValueError):
        round_to_unit(10000, 0)


def test_round_to_unit_raises_value_error_when_unit_is_negative():
    with pytest.raises(ValueError):
        round_to_unit(10000, -100)


def test_round_to_unit_raises_value_error_when_amount_is_negative():
    with pytest.raises(ValueError):
        round_to_unit(-1, 100)
