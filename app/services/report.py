from sqlalchemy import func

from app.models import Coupon, CouponStatus, Order, OrderItem, Product
from app.money import format_paise


def build_report(db):
    """Sales summary. Does not change any data."""
    product_rows = (
        db.query(
            OrderItem.product_id,
            OrderItem.product_name,
            func.sum(OrderItem.quantity),
        )
        .group_by(OrderItem.product_id, OrderItem.product_name)
        .order_by(OrderItem.product_id)
        .all()
    )
    # Use the live product name if the product still exists.
    names = {p.id: p.name for p in db.query(Product).all()}
    products = []
    for product_id, old_name, qty in product_rows:
        products.append(
            {
                "product_id": product_id,
                "product_name": names.get(product_id, old_name),
                "quantity_sold": int(qty or 0),
            }
        )

    totals = db.query(
        func.coalesce(func.sum(Order.subtotal_paise), 0),
        func.coalesce(func.sum(Order.discount_paise), 0),
        func.coalesce(func.sum(Order.total_paise), 0),
        func.count(Order.id),
    ).one()
    gross, discounts, net, order_count = [int(v) for v in totals]

    coupons_generated = db.query(Coupon).count()
    coupons_available = (
        db.query(Coupon).filter(Coupon.status == CouponStatus.available).count()
    )
    coupons_redeemed = (
        db.query(Coupon).filter(Coupon.status == CouponStatus.redeemed).count()
    )

    return {
        "products": products,
        "gross_revenue_paise": gross,
        "gross_revenue_display": format_paise(gross),
        "total_discounts_paise": discounts,
        "total_discounts_display": format_paise(discounts),
        "net_revenue_paise": net,
        "net_revenue_display": format_paise(net),
        "coupons_generated": coupons_generated,
        "coupons_available": coupons_available,
        "coupons_redeemed": coupons_redeemed,
        "total_orders": order_count,
    }
