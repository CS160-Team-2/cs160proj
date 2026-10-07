"""Shared pytest fixtures for the spike.

`test_rules.py` needs nothing from here — it tests pure functions.
`test_integration.py` needs a live MySQL and a Flask test client, both
provided below.
"""

import pytest
from tests.fakes import (
    FakeMappingService,
    FakePaymentGateway,
    FakeVehicleInterface,
)

import db as database
from app import app as flask_app

SEEDED_CUSTOMER_ID = 1
LEMON_ID, APPLE_ID, WATER_ID = 1, 2, 3


def _mysql_available():
    try:
        database.db_version()
        return True
    except Exception:                                  # noqa: BLE001
        return False


# If MySQL is not running, the integration tests are skipped with a clear
# message instead of producing a wall of connection errors.
requires_mysql = pytest.mark.skipif(
    not _mysql_available(),
    reason="MySQL is not reachable — start the server and run schema.sql "
           "(see SETUP.md Part 2)",
)


@pytest.fixture
def app():
    """Provide the Flask application in testing mode."""
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def client(app):
    """Call Flask routes without starting a live server."""
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def runner(app):
    """Run Flask CLI commands during tests."""
    return app.test_cli_runner()


@pytest.fixture
def clean_cart():
    """Empty the seeded customer's cart before and after each test, so
    tests do not leak state into one another."""
    def _empty():
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE ci FROM cart_items ci "
                    "JOIN carts c ON c.cart_id = ci.cart_id "
                    "WHERE c.customer_id = %s",
                    (SEEDED_CUSTOMER_ID,),
                )
            conn.commit()

    _empty()
    yield SEEDED_CUSTOMER_ID
    _empty()


@pytest.fixture
def temp_product():
    """Create a product for a test and unlist it afterwards. Products are
    never hard-deleted — that is the point of USE CASE 2."""
    created = []

    def _make(name="Spike Test Product", price="1.00", weight="0.50"):
        pid = database.insert_product(name, price, weight)
        created.append(pid)
        return pid

    yield _make

    for pid in created:
        try:
            database.unlist_product(pid)
        except Exception:                              # noqa: BLE001
            pass

@pytest.fixture
def fake_payment_gateway():
    return FakePaymentGateway()


@pytest.fixture
def fake_mapping_service():
    return FakeMappingService()


@pytest.fixture
def fake_vehicle_interface():
    return FakeVehicleInterface()