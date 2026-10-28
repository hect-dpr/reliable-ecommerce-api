import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class CartStatus(str, enum.Enum):
    open = "open"
    checked_out = "checked_out"


class CouponStatus(str, enum.Enum):
    available = "available"
    redeemed = "redeemed"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("inventory >= 0", name="ck_product_inventory"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    unit_price_paise = Column(Integer, nullable=False)
    inventory = Column(Integer, nullable=False)

    def __repr__(self):
        return "<Product id={} inventory={}>".format(self.id, self.inventory)


class Cart(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True)
    status = Column(
        Enum(CartStatus, native_enum=False),
        nullable=False,
        default=CartStatus.open,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
    order = relationship("Order", back_populates="cart", uselist=False)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),)

    id = Column(Integer, primary_key=True)
    cart_id = Column(Integer, ForeignKey("carts.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    cart_id = Column(Integer, ForeignKey("carts.id"), nullable=False, unique=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    subtotal_paise = Column(Integer, nullable=False)
    discount_paise = Column(Integer, nullable=False, default=0)
    total_paise = Column(Integer, nullable=False)
    coupon_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    cart = relationship("Cart", back_populates="order")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(200), nullable=False)
    unit_price_paise = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    line_total_paise = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), nullable=False, unique=True)
    discount_percent = Column(Integer, nullable=False)
    # Which order count this coupon is for (5, 10, 15, ...).
    milestone = Column(Integer, nullable=False, unique=True)
    status = Column(
        Enum(CouponStatus, native_enum=False),
        nullable=False,
        default=CouponStatus.available,
    )
    redeemed_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
