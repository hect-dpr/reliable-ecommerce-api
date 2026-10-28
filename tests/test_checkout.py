def _create_cart_with_item(client, product_id=1, quantity=1):
    cart_id = client.post("/carts").json()["id"]
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": product_id, "quantity": quantity},
    )
    return cart_id


def test_checkout_creates_order_and_decrements_inventory(client):
    before = client.get("/products").json()
    poster = next(p for p in before if p["id"] == 5)
    assert poster["inventory"] == 2

    cart_id = _create_cart_with_item(client, product_id=5, quantity=1)
    resp = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": "order-1"},
    )
    assert resp.status_code == 200
    order = resp.json()
    assert order["subtotal_paise"] == 2999
    assert order["discount_paise"] == 0
    assert order["total_paise"] == 2999
    assert order["items"][0]["product_name"] == "Limited Edition Poster"

    after = client.get("/products").json()
    poster_after = next(p for p in after if p["id"] == 5)
    assert poster_after["inventory"] == 1

    cart = client.get("/carts/{}".format(cart_id)).json()
    assert cart["status"] == "checked_out"


def test_checkout_idempotent_retry_same_key(client):
    cart_id = _create_cart_with_item(client, product_id=1, quantity=1)
    headers = {"Idempotency-Key": "retry-same"}
    first = client.post("/carts/{}/checkout".format(cart_id), json={}, headers=headers)
    second = client.post("/carts/{}/checkout".format(cart_id), json={}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    products = client.get("/products").json()
    mug = next(p for p in products if p["id"] == 1)
    assert mug["inventory"] == 99  # decremented once


def test_checkout_rejects_second_key_on_same_cart(client):
    cart_id = _create_cart_with_item(client, product_id=1, quantity=1)
    client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": "first-key"},
    )
    resp = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": "second-key"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "cart_already_checked_out"


def test_checkout_requires_idempotency_key(client):
    cart_id = _create_cart_with_item(client)
    resp = client.post("/carts/{}/checkout".format(cart_id), json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_idempotency_key"


def test_order_snapshots_price_after_product_change(client):
    cart_id = _create_cart_with_item(client, product_id=1, quantity=1)
    order = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": "snap-1"},
    ).json()
    assert order["items"][0]["unit_price_paise"] == 1299

    # Mutate live product price; historical order must be unchanged.
    from app.db import SessionLocal
    from app.models import Product

    db = SessionLocal()
    product = db.query(Product).filter(Product.id == 1).one()
    product.unit_price_paise = 9999
    db.commit()
    db.close()

    fetched = client.get("/orders/{}".format(order["id"])).json()
    assert fetched["items"][0]["unit_price_paise"] == 1299
    assert fetched["total_paise"] == 1299
