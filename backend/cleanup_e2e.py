"""Removes the orders and guest accounts the browser tests created (customer backlog C5 tests).

The browser tests that place real orders (E2E_ALLOW_ORDERS=1 in frontend/e2e) use guest emails like
e2e-<number>@example.test. This script deletes those guests with their orders, payments and addresses,
and puts the stock back, so the shop's numbers return to what they were. Stripe test charges stay in the
Stripe dashboard; they are test mode and harmless.

    python cleanup_e2e.py
"""

import db

TABLES_BY_ORDER = ("inventory_log", "order_status_history", "payments", "order_items")


# Deletes one e2e guest's orders (restoring stock), payments, cart, address and account row.
def remove_guest(cur, user_id):
    cur.execute("SELECT order_id FROM orders WHERE user_id = %s", (user_id,))
    for order_id in [row["order_id"] for row in cur.fetchall()]:
        cur.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
        for item in cur.fetchall():
            cur.execute("UPDATE inventory SET quantity_in_stock = quantity_in_stock + %s WHERE product_id = %s",
                        (item["quantity"], item["product_id"]))
        for table in TABLES_BY_ORDER:
            cur.execute(f"DELETE FROM {table} WHERE order_id = %s", (order_id,))
        cur.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
    cur.execute("DELETE FROM payments WHERE user_id = %s", (user_id,))
    cur.execute("DELETE ci FROM cart_items ci JOIN carts c ON c.cart_id = ci.cart_id WHERE c.user_id = %s", (user_id,))
    cur.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM addresses WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))


# Finds the e2e guests and removes them all in one transaction.
def main():
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE is_guest = TRUE AND contact_email LIKE 'e2e-%%@example.test'")
        ids = [row["user_id"] for row in cur.fetchall()]
        for user_id in ids:
            remove_guest(cur, user_id)
        conn.commit()
    print(f"Removed {len(ids)} e2e guest account(s) with their orders.")


if __name__ == "__main__":
    main()
