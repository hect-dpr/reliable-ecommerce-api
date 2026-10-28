from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app import errors
from app.db import begin_immediate
from app.models import (
    Cart,
    CartStatus,
    Coupon,
    CouponStatus,
    Order,
    OrderItem,
    Product,
)
from app.money import apply_percent_discount
from app.serializers import order_out


def get_order(db, order_id):
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order_id)
        .one_or_none()
    )
    if order is None:
        raise errors.not_found("order_not_found", "Order {} does not exist".format(order_id))
    return order_out(order)


def checkout(db, cart_id, idempotency_key, coupon_code=None):
    if not idempotency_key or not idempotency_key.strip():
        raise errors.bad_request(
            "missing_idempotency_key",
            "Idempotency-Key header is required for checkout",
        )
    idempotency_key = idempotency_key.strip()

    # Already succeeded with this key? Return that order.
    existing = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        return order_out(existing)

    try:
        begin_immediate(db)

        # Check again after taking the write lock (another request may have won).
        existing = (
            db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            db.commit()
            return order_out(existing)

        cart = (
            db.query(Cart)
            .options(joinedload(Cart.items))
            .filter(Cart.id == cart_id)
            .one_or_none()
        )
        if cart is None:
            db.rollback()
            raise errors.not_found(
                "cart_not_found",
                "Cart {} does not exist".format(cart_id),
            )
        if cart.status == CartStatus.checked_out:
            db.rollback()
            raise errors.conflict(
                "cart_already_checked_out",
                "Cart {} has already been checked out".format(cart_id),
            )
        if not cart.items:
            db.rollback()
            raise errors.bad_request("empty_cart", "Cannot check out an empty cart")

        product_ids = [item.product_id for item in cart.items]
        products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids))
            .with_for_update()
            .all()
        )
        products_by_id = {p.id: p for p in products}

        order_items_data = []
        subtotal = 0
        for item in cart.items:
            product = products_by_id.get(item.product_id)
            if product is None:
                db.rollback()
                raise errors.bad_request(
                    "invalid_product",
                    "Product {} does not exist".format(item.product_id),
                )
            if item.quantity > product.inventory:
                db.rollback()
                raise errors.conflict(
                    "insufficient_inventory",
                    "Product {} has only {} in stock (requested {})".format(
                        product.id, product.inventory, item.quantity
                    ),
                )
            line_total = product.unit_price_paise * item.quantity
            subtotal += line_total
            order_items_data.append(
                {
                    "product": product,
                    "quantity": item.quantity,
                    "unit_price_paise": product.unit_price_paise,
                    "line_total_paise": line_total,
                }
            )

        discount = 0
        coupon = None
        if coupon_code:
            coupon = (
                db.query(Coupon)
                .filter(Coupon.code == coupon_code)
                .with_for_update()
                .one_or_none()
            )
            if coupon is None:
                db.rollback()
                raise errors.bad_request(
                    "invalid_coupon",
                    "Coupon '{}' does not exist".format(coupon_code),
                )
            if coupon.status != CouponStatus.available:
                db.rollback()
                raise errors.conflict(
                    "coupon_already_redeemed",
                    "Coupon '{}' has already been redeemed".format(coupon_code),
                )
            discount = apply_percent_discount(subtotal, coupon.discount_percent)

        total = subtotal - discount

        # No real payment gateway — a successful checkout counts as paid.
        order = Order(
            cart_id=cart.id,
            idempotency_key=idempotency_key,
            subtotal_paise=subtotal,
            discount_paise=discount,
            total_paise=total,
            coupon_code=coupon.code if coupon else None,
        )
        db.add(order)
        db.flush()

        for row in order_items_data:
            product = row["product"]
            product.inventory -= row["quantity"]
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    unit_price_paise=row["unit_price_paise"],
                    quantity=row["quantity"],
                    line_total_paise=row["line_total_paise"],
                )
            )

        if coupon is not None:
            coupon.status = CouponStatus.redeemed
            coupon.redeemed_order_id = order.id

        cart.status = CartStatus.checked_out
        db.commit()
    except IntegrityError:
        db.rollback()
        # Two requests raced on the same key; return the order that landed.
        existing = (
            db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return order_out(existing)
        raise errors.conflict(
            "checkout_conflict",
            "Checkout conflicted with another request; retry with the same Idempotency-Key",
        )
    except errors.AppError:
        raise
    except Exception:
        db.rollback()
        raise

    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order.id)
        .one()
    )
    return order_out(order)
