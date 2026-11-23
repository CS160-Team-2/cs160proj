from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, request

import db
from manifest import normalize
from common import (STAFF, ApiError, body, current_user, ok, optional_text,
                    query_arg_int, require_decimal, require_int, require_role, require_text)

inventory_bp = Blueprint("inventory", __name__)

MAX_PRICE = Decimal("99999999.99")
MAX_WEIGHT = Decimal("2000.00")
MAX_INVENTORY_INT = 2147483647

AVAILABILITY_FILTERS = {
    "available": "p.is_listed = TRUE AND i.quantity_in_stock > 0",
    "out_of_stock": "p.is_listed = TRUE AND i.quantity_in_stock = 0",
    "low_stock": "p.is_listed = TRUE AND i.quantity_in_stock <= i.low_stock_threshold",
    "unlisted": "p.is_listed = FALSE",
}

INVENTORY_SELECT = (
    "SELECT p.product_id, p.name, p.description, p.category, p.price, p.unit_weight_lb, "
    "       p.image_key, p.is_listed, i.quantity_in_stock, i.low_stock_threshold, i.last_updated "
    "FROM products p JOIN inventory i ON i.product_id = p.product_id"
)


def inventory_json(row):
    stock = row["quantity_in_stock"]
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "price": row["price"],
        "unit_weight_lb": row["unit_weight_lb"],
        "image_key": row["image_key"],
        "is_listed": bool(row["is_listed"]),
        "stock": stock,
        "low_stock_threshold": row["low_stock_threshold"],
        "low_stock": stock <= row["low_stock_threshold"],
        "available": bool(row["is_listed"]) and stock > 0,
        "last_updated": row["last_updated"],
    }


def _load(product_id):
    row = db.query_one(f"{INVENTORY_SELECT} WHERE p.product_id = %s", (product_id,))
    if row is None:
        raise ApiError("No such product", 404, "NOT_FOUND")
    return row


def _price(data):
    price = require_decimal(data, "price")
    if price < 0:
        raise ApiError("Price cannot be negative", code="INVALID_PRICE")
    if price > MAX_PRICE:
        raise ApiError(f"Price cannot exceed {MAX_PRICE}", code="INVALID_PRICE")
    price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if price <= 0:
        raise ApiError("Price must be more than zero", code="INVALID_PRICE")
    return price


# Refuses a product name that another product already has, because manifests find products by name.
def _require_unused_name(name, own_product_id=None):
    wanted = normalize(name)
    for row in db.query_all("SELECT product_id, name, is_listed FROM products"):
        if row["product_id"] != own_product_id and normalize(row["name"]) == wanted:
            hint = "" if row["is_listed"] else " (it is unlisted: list it again instead)"
            raise ApiError(f"A product called \"{row['name']}\" already exists{hint}. Choose another name.",
                           409, "DUPLICATE_PRODUCT_NAME")


def _weight(data):
    weight = require_decimal(data, "unit_weight_lb")
    if weight <= 0:
        raise ApiError("Weight must be greater than zero", code="INVALID_WEIGHT")
    if weight > MAX_WEIGHT:
        raise ApiError(f"Weight cannot exceed {MAX_WEIGHT}", code="INVALID_WEIGHT")
    weight = weight.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if weight == 0:
        raise ApiError("Weight must round to at least 0.01 lb", code="INVALID_WEIGHT")
    return weight


def _inventory_int(data, field, minimum=None):
    try:
        number = require_int(data, field, minimum=minimum)
    except OverflowError:
        raise ApiError(f"{field} must be a whole number") from None
    if not -MAX_INVENTORY_INT - 1 <= number <= MAX_INVENTORY_INT:
        raise ApiError(f"{field} is outside the supported integer range")
    return number


# POST /api/admin/products: Adds a product with its price, weight and starting stock.
@inventory_bp.post("/api/admin/products")
@require_role(*STAFF)
def add_product():
    data = body()
    name = require_text(data, "name", 160)
    _require_unused_name(name)
    price = _price(data)
    weight = _weight(data)
    description = optional_text(data, "description", 2000)
    category = optional_text(data, "category", 60) or "Other"
    image_key = optional_text(data, "image_key", 100)
    stock = _inventory_int(data, "initial_stock", minimum=0) if "initial_stock" in data else 0
    threshold = (_inventory_int(data, "low_stock_threshold", minimum=0)
                 if "low_stock_threshold" in data else 5)

    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO products (name, description, category, price, unit_weight_lb, image_key) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (name, description, category, price, weight, image_key),
        )
        product_id = cur.lastrowid
        cur.execute(
            "INSERT INTO inventory (product_id, quantity_in_stock, low_stock_threshold) "
            "VALUES (%s, %s, %s)",
            (product_id, stock, threshold),
        )
        if stock:
            cur.execute(
                "INSERT INTO inventory_log (product_id, changed_by, change_qty, old_quantity, "
                "new_quantity, reason) VALUES (%s, %s, %s, 0, %s, 'Initial stock')",
                (product_id, current_user()["user_id"], stock, stock),
            )
    return ok(201, product=inventory_json(_load(product_id)))


