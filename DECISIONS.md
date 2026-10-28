# Design Decisions

## Rules we keep true

1. **No oversell** — stock never goes below zero. Checkout fails if there is not enough.
2. **One checkout per cart** — `orders.cart_id` is unique; the cart is marked checked out in the same transaction.
3. **Safe retries** — the same `Idempotency-Key` always returns the same order. Stock and coupons are only touched once.
4. **Coupons used once** — a coupon flips to redeemed only if checkout commits. A failed checkout does not spend it.
5. **One coupon per milestone** — milestones are `n`, `2n`, `3n`, …. We never invent a coupon early.
6. **Orders keep history** — line items store name, price, qty, and line total as they were at checkout.
7. **Totals stay sensible** — `total = subtotal - discount`, and discount is never bigger than subtotal.
8. **Reports do not write** — `GET /admin/report` only reads.

## Things that were unclear, and what we picked

| Question | What we do |
|---|---|
| Price or stock changes after add-to-cart | Cart shows **current** price/stock. At checkout we check stock again and **copy** the price onto the order. If stock is short, checkout fails. |
| Hold stock when adding to cart? | **No.** Add-to-cart only warns. Real stock change happens at checkout. Two carts can both hold the last unit; one wins. |
| Who creates coupons? | **Admin** via `POST /admin/coupons`. Hitting a milestone makes a coupon *allowed*, not automatic. |
| Several milestones waiting? | Oldest first (reward 5 before 10). |
| Multiple coupons on one order? | One code per checkout. |
| What is the discount on? | Percent off the order subtotal. |
| Payment? | A successful checkout counts as paid. No payment provider. |
| Bad coupon at checkout? | Fail the whole checkout. Do not place the order without the discount. |

---

## Decision: Money in paise (INR)

**Context:** Avoid float rounding; use Indian currency.

**Options considered:** Floats; Decimal; integer cents; integer paise.

**Choice:** Store and return integer paise (`*_paise`). Discount uses integer division. Display strings look like `₹12.99`.

**Why:** Exact and easy to test. Display is just formatting, not the source of truth.

**Consequences:** Clients work in paise. GST / other currencies later if needed.

---

## Decision: SQLite `BEGIN IMMEDIATE` for checkout and coupon create

**Context:** Two checkouts at once must not oversell or both redeem one coupon.

**Options considered:** Version numbers + retry; only `SELECT FOR UPDATE`; `BEGIN IMMEDIATE`; an in-process lock.

**Choice:** Every SQLite transaction starts with `BEGIN IMMEDIATE` (via SQLAlchemy events). Checkout and coupon create call `begin_immediate()` first. WAL and `busy_timeout` let the other writer wait. App checks still apply; DB also has `CHECK (inventory >= 0)`.

**Why:** SQLite writers take a DB-wide write lock. Taking it before reading stock/coupon closes the race. (The pysqlite dialect here does not accept `isolation_level="IMMEDIATE"` as an execution option, so we use events + SQL.)

**Consequences:** Writers line up on one process — fine for this assignment. Several app instances need a real server DB and row locks.

---

## Decision: Client sends `Idempotency-Key` on checkout

**Context:** Clients retry when they time out. A retry must not create a second order.

**Options considered:** Use cart id only; server-made tokens; required `Idempotency-Key` header.

**Choice:** Required header, unique in the DB. Same key → same order. Different key on an already-checked-out cart → `409 cart_already_checked_out`.

**Why:** Cart id alone cannot tell “retry” from “new attempt after a lost response.” Explicit keys are the usual pattern for payments-style APIs.

**Consequences:** Clients must keep the key for retries. Keys are unique across the whole system.

---

## Decision: Cart shows live prices; order freezes them

**Context:** Catalog price/name can change after add-to-cart or after purchase.

**Options considered:** Freeze at add-to-cart; freeze at checkout; always charge live price with no copy on the order.

**Choice:** Cart uses live catalog. Checkout copies name + unit price onto `order_items`.

**Why:** You pay what was true when you bought. Old orders still make sense after catalog edits.

**Consequences:** Cart totals can change between views. No price-match promise.

---

## Decision: Admin creates milestone coupons

**Context:** Every *n*th successful order should unlock a coupon, once per milestone.

**Options considered:** Auto-create inside checkout; admin creates them; pre-create a pool.

**Choice:** Checkout only creates orders (which raises the count). Admin `POST /admin/coupons` creates one coupon when enough orders exist and that milestone has no row yet. Unique `milestone` enforces once.

**Why:** Matches the required admin step, keeps checkout smaller, and is easy to test.

**Consequences:** Shoppers do not get a coupon the instant the milestone order lands unless an admin generates it.

---

## How checkout works (one transaction)

After `BEGIN IMMEDIATE`:

1. If this idempotency key already has an order, return it.
2. Load cart; reject empty or already checked out.
3. Check product stock; fail if short.
4. If a coupon is given, load it; fail if missing or already used; compute discount.
5. Insert order + line items (copied prices).
6. Reduce stock; mark coupon redeemed; mark cart checked out.
7. Commit. If a unique-key race happens, look up by idempotency key and return that order.

Coupon use and stock change commit with the order — a failed checkout never spends a coupon.

## Errors

JSON has an `error` code and a `detail` message. Bad input → **400**. Missing thing → **404**. Conflict / race → **409**.

## Done vs skipped

**Done:** products, carts, checkout, orders, paise money, safe retries, stock checks, coupons, admin report, concurrent tests, SQLite WAL + IMMEDIATE.

**Skipped for time:** auth, real payments/refunds, holding stock on add-to-cart, multi-instance setup, Alembic migrations, coupon expiry, per-customer limits, logging/metrics, rate limits.

## If we ran more than one server

- Use PostgreSQL (or similar).
- Use row locks (`SELECT … FOR UPDATE`) on products and coupons instead of DB-wide `BEGIN IMMEDIATE`.
- Keep unique constraints on idempotency key, cart id, and coupon milestone.
- Keep checkout as one DB transaction.

## How AI was used

AI helped with first-pass layout and a draft of this file.

**Where I pushed back:** An early draft used float prices and reserved stock on add-to-cart. That was dropped — floats break the money rule, and soft holds were extra complexity. We kept integer paise and check stock at checkout.

Also pushed back on auto-creating coupons inside checkout; admin generation matches the brief better.

## If I had two more hours

1. More concurrent cases (last unit, coupon + oversell together).
2. Alembic + a Postgres path to show row locks.
3. Clearer error when an idempotency key is reused with a different cart.
4. Simple request logging for debugging retries.
