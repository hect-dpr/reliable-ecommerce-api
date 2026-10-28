from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CouponOut, ReportOut
from app.services import coupons as coupon_service
from app.services import report as report_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/coupons", response_model=CouponOut, status_code=201)
def generate_coupon(db: Session = Depends(get_db)):
    """Admin: create a coupon when the next order milestone is due."""
    return coupon_service.generate_coupon(db)


@router.get("/report", response_model=ReportOut)
def get_report(db: Session = Depends(get_db)):
    """Admin: sales and coupon summary (read-only)."""
    return report_service.build_report(db)
