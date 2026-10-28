def test_report_reconciles_and_is_readonly(client):
    cart_id = client.post("/carts").json()["id"]
    client.post(
        "/carts/{}/items".format(cart_id),
        json={"product_id": 1, "quantity": 2},
    )
    client.post(
        "/carts/{}/checkout".format(cart_id),
        json={},
        headers={"Idempotency-Key": "report-1"},
    )

    first = client.get("/admin/report").json()
    second = client.get("/admin/report").json()
    assert first == second
    assert first["total_orders"] == 1
    assert first["gross_revenue_paise"] == 2598
    assert first["total_discounts_paise"] == 0
    assert first["net_revenue_paise"] == 2598
    sold = next(p for p in first["products"] if p["product_id"] == 1)
    assert sold["quantity_sold"] == 2
