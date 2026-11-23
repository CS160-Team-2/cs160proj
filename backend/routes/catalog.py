from flask import Blueprint, request

import db
from common import ApiError, ok, query_arg_decimal

catalog_bp = Blueprint("catalog", __name__)

PRODUCT_COLUMNS = (
    "p.product_id, p.name, p.description, p.category, p.price, p.unit_weight_lb, "
    "p.image_key, p.is_listed, COALESCE(i.quantity_in_stock, 0) AS stock"
)
PRODUCT_FROM = "FROM products p LEFT JOIN inventory i ON i.product_id = p.product_id"

SORTS = {
    "price_asc": "p.price ASC, p.product_id",
    "price_desc": "p.price DESC, p.product_id",
    "name": "p.name ASC, p.product_id",
}


# Reads "12" or "#12" as a product number; None when the search is not a plain number.
def _product_number(search):
    text = search[1:] if search.startswith("#") else search
    return int(text) if text.isascii() and text.isdigit() and len(text) <= 9 else None


def product_json(row):
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "price": row["price"],
        "unit_weight_lb": row["unit_weight_lb"],
        "image_key": row["image_key"],
        "stock": row["stock"],
        "available": bool(row["is_listed"]) and row["stock"] > 0,
    }


def fetch_product(product_id):
    return db.query_one(f"SELECT {PRODUCT_COLUMNS} {PRODUCT_FROM} WHERE p.product_id = %s",
                        (product_id,))


# GET /api/products: Lists listed products, with search, category, price and sort filters.
@catalog_bp.get("/api/products")
def list_products():
    where, params = ["p.is_listed = TRUE"], []

    search = request.args.get("search", "").strip()
    if search:
        number = _product_number(search)
        if number is None:
            where.append("p.name LIKE %s")
            params.append(f"%{search}%")
        else:
            where.append("(p.name LIKE %s OR p.product_id = %s)")
            params.extend([f"%{search}%", number])

    category = request.args.get("category", "").strip()
    if category:
        where.append("p.category = %s")
        params.append(category)

    min_price = query_arg_decimal("min_price")
    if min_price is not None:
        where.append("p.price >= %s")
        params.append(min_price)

    max_price = query_arg_decimal("max_price")
    if max_price is not None:
        where.append("p.price <= %s")
        params.append(max_price)

    sort = request.args.get("sort", "")
    if sort and sort not in SORTS:
        raise ApiError(f"sort must be one of: {', '.join(SORTS)}")
    order_by = SORTS.get(sort, "p.product_id")

    rows = db.query_all(
        f"SELECT {PRODUCT_COLUMNS} {PRODUCT_FROM} WHERE {' AND '.join(where)} ORDER BY {order_by}",
        tuple(params),
    )
    return ok(products=[product_json(r) for r in rows])


# GET /api/products/<int:product_id>
@catalog_bp.get("/api/products/<int:product_id>")
def get_product(product_id):
    row = fetch_product(product_id)
    if row is None:
        raise ApiError("No such product", 404, "NOT_FOUND")
    return ok(product=product_json(row))


# GET /api/categories: Lists the categories that have listed products.
@catalog_bp.get("/api/categories")
def list_categories():
    rows = db.query_all(
        "SELECT DISTINCT category FROM products WHERE is_listed = TRUE ORDER BY category"
    )
    return ok(categories=[r["category"] for r in rows])