# PATCH /api/admin/products/<int:product_id>: Any of name, description, category, price, unit_weight_lb, image_key, and is_listed.
@inventory_bp.patch("/api/admin/products/<int:product_id>")
@require_role(*STAFF)
def edit_product(product_id):
    _load(product_id)
    data = body()
    changes = {}

    if "name" in data:
        changes["name"] = require_text(data, "name", 160)
        _require_unused_name(changes["name"], product_id)
    if "description" in data:
        changes["description"] = optional_text(data, "description", 2000)
    if "category" in data:
        changes["category"] = require_text(data, "category", 60)
    if "price" in data:
        changes["price"] = _price(data)
    if "unit_weight_lb" in data:
        changes["unit_weight_lb"] = _weight(data)
    if "image_key" in data:
        changes["image_key"] = optional_text(data, "image_key", 100)
    if "is_listed" in data:
        if not isinstance(data["is_listed"], bool):
            raise ApiError("is_listed must be true or false")
        changes["is_listed"] = data["is_listed"]

    if not changes:
        raise ApiError("Nothing to update")

    assignments = ", ".join(f"{column} = %s" for column in changes)
    with db.transaction() as cur:
        cur.execute(f"UPDATE products SET {assignments} WHERE product_id = %s",
                    (*changes.values(), product_id))
    return ok(product=inventory_json(_load(product_id)))


# DELETE /api/admin/products/<int:product_id>: Not a row delete.
@inventory_bp.delete("/api/admin/products/<int:product_id>")
@require_role(*STAFF)
def unlist_product(product_id):
    _load(product_id)
    with db.transaction() as cur:
        cur.execute("UPDATE products SET is_listed = FALSE WHERE product_id = %s", (product_id,))
    return ok(product=inventory_json(_load(product_id)))


# GET /api/admin/inventory: Searches the inventory by name, category and availability.
@inventory_bp.get("/api/admin/inventory")
@require_role(*STAFF)
def list_inventory():
    where, params = [], []

    search = request.args.get("search", "").strip()
    if search:
        where.append("p.name LIKE %s")
        params.append(f"%{search}%")

    category = request.args.get("category", "").strip()
    if category:
        where.append("p.category = %s")
        params.append(category)

    availability = request.args.get("availability", "")
    if availability:
        if availability not in AVAILABILITY_FILTERS:
            raise ApiError(f"availability must be one of: {', '.join(AVAILABILITY_FILTERS)}")
        where.append(AVAILABILITY_FILTERS[availability])

    rows = db.query_all(
        f"{INVENTORY_SELECT} {'WHERE ' + ' AND '.join(where) if where else ''} "
        "ORDER BY p.name",
        tuple(params),
    )
    return ok(inventory=[inventory_json(r) for r in rows])


# GET /api/admin/inventory/low-stock: Lists products at or below their low-stock level.
@inventory_bp.get("/api/admin/inventory/low-stock")
@require_role(*STAFF)
def low_stock():
    rows = db.query_all(
        f"{INVENTORY_SELECT} WHERE {AVAILABILITY_FILTERS['low_stock']} "
        "ORDER BY i.quantity_in_stock, p.name"
    )
    return ok(inventory=[inventory_json(r) for r in rows])


# PATCH /api/admin/inventory/<int:product_id>
@inventory_bp.patch("/api/admin/inventory/<int:product_id>")
@require_role(*STAFF)
def adjust_stock(product_id):
    _load(product_id)
    data = body()
    if "delta" not in data and "low_stock_threshold" not in data:
        raise ApiError("Send a delta (with a reason), a low_stock_threshold, or both")

    with db.transaction() as cur:
        cur.execute(
            "SELECT quantity_in_stock FROM inventory WHERE product_id = %s FOR UPDATE",
            (product_id,),
        )
        old = cur.fetchone()["quantity_in_stock"]

        if "delta" in data:
            delta = _inventory_int(data, "delta")
            if delta == 0:
                raise ApiError("delta cannot be zero")
            reason = require_text(data, "reason", 255)
            if old + delta < 0:
                raise ApiError(f"Stock cannot go below zero: there are only {old} in stock",
                               409, "NEGATIVE_STOCK", stock=old)
            if old + delta > MAX_INVENTORY_INT:
                raise ApiError(f"Stock cannot exceed {MAX_INVENTORY_INT}",
                               409, "STOCK_LIMIT", stock=old)
            cur.execute(
                "UPDATE inventory SET quantity_in_stock = %s WHERE product_id = %s",
                (old + delta, product_id),
            )
            cur.execute(
                "INSERT INTO inventory_log (product_id, changed_by, change_qty, old_quantity, "
                "new_quantity, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                (product_id, current_user()["user_id"], delta, old, old + delta, reason),
            )

        if "low_stock_threshold" in data:
            threshold = _inventory_int(data, "low_stock_threshold", minimum=0)
            cur.execute(
                "UPDATE inventory SET low_stock_threshold = %s WHERE product_id = %s",
                (threshold, product_id),
            )

    return ok(product=inventory_json(_load(product_id)))


# GET /api/admin/inventory/<int:product_id>/changes: Newest first.
@inventory_bp.get("/api/admin/inventory/<int:product_id>/changes")
@require_role(*STAFF)
def stock_changes(product_id):
    _load(product_id)
    limit = min(max(query_arg_int("limit", 100), 1), 500)
    rows = db.query_all(
        "SELECT l.log_id, l.change_qty, l.old_quantity, l.new_quantity, l.reason, l.created_at, "
        "       u.full_name AS changed_by, o.order_number "
        "FROM inventory_log l LEFT JOIN users u ON u.user_id = l.changed_by "
        "LEFT JOIN orders o ON o.order_id = l.order_id "
        "WHERE l.product_id = %s ORDER BY l.log_id DESC LIMIT %s",
        (product_id, limit),
    )
    return ok(changes=rows)


# GET /api/admin/categories: Every category in use, including those only on unlisted products (the public list shows only listed ones).
@inventory_bp.get("/api/admin/categories")
@require_role(*STAFF)
def admin_categories():
    rows = db.query_all("SELECT DISTINCT category FROM products ORDER BY category")
    return ok(categories=[r["category"] for r in rows])
