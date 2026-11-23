import os

os.environ["MYSQL_DATABASE"] = os.environ.get("TEST_MYSQL_DATABASE", "ofs_test")
os.environ["VEHICLE_SIMULATION_SECONDS"] = "0"

import uuid                                            # noqa: E402

import pytest                                          # noqa: E402

import db as database                                  # noqa: E402
import ratelimit                                       # noqa: E402
import reset_db                                        # noqa: E402
from app import app as flask_app                       # noqa: E402
from services import mapping, payments, vehicle        # noqa: E402
from fakes import (                              # noqa: E402
    FakeMappingService,
    FakePaymentGateway,
    FakeVehicleInterface,
)

CUSTOMER = ("customer@ofs.test", "customer-pass-1")
EMPLOYEE = ("employee@ofs.test", "employee-pass-1")
MANAGER = ("manager@ofs.test", "manager-pass-1")
CUSTOMER_ID, EMPLOYEE_ID, MANAGER_ID = 1, 2, 3
CUSTOMER_ADDRESS_ID = 1
APPLES_ID = 1
VEHICLE_TOKEN = "dev-vehicle-token-1"
OTHER_VEHICLE_TOKEN = "dev-vehicle-token-2"


def _mysql_available():
    try:
        import pymysql
        pymysql.connect(**{**database.DB_CONFIG, "database": None}).close()
        return True
    except Exception:                                  # noqa: BLE001
        return False


requires_mysql = pytest.mark.skipif(
    not _mysql_available(),
    reason="MySQL test database is not reachable. Run schema.sql once as root "
           "(see SETUP.md Part 2) so the cs160team2 account can use ofs_test.",
)


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True)
    yield flask_app


# A clean, freshly seeded ofs_test and fresh fake services.
@pytest.fixture
def fresh_db():
    reset_db.load_tables(os.environ["MYSQL_DATABASE"])
    payments.use_gateway(payments.FakePaymentGateway())
    mapping.use_provider(mapping.FakeMapProvider())
    vehicle.use_link(vehicle.SimulatedVehicleLink(0))
    ratelimit.reset_all()


# A signed-out visitor.
@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


def signed_in(app, email, password):
    test_client = app.test_client()
    response = test_client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_json()
    return test_client


@pytest.fixture
def customer(app, fresh_db):
    return signed_in(app, *CUSTOMER)


@pytest.fixture
def employee(app, fresh_db):
    return signed_in(app, *EMPLOYEE)


@pytest.fixture
def manager(app, fresh_db):
    return signed_in(app, *MANAGER)


# Andy's standalone service fakes (backlog T-05), used by test_services_fake.py.
@pytest.fixture
def fake_payment_gateway():
    return FakePaymentGateway()


@pytest.fixture
def fake_mapping_service():
    return FakeMappingService()


@pytest.fixture
def fake_vehicle_interface():
    return FakeVehicleInterface()


# Insert a product with stock straight into the database.
def make_product(name="Test Product", price="1.00", weight="1.00", stock=100,
                 category="Test", threshold=5):
    with database.transaction() as cur:
        cur.execute(
            "INSERT INTO products (name, category, price, unit_weight_lb) VALUES (%s, %s, %s, %s)",
            (name, category, price, weight),
        )
        product_id = cur.lastrowid
        cur.execute(
            "INSERT INTO inventory (product_id, quantity_in_stock, low_stock_threshold) "
            "VALUES (%s, %s, %s)",
            (product_id, stock, threshold),
        )
    return product_id


def stock_of(product_id):
    return database.query_one(
        "SELECT quantity_in_stock FROM inventory WHERE product_id = %s", (product_id,)
    )["quantity_in_stock"]


def new_key():
    return uuid.uuid4().hex


# Put {product_id
def buy(test_client, items, address_id=CUSTOMER_ADDRESS_ID, token="tok_visa", key=None):
    test_client.delete("/api/cart")
    for product_id, quantity in items.items():
        added = test_client.post("/api/cart/items",
                                 json={"product_id": product_id, "quantity": quantity})
        assert added.status_code == 201, added.get_json()
    return test_client.post("/api/orders", json={
        "address_id": address_id, "payment_token": token, "idempotency_key": key or new_key(),
    })


# Place an order of the given weight and move it to awaiting_delivery.
def ready_order(customer_client, manager_client, weight="1.00"):
    product_id = make_product(weight=weight, stock=10)
    placed = buy(customer_client, {product_id: 1})
    assert placed.status_code == 201, placed.get_json()
    order_id = placed.get_json()["order"]["order_id"]
    moved = manager_client.patch(f"/api/admin/orders/{order_id}/status",
                                 json={"status": "awaiting_delivery"})
    assert moved.status_code == 200, moved.get_json()
    return order_id


def error_code(response):
    return response.get_json()["error"]["code"]
