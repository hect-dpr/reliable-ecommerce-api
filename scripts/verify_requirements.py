#!/usr/bin/env python3
"""Hit the API with requests and check README behaviour.

Starts its own server + temp DB by default.
  python scripts/verify_requirements.py
  python scripts/verify_requirements.py --base-url http://127.0.0.1:8000
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import requests
except ImportError:
    print("Install requests first: pip install requests", file=sys.stderr)
    sys.exit(1)


class Result(object):
    def __init__(self, requirement, passed, detail, status=None, body=None):
        self.requirement = requirement
        self.passed = passed
        self.detail = detail
        self.status = status
        self.body = body


class Runner(object):
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.results = []

    def _record(self, requirement, passed, detail, status=None, body=None):
        r = Result(requirement, passed, detail, status, body)
        self.results.append(r)
        mark = "PASS" if passed else "FAIL"
        print("\n[{}] {}".format(mark, requirement))
        if status is not None:
            print("  status: {}".format(status))
        if body is not None:
            print("  response: {}".format(_fmt(body)))
        print("  detail: {}".format(detail))
        return passed

    def request(self, method, path, requirement, expect_status=None, expect_error=None,
                checks=None, **kwargs):
        url = self.base + path
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as exc:
            return self._record(requirement, False, "request failed: {}".format(exc))

        try:
            body = resp.json()
        except ValueError:
            body = resp.text

        ok = True
        notes = []
        if expect_status is not None and resp.status_code != expect_status:
            ok = False
            notes.append("expected status {}, got {}".format(expect_status, resp.status_code))
        if expect_error is not None:
            err = body.get("error") if isinstance(body, dict) else None
            if err != expect_error:
                ok = False
                notes.append("expected error '{}', got '{}'".format(expect_error, err))
        if checks:
            for check in checks:
                try:
                    check(resp.status_code, body)
                except AssertionError as exc:
                    ok = False
                    notes.append(str(exc))

        detail = "; ".join(notes) if notes else "ok"
        return self._record(requirement, ok, detail, resp.status_code, body)

    def raw(self, method, path, **kwargs):
        return self.session.request(method, self.base + path, timeout=30, **kwargs)


def _fmt(body):
    try:
        return json.dumps(body, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(body)


def _key(prefix):
    return "{}-{}".format(prefix, uuid.uuid4().hex[:10])


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def start_server(host, port):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///{}".format(db_path)
    env["COUPON_ORDER_INTERVAL"] = "5"
    env["COUPON_DISCOUNT_PERCENT"] = "10"
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = "http://{}:{}".format(host, port)
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
            raise RuntimeError("server exited early:\n{}".format(out))
        try:
            r = requests.get(base + "/health", timeout=1)
            if r.status_code == 200:
                return proc, base, db_path
        except requests.RequestException:
            time.sleep(0.15)
    proc.kill()
    raise RuntimeError("server did not become healthy in time")


def stop_server(proc, db_path):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    for path in (db_path, db_path + "-wal", db_path + "-shm"):
        try:
            os.unlink(path)
        except OSError:
            pass


def place_order(runner, product_id=1, quantity=1, coupon_code=None, key=None):
    cart = runner.raw("POST", "/carts").json()
    cart_id = cart["id"]
    runner.raw(
        "POST",
        "/carts/{}/items".format(cart_id),
        json={"product_id": product_id, "quantity": quantity},
    )
    headers = {"Idempotency-Key": key or _key("order")}
    body = {}
    if coupon_code:
        body["coupon_code"] = coupon_code
    resp = runner.raw(
        "POST",
        "/carts/{}/checkout".format(cart_id),
        json=body,
        headers=headers,
    )
    return resp, cart_id


def run_all(runner):
    runner.request(
        "GET",
        "/products",
        "Products: at least five seeded products with prices in paise",
        expect_status=200,
        checks=[
            lambda s, b: _assert(isinstance(b, list) and len(b) >= 5, "need >= 5 products"),
            lambda s, b: _assert(
                all("unit_price_paise" in p and "unit_price_display" in p for p in b),
                "products missing paise/display fields",
            ),
            lambda s, b: _assert(
                any(p["id"] == 5 and p["inventory"] == 2 for p in b),
                "product 5 should have limited inventory 2",
            ),
            lambda s, b: _assert(
                any(p["unit_price_display"].startswith("₹") for p in b),
                "display should use ₹",
            ),
        ],
    )

    runner.request(
        "POST",
        "/carts",
        "Carts: create cart",
        expect_status=201,
        checks=[
            lambda s, b: _assert(b.get("status") == "open" and b.get("items") == [], "empty open cart"),
            lambda s, b: _assert(b.get("subtotal_paise") == 0, "subtotal 0"),
        ],
    )
    cart_id = runner.results[-1].body["id"]

    runner.request(
        "POST",
        "/carts/{}/items".format(cart_id),
        "Carts: add item",
        expect_status=200,
        json={"product_id": 1, "quantity": 2},
        checks=[
            lambda s, b: _assert(len(b["items"]) == 1, "one line"),
            lambda s, b: _assert(b["subtotal_paise"] == 1299 * 2, "subtotal uses current price"),
            lambda s, b: _assert("line_total_paise" in b["items"][0], "line totals present"),
        ],
    )

    runner.request(
        "POST",
        "/carts/{}/items".format(cart_id),
        "Carts: add second product (multi-item cart)",
        expect_status=200,
        json={"product_id": 2, "quantity": 1},
        checks=[lambda s, b: _assert(len(b["items"]) == 2, "two lines")],
    )

    runner.request(
        "PUT",
        "/carts/{}/items/1".format(cart_id),
        "Carts: update quantity",
        expect_status=200,
        json={"quantity": 1},
        checks=[
            lambda s, b: _assert(
                next(i for i in b["items"] if i["product_id"] == 1)["quantity"] == 1,
                "qty updated to 1",
            ),
        ],
    )

    runner.request(
        "DELETE",
        "/carts/{}/items/2".format(cart_id),
        "Carts: remove item",
        expect_status=200,
        checks=[
            lambda s, b: _assert(len(b["items"]) == 1, "one line left"),
            lambda s, b: _assert(b["subtotal_paise"] == 1299, "subtotal after remove"),
        ],
    )

    runner.request(
        "GET",
        "/carts/{}".format(cart_id),
        "Carts: view cart with prices and totals",
        expect_status=200,
        checks=[
            lambda s, b: _assert("subtotal_paise" in b and "subtotal_display" in b, "totals present"),
        ],
    )

    # Bad cart input should fail clearly, not sneak in.
    runner.request(
        "POST",
        "/carts/{}/items".format(cart_id),
        "Inventory: reject invalid product",
        expect_status=400,
        expect_error="invalid_product",
        json={"product_id": 99999, "quantity": 1},
    )
    runner.request(
        "POST",
        "/carts/{}/items".format(cart_id),
        "Inventory: reject quantity above stock on add",
        expect_status=400,
        expect_error="insufficient_inventory",
        json={"product_id": 5, "quantity": 3},
    )
    runner.request(
        "GET",
        "/carts/999999",
        "Carts: 404 for missing cart",
        expect_status=404,
        expect_error="cart_not_found",
    )

    empty_id = runner.raw("POST", "/carts").json()["id"]
    runner.request(
        "POST",
        "/carts/{}/checkout".format(empty_id),
        "Checkout: reject empty cart",
        expect_status=400,
        expect_error="empty_cart",
        json={},
        headers={"Idempotency-Key": _key("empty")},
    )
    runner.request(
        "POST",
        "/carts/{}/checkout".format(cart_id),
        "Checkout: require Idempotency-Key",
        expect_status=400,
        expect_error="missing_idempotency_key",
        json={},
    )

    products_before = {p["id"]: p for p in runner.raw("GET", "/products").json()}
    mug_before = products_before[1]["inventory"]
    idem_key = _key("checkout")
    runner.request(
        "POST",
        "/carts/{}/checkout".format(cart_id),
        "Checkout: successful checkout creates order and decrements inventory",
        expect_status=200,
        json={},
        headers={"Idempotency-Key": idem_key},
        checks=[
            lambda s, b: _assert("id" in b and b["total_paise"] == 1299, "order total"),
            lambda s, b: _assert(b["items"][0]["unit_price_paise"] == 1299, "saved price"),
            lambda s, b: _assert(b["items"][0]["product_name"], "saved name"),
            lambda s, b: _assert(
                isinstance(b["subtotal_paise"], int)
                and isinstance(b["total_paise"], int)
                and isinstance(b["discount_paise"], int),
                "money fields must be ints",
            ),
        ],
    )
    order = runner.results[-1].body
    order_id = order["id"]

    products_after = {p["id"]: p for p in runner.raw("GET", "/products").json()}
    runner._record(
        "Checkout: inventory decremented exactly once after checkout",
        products_after[1]["inventory"] == mug_before - 1,
        "inventory {} -> {}".format(mug_before, products_after[1]["inventory"]),
        body={"product_id": 1, "inventory": products_after[1]["inventory"]},
    )

    runner.request(
        "POST",
        "/carts/{}/checkout".format(cart_id),
        "Checkout: retry with same Idempotency-Key returns same order (no double charge)",
        expect_status=200,
        json={},
        headers={"Idempotency-Key": idem_key},
        checks=[
            lambda s, b: _assert(b["id"] == order_id, "same order id"),
        ],
    )
    inv_after_retry = next(p for p in runner.raw("GET", "/products").json() if p["id"] == 1)[
        "inventory"
    ]
    runner._record(
        "Checkout: inventory unchanged after idempotent retry",
        inv_after_retry == products_after[1]["inventory"],
        "inventory stayed {}".format(inv_after_retry),
    )

    runner.request(
        "POST",
        "/carts/{}/checkout".format(cart_id),
        "Carts: cannot check out the same cart twice with a different key",
        expect_status=409,
        expect_error="cart_already_checked_out",
        json={},
        headers={"Idempotency-Key": _key("other")},
    )

    runner.request(
        "GET",
        "/orders/{}".format(order_id),
        "Orders: retrieve order with saved line prices",
        expect_status=200,
        checks=[
            lambda s, b: _assert(b["id"] == order_id, "order id"),
            lambda s, b: _assert(b["items"][0]["unit_price_paise"] == 1299, "saved price kept"),
        ],
    )
    runner.request(
        "GET",
        "/orders/999999",
        "Orders: 404 for missing order",
        expect_status=404,
        expect_error="order_not_found",
    )

    runner.request(
        "POST",
        "/admin/coupons",
        "Coupons: admin generate rejected before milestone (orders < n)",
        expect_status=409,
        expect_error="no_eligible_milestone",
    )

    # We already have 1 order; place 4 more to reach milestone 5.
    for i in range(4):
        resp, _ = place_order(runner, product_id=2, key=_key("mile"))
        _assert(resp.status_code == 200, "setup order failed: {}".format(resp.text))

    runner.request(
        "POST",
        "/admin/coupons",
        "Coupons: admin generates coupon at milestone n=5",
        expect_status=201,
        checks=[
            lambda s, b: _assert(b.get("milestone") == 5, "milestone 5"),
            lambda s, b: _assert(b.get("discount_percent") == 10, "x=10"),
            lambda s, b: _assert(b.get("status") == "available", "available"),
            lambda s, b: _assert(b.get("code"), "has code"),
        ],
    )
    coupon_code = runner.results[-1].body["code"]

    runner.request(
        "POST",
        "/admin/coupons",
        "Coupons: second generate for same milestone rejected",
        expect_status=409,
        expect_error="no_eligible_milestone",
    )

    # Empty cart + coupon should fail without using the coupon.
    fail_cart = runner.raw("POST", "/carts").json()["id"]
    runner.request(
        "POST",
        "/carts/{}/checkout".format(fail_cart),
        "Coupons: failed checkout does not consume coupon",
        expect_status=400,
        expect_error="empty_cart",
        json={"coupon_code": coupon_code},
        headers={"Idempotency-Key": _key("fail-coupon")},
    )

    runner.request(
        "POST",
        "/admin/coupons",  # still no new milestone; just proving coupon still exists via redeem
        "Coupons: still no new coupon after failed checkout",
        expect_status=409,
        expect_error="no_eligible_milestone",
    )

    # Mug ₹12.99, 10% off → 129 paise discount, total 1170.
    pay_cart = runner.raw("POST", "/carts").json()["id"]
    runner.raw(
        "POST",
        "/carts/{}/items".format(pay_cart),
        json={"product_id": 1, "quantity": 1},
    )
    runner.request(
        "POST",
        "/carts/{}/checkout".format(pay_cart),
        "Coupons: valid coupon applied; discount correct and not negative",
        expect_status=200,
        json={"coupon_code": coupon_code},
        headers={"Idempotency-Key": _key("with-coupon")},
        checks=[
            lambda s, b: _assert(b["subtotal_paise"] == 1299, "subtotal"),
            lambda s, b: _assert(b["discount_paise"] == 129, "10% of 1299 floored"),
            lambda s, b: _assert(b["total_paise"] == 1170, "total"),
            lambda s, b: _assert(b["total_paise"] >= 0, "total not negative"),
            lambda s, b: _assert(b["discount_paise"] <= b["subtotal_paise"], "discount <= subtotal"),
            lambda s, b: _assert(b["coupon_code"] == coupon_code, "coupon on order"),
        ],
    )

    reuse_cart = runner.raw("POST", "/carts").json()["id"]
    runner.raw(
        "POST",
        "/carts/{}/items".format(reuse_cart),
        json={"product_id": 1, "quantity": 1},
    )
    runner.request(
        "POST",
        "/carts/{}/checkout".format(reuse_cart),
        "Coupons: coupon cannot be redeemed twice",
        expect_status=409,
        expect_error="coupon_already_redeemed",
        json={"coupon_code": coupon_code},
        headers={"Idempotency-Key": _key("reuse-coupon")},
    )

    runner.request(
        "POST",
        "/carts/{}/checkout".format(reuse_cart),
        "Coupons: invalid coupon code rejected",
        expect_status=400,
        expect_error="invalid_coupon",
        json={"coupon_code": "NOT-A-REAL-CODE"},
        headers={"Idempotency-Key": _key("bad-coupon")},
    )

    r1 = runner.raw("GET", "/admin/report")
    r2 = runner.raw("GET", "/admin/report")
    report = r1.json()
    runner._record(
        "Admin report: returns required summary fields",
        r1.status_code == 200
        and all(
            k in report
            for k in (
                "products",
                "gross_revenue_paise",
                "total_discounts_paise",
                "net_revenue_paise",
                "coupons_generated",
                "coupons_available",
                "coupons_redeemed",
                "total_orders",
            )
        ),
        "status={} keys_ok".format(r1.status_code),
        r1.status_code,
        report,
    )
    runner._record(
        "Admin report: calling twice does not change data",
        r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json(),
        "same report both times",
        r2.status_code,
        r2.json(),
    )
    runner._record(
        "Admin report: numbers match orders and coupons",
        report["total_orders"] >= 6
        and report["coupons_generated"] == 1
        and report["coupons_redeemed"] == 1
        and report["coupons_available"] == 0
        and report["total_discounts_paise"] == 129
        and report["net_revenue_paise"]
        == report["gross_revenue_paise"] - report["total_discounts_paise"],
        "orders={} coupons_gen={} redeemed={} discount={}".format(
            report["total_orders"],
            report["coupons_generated"],
            report["coupons_redeemed"],
            report["total_discounts_paise"],
        ),
        body=report,
    )

    # Concurrent oversell: two carts each want qty=2 of the poster (stock=2).
    poster = next(p for p in runner.raw("GET", "/products").json() if p["id"] == 5)
    if poster["inventory"] < 2:
        runner._record(
            "Concurrency: oversell race (skipped — poster inventory already < 2)",
            False,
            "need inventory 2 on product 5; have {}".format(poster["inventory"]),
        )
    else:
        cart_ids = []
        for _ in range(2):
            cid = runner.raw("POST", "/carts").json()["id"]
            add = runner.raw(
                "POST",
                "/carts/{}/items".format(cid),
                json={"product_id": 5, "quantity": 2},
            )
            _assert(add.status_code == 200, "add poster failed: {}".format(add.text))
            cart_ids.append(cid)

        def checkout_poster(cid, key):
            return runner.raw(
                "POST",
                "/carts/{}/checkout".format(cid),
                json={},
                headers={"Idempotency-Key": key},
            )

        concurrent_results = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(checkout_poster, cart_ids[0], _key("oversell-a")),
                pool.submit(checkout_poster, cart_ids[1], _key("oversell-b")),
            ]
            for fut in as_completed(futs):
                concurrent_results.append(fut.result())

        statuses = sorted(r.status_code for r in concurrent_results)
        bodies = [_safe_json(r) for r in concurrent_results]
        poster_after = next(p for p in runner.raw("GET", "/products").json() if p["id"] == 5)
        ok = (
            statuses == [200, 409]
            and any(
                isinstance(b, dict) and b.get("error") == "insufficient_inventory"
                for b in bodies
            )
            and poster_after["inventory"] == 0
        )
        runner._record(
            "Concurrency: competing checkouts do not oversell limited inventory",
            ok,
            "statuses={}, inventory={}, bodies summarized".format(
                statuses, poster_after["inventory"]
            ),
            status=statuses,
            body=bodies,
        )

    # Same Idempotency-Key sent many times at once → one order.
    race_cart = runner.raw("POST", "/carts").json()["id"]
    runner.raw(
        "POST",
        "/carts/{}/items".format(race_cart),
        json={"product_id": 4, "quantity": 1},
    )
    shared_key = _key("same-key-race")
    cable_before = next(p for p in runner.raw("GET", "/products").json() if p["id"] == 4)[
        "inventory"
    ]

    def same_key_checkout():
        return runner.raw(
            "POST",
            "/carts/{}/checkout".format(race_cart),
            json={},
            headers={"Idempotency-Key": shared_key},
        )

    same_key_results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(same_key_checkout) for _ in range(8)]
        for fut in as_completed(futs):
            same_key_results.append(fut.result())

    order_ids = set()
    all_200 = True
    bodies = []
    for r in same_key_results:
        bodies.append(_safe_json(r))
        if r.status_code != 200:
            all_200 = False
        else:
            order_ids.add(r.json()["id"])
    cable_after = next(p for p in runner.raw("GET", "/products").json() if p["id"] == 4)[
        "inventory"
    ]
    runner._record(
        "Concurrency: identical Idempotency-Key races create exactly one order",
        all_200 and len(order_ids) == 1 and cable_after == cable_before - 1,
        "statuses all 200={}, unique_orders={}, inventory {} -> {}".format(
            all_200, order_ids, cable_before, cable_after
        ),
        body=bodies,
    )

    # Two checkouts racing on one coupon → only one succeeds.
    report_now = runner.raw("GET", "/admin/report").json()
    orders_now = report_now["total_orders"]
    while orders_now < 10:
        resp, _ = place_order(runner, product_id=3, key=_key("to10"))
        _assert(resp.status_code == 200, "order toward milestone failed")
        orders_now += 1

    gen = runner.raw("POST", "/admin/coupons")
    if gen.status_code != 201:
        runner._record(
            "Concurrency: coupon race setup failed generating coupon",
            False,
            "status={} body={}".format(gen.status_code, _safe_json(gen)),
            gen.status_code,
            _safe_json(gen),
        )
    else:
        race_code = gen.json()["code"]
        race_carts = []
        for _ in range(2):
            cid = runner.raw("POST", "/carts").json()["id"]
            runner.raw(
                "POST",
                "/carts/{}/items".format(cid),
                json={"product_id": 1, "quantity": 1},
            )
            race_carts.append(cid)

        def redeem(cid, key):
            return runner.raw(
                "POST",
                "/carts/{}/checkout".format(cid),
                json={"coupon_code": race_code},
                headers={"Idempotency-Key": key},
            )

        redeem_results = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(redeem, race_carts[0], _key("coupon-race-a")),
                pool.submit(redeem, race_carts[1], _key("coupon-race-b")),
            ]
            for fut in as_completed(futs):
                redeem_results.append(fut.result())

        successes = [r for r in redeem_results if r.status_code == 200]
        failures = [r for r in redeem_results if r.status_code != 200]
        fail_errors = [
            _safe_json(r).get("error") for r in failures if isinstance(_safe_json(r), dict)
        ]
        ok = (
            len(successes) == 1
            and len(failures) == 1
            and "coupon_already_redeemed" in fail_errors
            and successes[0].json()["discount_paise"] == 129
        )
        runner._record(
            "Concurrency: coupon not redeemed by two concurrent checkouts",
            ok,
            "successes={}, failures={}, errors={}".format(
                len(successes), len(failures), fail_errors
            ),
            body=[_safe_json(r) for r in redeem_results],
        )

    bad = runner.raw("GET", "/carts/0")
    body = _safe_json(bad)
    runner._record(
        "Errors: body has error code and detail",
        bad.status_code == 404
        and isinstance(body, dict)
        and "error" in body
        and "detail" in body,
        "status={} body={}".format(bad.status_code, body),
        bad.status_code,
        body,
    )


def _safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return resp.text


# requirement name → short label for the final checklist
README_EXPECTATIONS = [
    ("Products: at least five seeded products with prices in paise", "5+ products, paise prices, limited stock"),
    ("Carts: create cart", "Create cart"),
    ("Carts: add item", "Add item"),
    ("Carts: add second product (multi-item cart)", "Multi-product cart"),
    ("Carts: update quantity", "Update quantity"),
    ("Carts: remove item", "Remove item"),
    ("Carts: view cart with prices and totals", "View cart totals"),
    ("Inventory: reject invalid product", "Reject bad product"),
    ("Inventory: reject quantity above stock on add", "Reject overstock add"),
    ("Checkout: successful checkout creates order and decrements inventory", "Checkout creates order, cuts stock"),
    ("Checkout: retry with same Idempotency-Key returns same order (no double charge)", "Retry same key = same order"),
    ("Carts: cannot check out the same cart twice with a different key", "Cart checked out once"),
    ("Orders: retrieve order with saved line prices", "Order keeps saved prices"),
    ("Checkout: inventory decremented exactly once after checkout", "Stock cut once"),
    ("Checkout: inventory unchanged after idempotent retry", "Retry does not cut stock again"),
    ("Coupons: admin generate rejected before milestone (orders < n)", "No coupon before milestone"),
    ("Coupons: admin generates coupon at milestone n=5", "Admin can generate coupon"),
    ("Coupons: second generate for same milestone rejected", "One coupon per milestone"),
    ("Coupons: valid coupon applied; discount correct and not negative", "Coupon discount correct"),
    ("Coupons: failed checkout does not consume coupon", "Failed checkout keeps coupon"),
    ("Coupons: coupon cannot be redeemed twice", "Coupon used once"),
    ("Admin report: returns required summary fields", "Report has required fields"),
    ("Admin report: calling twice does not change data", "Report is read-only"),
    ("Admin report: numbers match orders and coupons", "Report matches orders/coupons"),
    ("Concurrency: competing checkouts do not oversell limited inventory", "No oversell under concurrency"),
    ("Concurrency: identical Idempotency-Key races create exactly one order", "Same key race = one order"),
    ("Concurrency: coupon not redeemed by two concurrent checkouts", "Coupon race = one redeem"),
    ("Errors: body has error code and detail", "Errors have code + detail"),
]


def print_summary(results):
    by_name = {r.requirement: r for r in results}
    print("\n" + "=" * 72)
    print("README CHECKLIST")
    print("=" * 72)
    satisfied = 0
    missing = 0
    for req_name, label in README_EXPECTATIONS:
        r = by_name.get(req_name)
        if r is None:
            missing += 1
            print("[ MISSING ] {}".format(label))
            continue
        if r.passed:
            satisfied += 1
            print("[   OK    ] {}".format(label))
        else:
            print("[  FAIL   ] {} — {}".format(label, r.detail))

    total = len(README_EXPECTATIONS)
    passed_checks = sum(1 for r in results if r.passed)
    failed_checks = sum(1 for r in results if not r.passed)
    print("-" * 72)
    print(
        "Checks: {}  passed: {}  failed: {}".format(
            len(results), passed_checks, failed_checks
        )
    )
    print(
        "README items: {}/{} ok ({} missing)".format(satisfied, total, missing)
    )
    all_ok = failed_checks == 0 and missing == 0 and satisfied == total
    print("\nALL README EXPECTATIONS MET: {}".format("YES" if all_ok else "NO"))
    print("=" * 72)
    return all_ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help="Use a server that is already running (needs fresh seed stock)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    proc = None
    db_path = None
    if args.base_url:
        base = args.base_url
        print("Using server at {}".format(base))
        print("Note: stock/coupon checks need a fresh DB.")
    else:
        print("Starting server on {}:{} with a temp DB...".format(args.host, args.port))
        proc, base, db_path = start_server(args.host, args.port)
        print("Ready at {}".format(base))

    print("Started: {}".format(datetime.utcnow().isoformat() + "Z"))
    runner = Runner(base)
    exit_code = 1
    try:
        run_all(runner)
        all_ok = print_summary(runner.results)
        exit_code = 0 if all_ok else 1
    finally:
        if proc is not None:
            stop_server(proc, db_path)
            print("\nStopped server.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
