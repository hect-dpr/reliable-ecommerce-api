from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product
from app.schemas import ProductOut
from app.serializers import product_out

router = APIRouter(tags=["products"])


@router.get("/products", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    """List products (handy for finding seed IDs)."""
    products = db.query(Product).order_by(Product.id).all()
    return [product_out(p) for p in products]
