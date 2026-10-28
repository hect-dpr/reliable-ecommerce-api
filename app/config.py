import os

# Every Nth successful order unlocks one coupon for X% off.
COUPON_ORDER_INTERVAL = int(os.getenv("COUPON_ORDER_INTERVAL", "5"))
COUPON_DISCOUNT_PERCENT = int(os.getenv("COUPON_DISCOUNT_PERCENT", "10"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ecommerce.db")
