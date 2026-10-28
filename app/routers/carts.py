from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CartItemIn, CartItemUpdate, CartOut
from app.services import carts as cart_service

router = APIRouter(tags=["carts"])


@router.post("/carts", response_model=CartOut, status_code=201)
def create_cart(db: Session = Depends(get_db)):
    return cart_service.create_cart(db)


@router.get("/carts/{cart_id}", response_model=CartOut)
def get_cart(cart_id: int, db: Session = Depends(get_db)):
    return cart_service.get_cart(db, cart_id)


@router.post("/carts/{cart_id}/items", response_model=CartOut)
def add_item(cart_id: int, body: CartItemIn, db: Session = Depends(get_db)):
    return cart_service.add_item(db, cart_id, body.product_id, body.quantity)


@router.put("/carts/{cart_id}/items/{product_id}", response_model=CartOut)
def update_item(
    cart_id: int,
    product_id: int,
    body: CartItemUpdate,
    db: Session = Depends(get_db),
):
    return cart_service.update_item(db, cart_id, product_id, body.quantity)


@router.delete("/carts/{cart_id}/items/{product_id}", response_model=CartOut)
def remove_item(cart_id: int, product_id: int, db: Session = Depends(get_db)):
    return cart_service.remove_item(db, cart_id, product_id)
