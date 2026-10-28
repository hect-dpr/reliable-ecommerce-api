import pytest

from app.money import apply_percent_discount, format_paise


def test_discount_floors_and_never_exceeds_subtotal():
    assert apply_percent_discount(1299, 10) == 129
    assert apply_percent_discount(1, 10) == 0
    assert apply_percent_discount(100, 100) == 100
    assert apply_percent_discount(0, 10) == 0


def test_discount_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        apply_percent_discount(-1, 10)
    with pytest.raises(ValueError):
        apply_percent_discount(100, 101)


def test_format_paise():
    assert format_paise(1299) == "₹12.99"
    assert format_paise(0) == "₹0.00"
    assert format_paise(5) == "₹0.05"
