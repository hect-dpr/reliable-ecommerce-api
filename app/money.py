# Money is stored as integer paise (100 paise = ₹1). Do not use floats.


def apply_percent_discount(subtotal_paise, discount_percent):
    """Discount in paise, rounded down. Never more than the subtotal."""
    if subtotal_paise < 0:
        raise ValueError("subtotal_paise must be non-negative")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount_percent must be between 0 and 100")
    discount = (subtotal_paise * discount_percent) // 100
    return min(discount, subtotal_paise)


def format_paise(paise):
    """Turn paise into a display string like ₹12.99."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return "{}₹{}.{:02d}".format(sign, paise // 100, paise % 100)
