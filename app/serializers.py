from app.money import format_paise


def product_out(product):
    return {
        "id": product.id,
        "name": product.name,
        "unit_price_paise": product.unit_price_paise,
        "unit_price_display": format_paise(product.unit_price_paise),
        "inventory": product.inventory,
    }


def cart_out(cart, products_by_id):
    items = []
    subtotal = 0
    for item in cart.items:
        product = products_by_id[item.product_id]
        line_total = product.unit_price_paise * item.quantity
        subtotal += line_total
        items.append(
            {
                "product_id": item.product_id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price_paise": product.unit_price_paise,
                "unit_price_display": format_paise(product.unit_price_paise),
                "line_total_paise": line_total,
                "line_total_display": format_paise(line_total),
                "available_inventory": product.inventory,
            }
        )
    return {
        "id": cart.id,
        "status": cart.status.value,
        "items": items,
        "subtotal_paise": subtotal,
        "subtotal_display": format_paise(subtotal),
    }


def order_out(order):
    items = []
    for item in order.items:
        items.append(
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price_paise": item.unit_price_paise,
                "unit_price_display": format_paise(item.unit_price_paise),
                "line_total_paise": item.line_total_paise,
                "line_total_display": format_paise(item.line_total_paise),
            }
        )
    return {
        "id": order.id,
        "cart_id": order.cart_id,
        "items": items,
        "subtotal_paise": order.subtotal_paise,
        "subtotal_display": format_paise(order.subtotal_paise),
        "discount_paise": order.discount_paise,
        "discount_display": format_paise(order.discount_paise),
        "total_paise": order.total_paise,
        "total_display": format_paise(order.total_paise),
        "coupon_code": order.coupon_code,
    }


def coupon_out(coupon):
    return {
        "code": coupon.code,
        "discount_percent": coupon.discount_percent,
        "milestone": coupon.milestone,
        "status": coupon.status.value,
    }
