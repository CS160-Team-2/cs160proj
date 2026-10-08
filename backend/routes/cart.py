"""Shopping cart (API design table V).

    GET    /api/cart                          the cart, repriced every time
    POST   /api/cart/items                    {"product_id", "quantity"}; adds to any existing quantity
    PATCH  /api/cart/items/<product_id>       {"quantity"}; sets the quantity
    DELETE /api/cart/items/<product_id>       removes the line
    DELETE /api/cart                          empties the cart

Who owns the cart:
  - A signed-in customer's cart is saved in the database.
  - A visitor who has not signed in gets a cart kept in their session
    cookie, because the design lets people browse and fill a cart before
    making an account. When they sign in or register, it is merged into
    their saved cart.
  - Staff accounts do not have carts.

Every response returns the whole cart with weight and delivery fee
worked out here, using the same rules as checkout, so the cart and the
receipt can never disagree.
"""

from flask import Blueprint, session

import db
import rules
from common import ApiError, body, current_user, ok, require_int
from routes.catalog import fetch_product

cart_bp = Blueprint("cart", __name__)


# =====================================================================
# Reading and writing either kind of cart
# =====================================================================

def _owner():
    """The customer's user id, or None for a signed-out visitor."""
    user = current_user()
    if user is None:
        return None
    if user["role"] != "customer":
        raise ApiError("Staff accounts do not have a shopping cart", 403, "FORBIDDEN")
    return user["user_id"]


def quantities(user_id):
    """{product_id: quantity} for this cart."""
    if user_id is None:
        return {int(k): v for k, v in session.get("guest_cart", {}).items()}
    rows = db.query_all(
        "SELECT ci.product_id, ci.quantity FROM carts c "
        "JOIN cart_items ci ON ci.cart_id = c.cart_id WHERE c.user_id = %s",
        (user_id,),
    )
    return {r["product_id"]: r["quantity"] for r in rows}


def _set_quantity(user_id, product_id, quantity):
    if user_id is None:
        cart = dict(session.get("guest_cart", {}))
        cart[str(product_id)] = quantity
        session["guest_cart"] = cart
        return
    with db.transaction() as cur:
        cur.execute("INSERT IGNORE INTO carts (user_id) VALUES (%s)", (user_id,))
        cur.execute("SELECT cart_id FROM carts WHERE user_id = %s", (user_id,))
        cart_id = cur.fetchone()["cart_id"]
        cur.execute(
            "INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)",
            (cart_id, product_id, quantity),
        )


def _remove(user_id, product_id):
    if user_id is None:
        cart = dict(session.get("guest_cart", {}))
        cart.pop(str(product_id), None)
        session["guest_cart"] = cart
        return
    with db.transaction() as cur:
        cur.execute(
            "DELETE ci FROM cart_items ci JOIN carts c ON c.cart_id = ci.cart_id "
            "WHERE c.user_id = %s AND ci.product_id = %s",
            (user_id, product_id),
        )


def clear(cur, user_id):
    """Empty a saved cart inside an existing transaction (used by checkout)."""
    cur.execute(
        "DELETE ci FROM cart_items ci JOIN carts c ON c.cart_id = ci.cart_id "
        "WHERE c.user_id = %s",
        (user_id,),
    )


def merge_guest_cart(user_id, guest_cart):
    """Fold a visitor's session cart into their saved cart at sign-in.
    Quantities add together, capped at what is in stock; products that
    can no longer be bought are dropped."""
    saved = quantities(user_id)
    for key, quantity in guest_cart.items():
        product = fetch_product(int(key))
        if product is None or not product["is_listed"] or product["stock"] <= 0:
            continue
        total = min(saved.get(product["product_id"], 0) + int(quantity), product["stock"])
        _set_quantity(user_id, product["product_id"], total)


# =====================================================================
# Pricing
# =====================================================================

