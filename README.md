# Checkout and Rewards API

FastAPI + SQLite: carts, checkout, stock, and discount coupons.

## Setup

Requires Python 3.8+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Service listens on `http://127.0.0.1:8000`. Interactive docs: `/docs`.

On startup the app creates tables and seeds five products (including one with limited inventory).

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `COUPON_ORDER_INTERVAL` (`n`) | `5` | Every *n*th successful order unlocks one coupon |
| `COUPON_DISCOUNT_PERCENT` (`x`) | `10` | Coupon discount percent |
| `DATABASE_URL` | `sqlite:///./ecommerce.db` | SQLAlchemy database URL |

## Seed products

| ID | Name | Price | Inventory |
|---|---|---|---|
| 1 | Ceramic Mug | ₹12.99 | 100 |
| 2 | Notebook | ₹8.99 | 50 |
| 3 | Desk Lamp | ₹45.99 | 25 |
| 4 | USB-C Cable | ₹14.99 | 200 |
| 5 | Limited Edition Poster | ₹29.99 | 2 |

`GET /products` lists the live catalog.

## Money

Currency is **INR**. Amounts are integer **paise** (`*_paise`; 100 paise = ₹1). `*_display` is just for reading (e.g. `"₹12.99"`). Discount: `(subtotal_paise * percent) // 100`.

## Admin endpoints

No auth. Treat these as admin-only:

- `POST /admin/coupons`
- `GET /admin/report`

## API

Errors look like `{"error": "<code>", "detail": "<message>"}`.

### `GET /products`

**200** — list of products with `id`, `name`, `unit_price_paise`, `unit_price_display`, `inventory`.

### `POST /carts`

**201** — creates an empty open cart.

### `GET /carts/{cart_id}`

**200** — cart with line items priced at **current** catalog prices, plus `subtotal_paise`.

**404** `cart_not_found`

### `POST /carts/{cart_id}/items`

Body: `{"product_id": int, "quantity": int}` (`quantity > 0`).

**200** — updated cart. Adding an existing product increases its quantity.

**400** `invalid_product` | `invalid_quantity` | `insufficient_inventory`

**409** `cart_checked_out`

**404** `cart_not_found`

### `PUT /carts/{cart_id}/items/{product_id}`

Body: `{"quantity": int}` (`quantity > 0`).

**200** — updated cart.

**400** `insufficient_inventory` | `invalid_product`

**404** `cart_not_found` | `cart_item_not_found`

**409** `cart_checked_out`

### `DELETE /carts/{cart_id}/items/{product_id}`

**200** — updated cart.

**404** `cart_not_found` | `cart_item_not_found`

**409** `cart_checked_out`

### `POST /carts/{cart_id}/checkout`

Headers: `Idempotency-Key` (required).

Body (optional): `{"coupon_code": "SAVE-..."}`.

**200** — order. Checkout success counts as paid (no payment provider).

Price and name are copied onto the order. Stock goes down in the same transaction. A coupon is only marked used if that commit succeeds.

Retry with the **same** `Idempotency-Key` returns the same order and does not touch stock again.

**400** `missing_idempotency_key` | `empty_cart` | `invalid_product` | `invalid_coupon`

**409** `cart_already_checked_out` | `insufficient_inventory` | `coupon_already_redeemed` | `checkout_conflict`

**404** `cart_not_found`

### `GET /orders/{order_id}`

**200** — order with the line items and totals saved at checkout.

**404** `order_not_found`

### `POST /admin/coupons` *(admin)*

Creates one coupon for the next due milestone (`n`, `2n`, …) when enough orders exist.

**201** — `{code, discount_percent, milestone, status}`

**409** `no_eligible_milestone`

### `GET /admin/report` *(admin)*

Read-only summary. Calling it again does not change anything.

```json
{
  "products": [{"product_id": 1, "product_name": "...", "quantity_sold": 2}],
  "gross_revenue_paise": 2598,
  "total_discounts_paise": 0,
  "net_revenue_paise": 2598,
  "coupons_generated": 0,
  "coupons_available": 0,
  "coupons_redeemed": 0,
  "total_orders": 1
}
```

(Display string fields are also included.)

## Example session

```bash
# Create cart and add the limited poster
curl -s -X POST http://127.0.0.1:8000/carts
curl -s -X POST http://127.0.0.1:8000/carts/1/items \
  -H 'Content-Type: application/json' \
  -d '{"product_id": 5, "quantity": 1}'

# Checkout (safe to retry with the same key)
curl -s -X POST http://127.0.0.1:8000/carts/1/checkout \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{}'

# After 5 orders, generate a coupon
curl -s -X POST http://127.0.0.1:8000/admin/coupons

# Report
curl -s http://127.0.0.1:8000/admin/report
```

## Tests

```bash
pytest -q
```

Covers carts, checkout retries, coupons, reporting, and concurrent oversell / retry / coupon races.

Also: `python scripts/verify_requirements.py` hits the live HTTP API with `requests`.

## Design notes

See [`DECISIONS.md`](DECISIONS.md).
