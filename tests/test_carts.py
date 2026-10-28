def test_cart_rejects_invalid_product(client):
    cart = client.post("/carts").json()
    resp = client.post(
        "/carts/{}/items".format(cart["id"]),
        json={"product_id": 999, "quantity": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_product"


def test_cart_rejects_over_inventory_add(client):
    cart = client.post("/carts").json()
    # Product 5 (poster) has inventory 2.
    resp = client.post(
        "/carts/{}/items".format(cart["id"]),
        json={"product_id": 5, "quantity": 3},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "insufficient_inventory"


def test_cart_add_update_remove_and_totals(client):
    cart_id = client.post("/carts").json()["id"]
    added = client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": 1, "quantity": 2},
    ).json()
    assert added["subtotal_paise"] == 1299 * 2

    updated = client.put(
        "/carts/{}/items/1".format(cart_id),
        json={"quantity": 1},
    ).json()
    assert updated["subtotal_paise"] == 1299

    emptied = client.delete("/carts/{}/items/1".format(cart_id)).json()
    assert emptied["items"] == []
    assert emptied["subtotal_paise"] == 0
