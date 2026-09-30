"""OFS feasibility spike — Flask API.

Endpoints, grouped by what they prove:

  Connectivity
    GET    /api/health                       Flask is up and reachable
    GET    /api/products                     Flask -> MySQL, DECIMAL intact

  Rule arithmetic
    POST   /api/cart-check                   weight + delivery charge

  USE CASE 1 — customer chooses a product, stored in the database
    POST   /api/cart/items                   add a product to a cart
    GET    /api/cart/<customer_id>           read the cart back
    DELETE /api/cart/<customer_id>/items/<product_id>

  USE CASE 2 — store employee adds or removes a product
    POST   /api/admin/products               add a product
    DELETE /api/admin/products/<product_id>  remove it from sale

Run:  python app.py      (listens on http://localhost:5001)

Port 5001, not the Flask default of 5000, because macOS Monterey and
later run AirPlay Receiver on port 5000.
"""

import os
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from flask_cors import CORS

import db
import rules

app = Flask(__name__)

# In development React runs on a different port, so the browser treats it
# as a different origin. Behind Apache (see deploy/) both are served from
# the same origin and this is no longer needed — which is itself one of
# the things the Apache step proves.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
CORS(app, resources={r"/api/*": {"origins": [FRONTEND_ORIGIN]}})


def money(value):
    """Decimal is not JSON-serialisable. Send money and weight as strings
    so no precision is lost crossing the wire — the browser only displays
    them, it never does arithmetic on them."""
    return str(value)


def product_json(row):
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "price": money(row["price"]),
        "unit_weight_lb": money(row["unit_weight_lb"]),
    }


def fail(message, status=400, code="BAD_REQUEST"):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


# =====================================================================
# Connectivity
# =====================================================================

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "OFS spike API"})


@app.get("/api/products")
def products():
    try:
        rows = db.fetch_products()
    except Exception as exc:                      # noqa: BLE001
        return fail(str(exc), 500, "DB_ERROR")

    return jsonify({
        "ok": True,
        "mysql_version": db.db_version(),
        # Proof the driver returns Decimal, not float. If this says
        # "float", the 20 lb rule cannot be trusted.
        "weight_python_type": type(rows[0]["unit_weight_lb"]).__name__ if rows else None,
        "products": [product_json(r) for r in rows],
    })


# =====================================================================
# Rule arithmetic
# =====================================================================

@app.post("/api/cart-check")
def cart_check():
    """Body: {"lines": [{"product_id": 1, "quantity": 20}, ...]}"""
    body = request.get_json(silent=True) or {}
    quantities = {
        int(line["product_id"]): int(line["quantity"])
        for line in body.get("lines", [])
        if int(line.get("quantity", 0)) > 0
    }
    return jsonify(_price(quantities))


def _price(quantities):
    """Shared by /api/cart-check and /api/cart/<id>."""
    if not quantities:
        return {
            "ok": True, "total_weight_lb": "0.00", "delivery_fee": "0.00",
            "free_delivery": True, "subtotal": "0.00", "order_total": "0.00",
            "threshold_lb": money(rules.FREE_DELIVERY_LIMIT_LB), "lines": [],
        }

    rows = db.fetch_products_by_ids(list(quantities.keys()))
    lines = [
        {**r, "quantity": quantities[r["product_id"]]}
        for r in rows
    ]

    total_weight = rules.calculate_total_weight(lines)
    delivery_fee = rules.calculate_delivery_fee(total_weight)
    subtotal = rules.calculate_subtotal(lines)

    return {
        "ok": True,
        "total_weight_lb": money(total_weight),
        "delivery_fee": money(delivery_fee),
        "free_delivery": delivery_fee == Decimal("0.00"),
        "subtotal": money(subtotal),
        "order_total": money(subtotal + delivery_fee),
        "threshold_lb": money(rules.FREE_DELIVERY_LIMIT_LB),
        "lines": [
            {
                "product_id": ln["product_id"],
                "name": ln["name"],
                "quantity": ln["quantity"],
                "line_weight_lb": money(
                    Decimal(ln["unit_weight_lb"]) * ln["quantity"]
                ),
            }
            for ln in lines
        ],
    }


# =====================================================================
# USE CASE 1 — Customer chooses a product, stored in the database
# =====================================================================