def cart_lines(product_quantities):
    """Current product rows joined with quantities, for pricing."""
    if not product_quantities:
        return []
    ids = list(product_quantities)
    rows = db.query_all(
        "SELECT p.product_id, p.name, p.price, p.unit_weight_lb, p.image_key, p.is_listed, "
        "       COALESCE(i.quantity_in_stock, 0) AS stock "
        "FROM products p LEFT JOIN inventory i ON i.product_id = p.product_id "
        f"WHERE p.product_id IN ({db.placeholders(ids)}) ORDER BY p.product_id",
        tuple(ids),
    )
    return [{**r, "quantity": product_quantities[r["product_id"]]} for r in rows]


def line_problem(line):
    """Why this line cannot be bought as it stands, or None."""
    if not line["is_listed"]:
        return "This product is no longer sold"
    if line["stock"] <= 0:
        return "Out of stock"
    if line["quantity"] > line["stock"]:
        return f"Only {line['stock']} left in stock"
    return None


def summary(product_quantities):
    lines = cart_lines(product_quantities)
    totals = rules.price_lines(lines)
    return {
        "items": [
            {
                "product_id": ln["product_id"],
                "name": ln["name"],
                "image_key": ln["image_key"],
                "price": ln["price"],
                "unit_weight_lb": ln["unit_weight_lb"],
                "quantity": ln["quantity"],
                "line_total": (ln["price"] * ln["quantity"]).quantize(rules.CENTS),
                "line_weight_lb": (ln["unit_weight_lb"] * ln["quantity"]).quantize(rules.CENTS),
                "stock": ln["stock"],
                "problem": line_problem(ln),
            }
            for ln in lines
        ],
        "item_count": sum(ln["quantity"] for ln in lines),
        "subtotal": totals["subtotal"],
        "total_weight_lb": totals["total_weight_lb"],
        "delivery_fee": totals["delivery_fee"],
        "free_delivery_below_lb": rules.FREE_DELIVERY_LIMIT_LB,
        "estimated_total": totals["subtotal"] + totals["delivery_fee"],
        "can_check_out": bool(lines) and all(line_problem(ln) is None for ln in lines),
    }


def _respond(user_id, status=200):
    return ok(status, cart=summary(quantities(user_id)))


def _buyable_product(product_id):
    product = fetch_product(product_id)
    if product is None:
        raise ApiError("Product not found", 404, "NOT_FOUND")
    if not product["is_listed"] or product["stock"] <= 0:
        raise ApiError("This product is unavailable", 409, "PRODUCT_UNAVAILABLE")
    return product


def _check_stock(product, quantity):
    if quantity > product["stock"]:
        raise ApiError(f"Only {product['stock']} of {product['name']} in stock",
                       409, "NOT_ENOUGH_STOCK", available=product["stock"])


# =====================================================================
# Routes
# =====================================================================

@cart_bp.get("/api/cart")
def get_cart():
    return _respond(_owner())


@cart_bp.post("/api/cart/items")
def add_item():
    user_id = _owner()
    data = body()
    product_id = require_int(data, "product_id")
    quantity = require_int(data, "quantity", minimum=1)

    product = _buyable_product(product_id)
    total = quantities(user_id).get(product_id, 0) + quantity
    _check_stock(product, total)
    _set_quantity(user_id, product_id, total)
    return _respond(user_id, 201)


@cart_bp.patch("/api/cart/items/<int:product_id>")
def set_item_quantity(product_id):
    user_id = _owner()
    quantity = require_int(body(), "quantity", minimum=1)
    if product_id not in quantities(user_id):
        raise ApiError("That product is not in the cart", 404, "NOT_IN_CART")

    product = _buyable_product(product_id)
    _check_stock(product, quantity)
    _set_quantity(user_id, product_id, quantity)
    return _respond(user_id)


@cart_bp.delete("/api/cart/items/<int:product_id>")
def remove_item(product_id):
    user_id = _owner()
    if product_id not in quantities(user_id):
        raise ApiError("That product is not in the cart", 404, "NOT_IN_CART")
    _remove(user_id, product_id)
    return _respond(user_id)


@cart_bp.delete("/api/cart")
def empty_cart():
    user_id = _owner()
    if user_id is None:
        session.pop("guest_cart", None)
    else:
        with db.transaction() as cur:
            clear(cur, user_id)
    return _respond(user_id)
