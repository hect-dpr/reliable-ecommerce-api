from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import OrderOut
from app.services import checkout as checkout_service

router = APIRouter(tags=["orders"])


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return checkout_service.get_order(db, order_id)
