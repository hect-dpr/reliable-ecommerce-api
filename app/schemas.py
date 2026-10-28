from typing import List, Optional

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: int
    name: str
    unit_price_paise: int
    unit_price_display: str
    inventory: int


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0)


class CartItemOut(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price_paise: int
    unit_price_display: str
    line_total_paise: int
    line_total_display: str
    available_inventory: int


class CartOut(BaseModel):
    id: int
    status: str
    items: List[CartItemOut]
    subtotal_paise: int
    subtotal_display: str


class CheckoutIn(BaseModel):
    coupon_code: Optional[str] = None


class OrderItemOut(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price_paise: int
    unit_price_display: str
    line_total_paise: int
    line_total_display: str


class OrderOut(BaseModel):
    id: int
    cart_id: int
    items: List[OrderItemOut]
    subtotal_paise: int
    subtotal_display: str
    discount_paise: int
    discount_display: str
    total_paise: int
    total_display: str
    coupon_code: Optional[str] = None


class CouponOut(BaseModel):
    code: str
    discount_percent: int
    milestone: int
    status: str


class ProductSalesOut(BaseModel):
    product_id: int
    product_name: str
    quantity_sold: int


class ReportOut(BaseModel):
    products: List[ProductSalesOut]
    gross_revenue_paise: int
    gross_revenue_display: str
    total_discounts_paise: int
    total_discounts_display: str
    net_revenue_paise: int
    net_revenue_display: str
    coupons_generated: int
    coupons_available: int
    coupons_redeemed: int
    total_orders: int


class ErrorOut(BaseModel):
    error: str
    detail: str
