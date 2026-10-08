"""Database guarantees the rest of the system relies on. These came from
the feasibility spike and still matter: if any of them fails, the money
and weight rules cannot be trusted no matter how the code is written."""

from decimal import Decimal

import pymysql
import pytest

import db as database
from conftest import APPLES_ID, make_product, requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def test_decimal_survives_the_round_trip():
    row = database.query_one("SELECT unit_weight_lb FROM products WHERE product_id = %s",
                             (APPLES_ID,))
    assert isinstance(row["unit_weight_lb"], Decimal)
    assert row["unit_weight_lb"] == Decimal("3.00")


def test_decimal_arithmetic_is_exact_after_reading_from_mysql():
    lemon = make_product(weight="0.10")
    weight = database.query_one("SELECT unit_weight_lb FROM products WHERE product_id = %s",
                                (lemon,))["unit_weight_lb"]
    assert weight * 10 == Decimal("1.00")


@pytest.mark.parametrize("weight", ["0.00", "-1.00"])
def test_database_refuses_a_product_without_a_positive_weight(weight):
    with pytest.raises(pymysql.err.OperationalError):
        make_product(weight=weight)


def test_database_refuses_negative_stock():
    with pytest.raises(pymysql.err.OperationalError):
        with database.transaction() as cur:
            cur.execute("UPDATE inventory SET quantity_in_stock = -1 WHERE product_id = %s",
                        (APPLES_ID,))


def test_hard_deleting_a_product_in_a_cart_is_blocked(customer):
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    with pytest.raises(pymysql.err.IntegrityError):
        with database.transaction() as cur:
            cur.execute("DELETE FROM inventory WHERE product_id = %s", (APPLES_ID,))
            cur.execute("DELETE FROM products WHERE product_id = %s", (APPLES_ID,))
