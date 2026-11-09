"""M1 staff account management: privacy, roles, safe changes and races."""
import threading

from flask import request as flask_request
import pytest
from werkzeug.security import check_password_hash

import common
import db as database
from conftest import EMPLOYEE_ID, MANAGER_ID, error_code, requires_mysql, signed_in

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


def add_staff(manager, *, email="new-staff@ofs.test", role="employee"):
    response = manager.post("/api/admin/staff", json={
        "full_name": "New Staff", "email": email,
        "password": "initial-pass-1", "role": role,
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["staff"]


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_new_staff_credentials_work_but_are_never_returned(app, manager, role):
    staff = add_staff(manager, role=role)
    assert staff["role"] == role and staff["is_active"] is True
    assert set(staff) == {"user_id", "email", "full_name", "phone", "role", "is_guest",
                          "is_active", "created_at"}
    row = database.query_one("SELECT password_hash FROM users WHERE user_id = %s",
                             (staff["user_id"],))
    assert check_password_hash(row["password_hash"], "initial-pass-1")
    account = signed_in(app, staff["email"], "initial-pass-1")
    assert account.get("/api/auth/me").get_json()["user"]["role"] == role


def test_staff_list_includes_inactive_accounts_without_passwords(manager):
    staff = add_staff(manager)
    assert manager.delete(f"/api/admin/staff/{staff['user_id']}").status_code == 200
    response = manager.get("/api/admin/staff")
    listed = next(row for row in response.get_json()["staff"]
                  if row["user_id"] == staff["user_id"])
    assert listed["is_active"] is False
    assert "password" not in response.get_data(as_text=True)
    assert "customer@ofs.test" not in response.get_data(as_text=True)


def test_profile_edit_and_role_change_persist_as_one_update(manager):
    response = manager.patch(f"/api/admin/staff/{EMPLOYEE_ID}", json={
        "full_name": "  Updated Employee  ", "email": "UPDATED@OFS.TEST",
        "phone": "555-0100", "role": "manager",
    })
    assert response.status_code == 200
    staff = response.get_json()["staff"]
    assert staff["full_name"] == "Updated Employee"
    assert staff["email"] == "updated@ofs.test"
    assert staff["phone"] == "555-0100"
    assert staff["role"] == "manager"


def test_duplicate_email_does_not_partially_change_name_or_role(manager):
    response = manager.patch(f"/api/admin/staff/{EMPLOYEE_ID}", json={
        "full_name": "Must not be saved", "role": "manager", "email": "MANAGER@OFS.TEST",
    })
    assert response.status_code == 409
    assert error_code(response) == "EMAIL_TAKEN"
    row = database.query_one("SELECT full_name, role, email FROM users WHERE user_id = %s",
                             (EMPLOYEE_ID,))
    assert row == {"full_name": "Eli Park", "role": "employee", "email": "employee@ofs.test"}
    duplicate = manager.post("/api/admin/staff", json={
        "full_name": "Another Person", "email": "EMPLOYEE@OFS.TEST",
        "password": "initial-pass-1", "role": "employee",
    })
    assert error_code(duplicate) == "EMAIL_TAKEN"


def test_inactive_staff_can_be_reactivated_without_changing_their_id(app, manager):
    staff = add_staff(manager)
    path = f"/api/admin/staff/{staff['user_id']}"
    manager.delete(path)
    response = manager.patch(path, json={"is_active": True})
    assert response.status_code == 200
    assert response.get_json()["staff"]["user_id"] == staff["user_id"]
    account = signed_in(app, staff["email"], "initial-pass-1")
    assert account.get("/api/admin/inventory").status_code == 200


@pytest.mark.parametrize("changes", [
    {}, {"role": "customer"}, {"role": "admin"},
    {"is_active": False}, {"is_active": "true"},
    {"full_name": "  "}, {"email": "not-an-email"},
])
def test_invalid_staff_edits_are_rejected_without_mutation(manager, changes):
    response = manager.patch(f"/api/admin/staff/{EMPLOYEE_ID}", json=changes)
    assert response.status_code == 400
    row = database.query_one("SELECT role, is_active, full_name, email FROM users WHERE user_id = %s",
                             (EMPLOYEE_ID,))
    assert row["role"] == "employee" and row["is_active"]
    assert row["full_name"] == "Eli Park" and row["email"] == "employee@ofs.test"


def test_self_protection_still_applies_when_another_manager_exists(manager):
    add_staff(manager, role="manager")
    own_path = f"/api/admin/staff/{MANAGER_ID}"
    assert error_code(manager.delete(own_path)) == "SELF_DEACTIVATION"
    assert error_code(manager.patch(own_path, json={"role": "employee"})) == "SELF_DEMOTION"


def test_an_inactive_manager_does_not_allow_the_last_active_manager_to_be_removed(manager):
    inactive = add_staff(manager, role="manager")
    manager.delete(f"/api/admin/staff/{inactive['user_id']}")
    own_path = f"/api/admin/staff/{MANAGER_ID}"
    assert manager.delete(own_path).status_code == 409
    assert manager.patch(own_path, json={"role": "employee"}).status_code == 409
    active = database.query_one("SELECT COUNT(*) AS n FROM users WHERE role = 'manager' AND is_active = TRUE")
    assert active["n"] == 1


@pytest.mark.parametrize("fixture,expected", [("customer", 403), ("employee", 403), ("client", 401)])
@pytest.mark.parametrize("method,path,payload", [
    ("get", "/api/admin/staff", None),
    ("post", "/api/admin/staff", {"full_name": "Blocked", "email": "blocked@ofs.test", "password": "long-enough-1", "role": "manager"}),
    ("patch", f"/api/admin/staff/{EMPLOYEE_ID}", {"role": "manager"}),
    ("delete", f"/api/admin/staff/{MANAGER_ID}", None),
])
def test_non_managers_cannot_use_any_staff_management_action(request, fixture, expected, method, path, payload):
    actor = request.getfixturevalue(fixture)
    assert getattr(actor, method)(path, json=payload).status_code == expected


@pytest.mark.parametrize("method,changes", [("patch", {"role": "employee"}), ("delete", None)])
def test_two_managers_cannot_remove_each_other_concurrently(app, manager, monkeypatch, method, changes):
    rival = add_staff(manager, email="rival-manager@ofs.test", role="manager")
    second = signed_in(app, rival["email"], "initial-pass-1")
    barrier = threading.Barrier(2)
    original = common.current_user

    def synchronized_initial_role_check():
        user = original()
        if flask_request.method in ("PATCH", "DELETE") and not getattr(flask_request, "staff_role_checked", False):
            flask_request.staff_role_checked = True
            barrier.wait(timeout=10)
        return user

    # Both requests pass the initial role check before either gets the
    # mutation lock. The loser must re-read its newly changed role/status.
    monkeypatch.setattr(common, "current_user", synchronized_initial_role_check)
    results = []

    def remove_other(client, other_id):
        response = getattr(client, method)(f"/api/admin/staff/{other_id}", json=changes)
        results.append(response.status_code)

    threads = [threading.Thread(target=remove_other, args=(manager, rival["user_id"])),
               threading.Thread(target=remove_other, args=(second, MANAGER_ID))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not any(thread.is_alive() for thread in threads)
    expected = [200, 403] if method == "patch" else [200, 401]
    assert sorted(results) == expected
    active = database.query_one("SELECT COUNT(*) AS n FROM users WHERE role = 'manager' AND is_active = TRUE")
    assert active["n"] == 1