@app.post("/api/cart/items")
def cart_add():
    """Body: {"customer_id": 1, "product_id": 2, "quantity": 6}

    Proves the write path: browser -> Flask -> MySQL, committed, and
    readable afterwards by a different connection.
    """
    body = request.get_json(silent=True) or {}
    try:
        customer_id = int(body["customer_id"])
        product_id = int(body["product_id"])
        quantity = int(body["quantity"])
    except (KeyError, TypeError, ValueError):
        return fail("customer_id, product_id and quantity are required integers")

    if quantity < 1:
        return fail("quantity must be at least 1")

    try:
        cart_id = db.add_to_cart(customer_id, product_id, quantity)
    except Exception as exc:                      # noqa: BLE001
        # A foreign-key violation lands here — proof the database is
        # rejecting a product or customer that does not exist, rather
        # than silently storing a dangling reference.
        return fail(str(exc), 409, "WRITE_REJECTED")

    stored = db.fetch_cart(customer_id)
    quantities = {r["product_id"]: r["quantity"] for r in stored}
    return jsonify({
        "ok": True,
        "cart_id": cart_id,
        "stored_in_database": True,
        "cart": _price(quantities),
    }), 201


@app.get("/api/cart/<int:customer_id>")
def cart_get(customer_id):
    try:
        stored = db.fetch_cart(customer_id)
    except Exception as exc:                      # noqa: BLE001
        return fail(str(exc), 500, "DB_ERROR")

    quantities = {r["product_id"]: r["quantity"] for r in stored}
    return jsonify({"ok": True, "customer_id": customer_id, "cart": _price(quantities)})


@app.delete("/api/cart/<int:customer_id>/items/<int:product_id>")
def cart_remove(customer_id, product_id):
    try:
        deleted = db.remove_from_cart(customer_id, product_id)
    except Exception as exc:                      # noqa: BLE001
        return fail(str(exc), 500, "DB_ERROR")

    if deleted == 0:
        return fail("That product is not in the cart", 404, "NOT_IN_CART")

    stored = db.fetch_cart(customer_id)
    quantities = {r["product_id"]: r["quantity"] for r in stored}
    return jsonify({"ok": True, "removed": product_id, "cart": _price(quantities)})


# =====================================================================
# USE CASE 2 — Store employee adds or removes a product
# =====================================================================

@app.post("/api/admin/products")
def admin_add_product():
    """Body: {"name": "...", "price": "4.99", "unit_weight_lb": "1.50"}

    Note there is no authentication here. That is deliberate for a spike
    — roles and permissions are feature 3.3, built in Part III. What this
    proves is only that the write reaches MySQL and that the database
    enforces the weight rule.
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()

    try:
        price = Decimal(str(body["price"]))
        weight = Decimal(str(body["unit_weight_lb"]))
    except (KeyError, TypeError, InvalidOperation):
        return fail("price and unit_weight_lb are required decimal values")

    if not name:
        return fail("name is required")

    try:
        product_id = db.insert_product(name, price, weight)
    except Exception as exc:                      # noqa: BLE001
        # A zero or negative weight lands here, rejected by the CHECK
        # constraint in schema.sql rather than by application code.
        return fail(str(exc), 409, "REJECTED_BY_DATABASE")

    return jsonify({
        "ok": True,
        "product_id": product_id,
        "appears_in_catalog": any(
            p["product_id"] == product_id for p in db.fetch_products()
        ),
    }), 201


@app.delete("/api/admin/products/<int:product_id>")
def admin_remove_product(product_id):
    """Remove a product from sale.

    Soft delete — sets is_listed = FALSE. A hard DELETE would fail on the
    foreign key from cart_items, and in the real system would orphan
    order history. Proving that here is the point.
    """
    try:
        changed = db.unlist_product(product_id)
    except Exception as exc:                      # noqa: BLE001
        return fail(str(exc), 500, "DB_ERROR")

    if changed == 0:
        return fail("No such product", 404, "NOT_FOUND")

    listed_ids = [p["product_id"] for p in db.fetch_products()]
    return jsonify({
        "ok": True,
        "product_id": product_id,
        "still_in_catalog": product_id in listed_ids,   # expect False
        "row_still_exists": any(
            p["product_id"] == product_id
            for p in db.fetch_products(include_unlisted=True)
        ),                                               # expect True
    })


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True)
