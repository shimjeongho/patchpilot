from expense.formatter import format_split


def test_format_split_numbers_each_person_from_one():
    result = format_split([3334, 3333, 3333])
    assert result == "1번: 3,334원\n2번: 3,333원\n3번: 3,333원"


def test_format_split_adds_thousands_separator():
    assert format_split([1234567]) == "1번: 1,234,567원"


def test_format_split_keeps_small_amount_without_separator():
    assert format_split([0, 999]) == "1번: 0원\n2번: 999원"
