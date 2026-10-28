import secrets

from app import errors
from app.config import COUPON_DISCOUNT_PERCENT, COUPON_ORDER_INTERVAL
from app.db import begin_immediate
from app.models import Coupon, Order
from app.serializers import coupon_out


def _next_eligible_milestone(db):
    """Smallest milestone (n, 2n, ...) we have enough orders for, but no coupon yet."""
    order_count = db.query(Order).count()
    n = COUPON_ORDER_INTERVAL
    if n <= 0:
        raise errors.bad_request("invalid_config", "COUPON_ORDER_INTERVAL must be positive")

    already_made = {row[0] for row in db.query(Coupon.milestone).all()}
    milestone = n
    while milestone <= order_count:
        if milestone not in already_made:
            return milestone
        milestone += n
    return None


def generate_coupon(db):
    """Admin: make one coupon for the next open milestone."""
    begin_immediate(db)
    try:
        milestone = _next_eligible_milestone(db)
        if milestone is None:
            order_count = db.query(Order).count()
            db.rollback()
            raise errors.conflict(
                "no_eligible_milestone",
                "No coupon to generate yet (orders={}, every {}th order)".format(
                    order_count, COUPON_ORDER_INTERVAL
                ),
            )

        code = "SAVE-{}".format(secrets.token_hex(4).upper())
        coupon = Coupon(
            code=code,
            discount_percent=COUPON_DISCOUNT_PERCENT,
            milestone=milestone,
        )
        db.add(coupon)
        db.commit()
        db.refresh(coupon)
        return coupon_out(coupon)
    except errors.AppError:
        raise
    except Exception:
        db.rollback()
        raise
