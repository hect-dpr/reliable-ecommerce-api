from concurrent.futures import ThreadPoolExecutor, as_completed


def test_concurrent_checkout_does_not_oversell(client):
    """Two carts each ask for 2 posters (stock=2). One wins; stock ends at 0."""
    cart_ids = []
    for _ in range(2):
        cart_id = client.post("/carts").json()["id"]
        add = client.post(
            "/carts/{}/items".format(cart_id),
            json={"product_id": 5, "quantity": 2},
        )
        assert add.status_code == 200
        cart_ids.append(cart_id)

    def do_checkout(cart_id, key):
        return client.post(
            "/carts/{}/checkout".format(cart_id),
            json={},
            headers={"Idempotency-Key": key},
        )

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(do_checkout, cart_ids[0], "concurrent-a"),
            pool.submit(do_checkout, cart_ids[1], "concurrent-b"),
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]
    errors = {r.json().get("error") for r in results if r.status_code != 200}
    assert errors == {"insufficient_inventory"}

    poster = next(p for p in client.get("/products").json() if p["id"] == 5)
    assert poster["inventory"] == 0

    report = client.get("/admin/report").json()
    assert report["total_orders"] == 1
    sold = next(p for p in report["products"] if p["product_id"] == 5)
    assert sold["quantity_sold"] == 2


def test_concurrent_identical_idempotency_key(client):
    """Many parallel checkouts with the same key → one order."""
    cart_id = client.post("/carts").json()["id"]
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": 1, "quantity": 1},
    )

    def do_checkout():
        return client.post(
            "/carts/{}/checkout".format(cart_id),
            json={},
            headers={"Idempotency-Key": "same-key-race"},
        )

    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(do_checkout) for _ in range(8)]
        for fut in as_completed(futures):
            results.append(fut.result())

    assert all(r.status_code == 200 for r in results)
    order_ids = {r.json()["id"] for r in results}
    assert len(order_ids) == 1

    mug = next(p for p in client.get("/products").json() if p["id"] == 1)
    assert mug["inventory"] == 99

    report = client.get("/admin/report").json()
    assert report["total_orders"] == 1


def test_concurrent_coupon_redemption(client):
    """Two checkouts race on one coupon; only one gets it."""
    for i in range(5):
        cart_id = client.post("/carts").json()["id"]
        client.post(
            "/carts/{}/items".format(cart_id),
            json={"product_id": 2, "quantity": 1},
        )
        assert (
            client.post(
                "/carts/{}/checkout".format(cart_id),
                json={},
                headers={"Idempotency-Key": "setup-{}".format(i)},
            ).status_code
            == 200
        )

    code = client.post("/admin/coupons").json()["code"]

    cart_ids = []
    for _ in range(2):
        cart_id = client.post("/carts").json()["id"]
        client.post(
            "/carts/{}/items".format(cart_id),
            json={"product_id": 1, "quantity": 1},
        )
        cart_ids.append(cart_id)

    def do_checkout(cart_id, key):
        return client.post(
            "/carts/{}/checkout".format(cart_id),
            json={"coupon_code": code},
            headers={"Idempotency-Key": key},
        )

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(do_checkout, cart_ids[0], "coupon-race-a"),
            pool.submit(do_checkout, cart_ids[1], "coupon-race-b"),
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    successes = [r for r in results if r.status_code == 200]
    failures = [r for r in results if r.status_code != 200]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].json()["error"] == "coupon_already_redeemed"
    assert successes[0].json()["discount_paise"] == 129

    report = client.get("/admin/report").json()
    assert report["coupons_redeemed"] == 1
    assert report["coupons_available"] == 0
    assert report["total_discounts_paise"] == 129
