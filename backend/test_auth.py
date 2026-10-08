"""Accounts, sign-in and role checks (API tables I and II; backlog B-03,
B-04; test plan T-17 and T-20)."""

import pytest

import db as database
from conftest import (CUSTOMER, EMPLOYEE_ID, MANAGER_ID, error_code, requires_mysql,
                      signed_in)

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def register(client, email="new@example.com", password="long-enough-1", name="New Person"):
    return client.post("/api/auth/register",
                       json={"email": email, "password": password, "full_name": name})


# --- Register, sign in, sign out --------------------------------------

def test_register_creates_a_signed_in_customer(client):
    response = register(client)

    assert response.status_code == 201
    assert response.get_json()["user"]["role"] == "customer"
    assert client.get("/api/auth/me").get_json()["user"]["email"] == "new@example.com"


def test_passwords_are_stored_hashed(client):
    register(client, password="long-enough-1")
    stored = database.query_one("SELECT password_hash FROM users WHERE email = 'new@example.com'")

    assert "long-enough-1" not in stored["password_hash"]
    assert stored["password_hash"].startswith("pbkdf2:sha256")


@pytest.mark.parametrize("payload,code", [
    ({"email": "not-an-email", "password": "long-enough-1", "full_name": "A"}, "INVALID_EMAIL"),
    ({"email": "a@b.co", "password": "short", "full_name": "A"}, "WEAK_PASSWORD"),
    ({"email": "a@b.co", "password": "long-enough-1"}, "BAD_REQUEST"),
])
def test_register_validates_input(client, payload, code):
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert error_code(response) == code


def test_email_can_only_be_used_once(client):
    register(client, email="dup@example.com")
    again = register(client, email="DUP@example.com")

    assert again.status_code == 409
    assert error_code(again) == "EMAIL_TAKEN"


def test_login_returns_the_role(client):
    response = client.post("/api/auth/login",
                           json={"email": "manager@ofs.test", "password": "manager-pass-1"})
    assert response.get_json()["user"]["role"] == "manager"


def test_wrong_password_and_unknown_email_look_the_same(client):
    wrong_password = client.post("/api/auth/login",
                                 json={"email": CUSTOMER[0], "password": "nope-nope-nope"})
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@example.com", "password": "nope-nope-nope"})

    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.get_json() == unknown.get_json()


def test_logout_ends_the_session(customer):
    customer.post("/api/auth/logout")
    assert customer.get("/api/auth/me").status_code == 401


# --- Own account ------------------------------------------------------

def test_update_own_name(customer):
    response = customer.patch("/api/users/me", json={"full_name": "Anna R."})
    assert response.get_json()["user"]["full_name"] == "Anna R."


def test_password_change_needs_the_current_password(app, customer):
    refused = customer.patch("/api/users/me",
                             json={"new_password": "brand-new-pass", "current_password": "wrong"})
    assert refused.status_code == 403

    changed = customer.patch("/api/users/me", json={
        "new_password": "brand-new-pass", "current_password": CUSTOMER[1]})
    assert changed.status_code == 200
    signed_in(app, CUSTOMER[0], "brand-new-pass")


def test_role_cannot_be_changed_through_own_account(customer):
    customer.patch("/api/users/me", json={"full_name": "Anna", "role": "manager"})
    assert customer.get("/api/auth/me").get_json()["user"]["role"] == "customer"


# --- Role boundaries (T-17) -------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/inventory"),
    ("post", "/api/admin/products"),
    ("get", "/api/admin/orders"),
    ("get", "/api/admin/staff"),
    ("get", "/api/admin/delivery/queue"),
])
def test_customers_cannot_reach_staff_endpoints(customer, method, path):
    assert getattr(customer, method)(path, json={}).status_code == 403


@pytest.mark.parametrize("path", ["/api/admin/orders", "/api/admin/staff",
                                  "/api/admin/delivery/trips"])
def test_employees_cannot_reach_manager_endpoints(employee, path):
    assert employee.get(path).status_code == 403


def test_employees_can_reach_inventory(employee):
    assert employee.get("/api/admin/inventory").status_code == 200


def test_signed_out_visitors_must_sign_in(client):
    response = client.get("/api/admin/inventory")
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


# --- Staff accounts ---------------------------------------------------

def test_manager_creates_and_lists_staff(manager):
    created = manager.post("/api/admin/staff", json={
        "email": "clerk@ofs.test", "password": "clerk-pass-1", "full_name": "Clerk",
        "role": "employee"})
    assert created.status_code == 201

    emails = [s["email"] for s in manager.get("/api/admin/staff").get_json()["staff"]]
    assert "clerk@ofs.test" in emails
    assert "customer@ofs.test" not in emails


def test_staff_cannot_be_created_as_customers(manager):
    response = manager.post("/api/admin/staff", json={
        "email": "x@ofs.test", "password": "long-enough-1", "full_name": "X", "role": "customer"})
    assert error_code(response) == "INVALID_ROLE"


def test_deactivated_staff_lose_access_immediately(app, manager):
    employee = signed_in(app, "employee@ofs.test", "employee-pass-1")
    assert manager.delete(f"/api/admin/staff/{EMPLOYEE_ID}").status_code == 200

    assert employee.get("/api/admin/inventory").status_code == 401
    login = employee.post("/api/auth/login",
                          json={"email": "employee@ofs.test", "password": "employee-pass-1"})
    assert error_code(login) == "ACCOUNT_INACTIVE"

    row = database.query_one("SELECT user_id FROM users WHERE user_id = %s", (EMPLOYEE_ID,))
    assert row is not None                      # deactivated, not deleted


def test_manager_can_promote_and_reactivate(manager):
    manager.delete(f"/api/admin/staff/{EMPLOYEE_ID}")
    response = manager.patch(f"/api/admin/staff/{EMPLOYEE_ID}",
                             json={"is_active": True, "role": "manager"})

    staff = response.get_json()["staff"]
    assert staff["is_active"] is True and staff["role"] == "manager"


def test_manager_cannot_lock_themselves_out(manager):
    assert error_code(manager.delete(f"/api/admin/staff/{MANAGER_ID}")) == "SELF_DEACTIVATION"
    demote = manager.patch(f"/api/admin/staff/{MANAGER_ID}", json={"role": "employee"})
    assert error_code(demote) == "SELF_DEMOTION"


def test_staff_endpoints_do_not_touch_customers(manager):
    assert manager.delete("/api/admin/staff/1").status_code == 404
