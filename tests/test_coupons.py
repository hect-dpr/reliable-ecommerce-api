def _place_order(client, key, product_id=1):
    cart_id = client.post("/carts").json()["id"]
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": product_id, "quantity": 1},
    )
    return client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": key},
    )


def test_coupon_not_generated_before_milestone(client):
    for i in range(4):
        assert _place_order(client, "pre-{}".format(i)).status_code == 200
    resp = client.post("/admin/coupons")
    assert resp.status_code == 409
    assert resp.json()["error"] == "no_eligible_milestone"


def test_coupon_generated_at_milestone_once(client):
    for i in range(5):
        assert _place_order(client, "mile-{}".format(i)).status_code == 200

    first = client.post("/admin/coupons")
    assert first.status_code == 201
    coupon = first.json()
    assert coupon["milestone"] == 5
    assert coupon["discount_percent"] == 10
    assert coupon["status"] == "available"

    second = client.post("/admin/coupons")
    assert second.status_code == 409
    assert second.json()["error"] == "no_eligible_milestone"


def test_coupon_applied_at_checkout(client):
    for i in range(5):
        _place_order(client, "gen-{}".format(i))
    code = client.post("/admin/coupons").json()["code"]

    cart_id = client.post("/carts").json()["id"]
    # Mug 1299 -> 10% off = 129 discount, total 1170
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": 1, "quantity": 1},
    )
    order = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={"coupon_code": code},
        headers={"Idempotency-Key": "with-coupon"},
    ).json()
    assert order["subtotal_paise"] == 1299
    assert order["discount_paise"] == 129
    assert order["total_paise"] == 1170
    assert order["coupon_code"] == code


def test_failed_checkout_does_not_consume_coupon(client):
    for i in range(5):
        _place_order(client, "fail-gen-{}".format(i), product_id=2)
    code = client.post("/admin/coupons").json()["code"]

    # Empty cart checkout should fail without redeeming the coupon.
    cart_id = client.post("/carts").json()["id"]
    resp = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={"coupon_code": code},
        headers={"Idempotency-Key": "empty-fail"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "empty_cart"

    # Coupon still usable.
    cart_id = client.post("/carts").json()["id"]
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": 1, "quantity": 1},
    )
    order = client.post(
        "/carts/{}/checkout".format(cart_id),
        json={"coupon_code": code},
        headers={"Idempotency-Key": "after-fail"},
    )
    assert order.status_code == 200
    assert order.json()["coupon_code"] == code


def test_coupon_cannot_be_redeemed_twice(client):
    for i in range(5):
        _place_order(client, "twice-{}".format(i))
    code = client.post("/admin/coupons").json()["code"]

    cart1 = client.post("/carts").json()["id"]
    client.post("/carts/{}/items".format(cart1), json={"product_id": 1, "quantity": 1})
    assert (
        client.post(
            "/carts/{}/checkout".format(cart1),
            json={"coupon_code": code},
            headers={"Idempotency-Key": "c1"},
        ).status_code
        == 200
    )

    cart2 = client.post("/carts").json()["id"]
    client.post("/carts/{}/items".format(cart2), json={"product_id": 1, "quantity": 1})
    resp = client.post(
        "/carts/{}/checkout".format(cart2),
        json={"coupon_code": code},
        headers={"Idempotency-Key": "c2"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "coupon_already_redeemed"
