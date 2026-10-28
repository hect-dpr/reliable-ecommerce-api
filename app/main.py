from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import AppError
from app.routers import carts, products


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.db import Base, SessionLocal, engine
    from app.seed import seed_products

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_products(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Checkout and Rewards API",
    description="Carts, checkout, inventory, and milestone coupons.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "detail": exc.detail},
    )


app.include_router(products.router)
app.include_router(carts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
