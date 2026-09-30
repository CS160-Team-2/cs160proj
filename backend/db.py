"""MySQL access for the OFS feasibility spike.

Proves three things the team cannot assume:
  1. Python can reach MySQL from both Windows and Apple Silicon.
  2. DECIMAL columns come back as Python Decimal, not float.
  3. Writes, transactions and foreign keys behave as expected — which is
     what the two main use cases depend on.
"""

import os

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# Reads backend/.env if present, so nobody has to export credentials by
# hand each session. Real environment variables still win over the file.
load_dotenv()

DB_CONFIG = {
    "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user":     os.environ.get("MYSQL_USER", "cs160team2"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "ofs"),
    "charset":  "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": False,          # explicit commits — see add_to_cart()
}


def get_connection():
    """Open a new connection. The spike opens one per request, which is
    fine at this scale; the real system will use a connection pool."""
    return pymysql.connect(**DB_CONFIG)


def db_version():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS version")
            return cur.fetchone()["version"]


# =====================================================================
# Catalog — read
# =====================================================================

def fetch_products(include_unlisted=False):
    sql = ("SELECT product_id, name, price, unit_weight_lb, is_listed "
           "FROM products")
    if not include_unlisted:
        sql += " WHERE is_listed = TRUE"
    sql += " ORDER BY product_id"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def fetch_products_by_ids(product_ids):
    if not product_ids:
        return []
    placeholders = ",".join(["%s"] * len(product_ids))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT product_id, name, price, unit_weight_lb "
                f"FROM products WHERE product_id IN ({placeholders})",
                tuple(product_ids),
            )
            return cur.fetchall()


# =====================================================================
# USE CASE 1 — A customer chooses a product, and it is stored
# =====================================================================

def add_to_cart(customer_id, product_id, quantity):
    """Put a product in a customer's cart, creating the cart if needed.

    Feasibility questions this answers:
      - can we write to MySQL from Flask at all?
      - does a multi-statement write commit as one unit?
      - does ON DUPLICATE KEY UPDATE work for the "already in cart" case?
      - do foreign keys reject a product that does not exist?
    """
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                # One open cart per customer.
                cur.execute(
                    "SELECT cart_id FROM carts WHERE customer_id = %s",
                    (customer_id,),
                )
                row = cur.fetchone()
                if row:
                    cart_id = row["cart_id"]
                else:
                    cur.execute(
                        "INSERT INTO carts (customer_id) VALUES (%s)",
                        (customer_id,),
                    )
                    cart_id = cur.lastrowid

                # Adding a product already in the cart increases the
                # quantity rather than failing on the primary key.
                cur.execute(
                    "INSERT INTO cart_items (cart_id, product_id, quantity) "
                    "VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
                    (cart_id, product_id, quantity),
                )
            conn.commit()
            return cart_id
        except Exception:
            conn.rollback()          # nothing half-written
            raise


def remove_from_cart(customer_id, product_id):
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE ci FROM cart_items ci "
                    "JOIN carts c ON c.cart_id = ci.cart_id "
                    "WHERE c.customer_id = %s AND ci.product_id = %s",
                    (customer_id, product_id),
                )
                deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise


def fetch_cart(customer_id):
    """Read the cart back. Proves the write actually persisted, rather
    than living in application memory."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ci.product_id, ci.quantity, "
                "       p.name, p.price, p.unit_weight_lb "
                "FROM carts c "
                "JOIN cart_items ci ON ci.cart_id = c.cart_id "
                "JOIN products   p  ON p.product_id = ci.product_id "
                "WHERE c.customer_id = %s "
                "ORDER BY ci.product_id",
                (customer_id,),
            )
            return cur.fetchall()


# =====================================================================
# USE CASE 2 — A store employee adds or removes a product
# =====================================================================

def insert_product(name, price, unit_weight_lb):
    """Add a new product to the catalog.

    Feasibility question: does the database itself enforce the rule that
    a product must have a positive weight? The CHECK constraint in
    schema.sql should reject a zero or negative weight even if the
    application forgets to validate.
    """
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO products (name, price, unit_weight_lb) "
                    "VALUES (%s, %s, %s)",
                    (name, price, unit_weight_lb),
                )
                product_id = cur.lastrowid
            conn.commit()
            return product_id
        except Exception:
            conn.rollback()
            raise


def unlist_product(product_id):
    """Remove a product from sale.

    Deliberately a soft delete: `is_listed = FALSE` rather than
    DELETE FROM products. A hard delete would either fail on the foreign
    key from cart_items, or — worse, in the real system — orphan the
    order history that references it. Proving this now is the point:
    "remove a product" cannot mean "delete the row".
    """
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE products SET is_listed = FALSE "
                    "WHERE product_id = %s",
                    (product_id,),
                )
                changed = cur.rowcount
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise


def relist_product(product_id):
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE products SET is_listed = TRUE WHERE product_id = %s",
                    (product_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
