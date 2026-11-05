"""Uploading a delivery manifest to restock the inventory. Managers only.

    POST /api/admin/inventory/manifest/preview   multipart, field "file": what would change
    POST /api/admin/inventory/manifest           multipart, field "file": apply it

Preview never changes anything. Apply re-reads the file itself (it does
not trust an earlier preview) and saves every line in one transaction,
or nothing at all. A file whose contents were already applied is refused,
so the same delivery cannot be counted twice.

The file rules themselves are tested without a database in test_manifest.py.
"""

import io

import pytest

import db as database
from conftest import APPLES_ID, MANAGER_ID, error_code, requires_mysql, stock_of

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

PREVIEW = "/api/admin/inventory/manifest/preview"
APPLY = "/api/admin/inventory/manifest"

BROCCOLI_ID = 3        # 'Organic Broccoli Crown', 35 in stock
# Apples start at 40 in stock.

DELIVERY = (
    "product_name,quantity\n"
    '"Organic Apples, 3 lb bag",24\n'
    "Organic Broccoli Crown,30\n"
).encode("utf-8")

BAD_DELIVERY = (
    "product_name,quantity\n"
    '"Organic Apples, 3 lb bag",24\n'
    "Organic Brocoli Crown,30\n"
).encode("utf-8")


def upload(user, path, raw=DELIVERY, filename="delivery.csv"):
    return user.post(path, data={"file": (io.BytesIO(raw), filename)},
                     content_type="multipart/form-data")


def manifest_log_rows():
    return list(database.query_all(
        "SELECT product_id, changed_by, change_qty, old_quantity, new_quantity, reason "
        "FROM inventory_log WHERE reason LIKE 'Delivery manifest%%' ORDER BY log_id"))


# =====================================================================
# Preview
# =====================================================================

def test_preview_shows_stock_now_and_after_without_changing_anything(manager):
    response = upload(manager, PREVIEW)

    assert response.status_code == 200
    body = response.get_json()
    assert body["can_apply"] is True and body["problems"] == []
    assert body["already_applied"] is None
    assert body["filename"] == "delivery.csv"
    assert [(line["product_id"], line["quantity"], line["stock_now"], line["stock_after"])
            for line in body["lines"]] == [(APPLES_ID, 24, 40, 64), (BROCCOLI_ID, 30, 35, 65)]

    assert stock_of(APPLES_ID) == 40 and stock_of(BROCCOLI_ID) == 35
    assert manifest_log_rows() == []


def test_preview_lists_problems_and_cannot_be_applied(manager):
    body = upload(manager, PREVIEW, BAD_DELIVERY).get_json()

    assert body["can_apply"] is False
    assert [problem["line"] for problem in body["problems"]] == [3]
    assert "Organic Brocoli Crown" in body["problems"][0]["message"]
    assert stock_of(APPLES_ID) == 40


# =====================================================================
# Apply
# =====================================================================

def test_applying_adds_the_stock_and_logs_who_and_why(manager):
    response = upload(manager, APPLY)

    assert response.status_code == 201
    saved = response.get_json()["manifest"]
    assert saved["filename"] == "delivery.csv"
    assert saved["line_count"] == 2 and saved["total_units"] == 54
    assert stock_of(APPLES_ID) == 64 and stock_of(BROCCOLI_ID) == 65

    reason = f"Delivery manifest #{saved['manifest_id']} (delivery.csv)"
    assert manifest_log_rows() == [
        {"product_id": APPLES_ID, "changed_by": MANAGER_ID, "change_qty": 24,
         "old_quantity": 40, "new_quantity": 64, "reason": reason},
        {"product_id": BROCCOLI_ID, "changed_by": MANAGER_ID, "change_qty": 30,
         "old_quantity": 35, "new_quantity": 65, "reason": reason},
    ]


def test_the_change_shows_in_the_existing_stock_history(manager):
    saved = upload(manager, APPLY).get_json()["manifest"]

    latest = manager.get(f"/api/admin/inventory/{APPLES_ID}/changes").get_json()["changes"][0]

    assert latest["reason"] == f"Delivery manifest #{saved['manifest_id']} (delivery.csv)"
    assert latest["change_qty"] == 24


def test_one_bad_line_means_nothing_is_applied(manager):
    response = upload(manager, APPLY, BAD_DELIVERY)

    assert response.status_code == 422
    assert error_code(response) == "MANIFEST_INVALID"
    assert [problem["line"] for problem in response.get_json()["error"]["problems"]] == [3]
    assert stock_of(APPLES_ID) == 40                       # the good line was not saved either
    assert manifest_log_rows() == []
    assert not database.query_all("SELECT * FROM delivery_manifests")


def test_the_same_file_cannot_be_applied_twice(manager):
    assert upload(manager, APPLY).status_code == 201

    again = upload(manager, APPLY, filename="delivery-copy.csv")   # renamed, same contents

    assert again.status_code == 409
    assert error_code(again) == "MANIFEST_ALREADY_APPLIED"
    assert stock_of(APPLES_ID) == 64                       # added once, not twice


def test_preview_warns_when_a_file_was_already_applied(manager):
    first = upload(manager, APPLY).get_json()["manifest"]

    body = upload(manager, PREVIEW).get_json()

    assert body["can_apply"] is False
    assert body["already_applied"]["manifest_id"] == first["manifest_id"]
    assert body["already_applied"]["applied_by"] == "Maya Chen"


def test_a_different_delivery_of_the_same_products_is_allowed(manager):
    upload(manager, APPLY)
    tomorrow = DELIVERY.replace(b",24\n", b",10\n")

    assert upload(manager, APPLY, tomorrow).status_code == 201
    assert stock_of(APPLES_ID) == 74


def test_applying_records_the_manifest(manager):
    saved = upload(manager, APPLY).get_json()["manifest"]

    row = database.query_one("SELECT * FROM delivery_manifests WHERE manifest_id = %s",
                             (saved["manifest_id"],))
    assert row["filename"] == "delivery.csv"
    assert row["applied_by"] == MANAGER_ID
    assert row["line_count"] == 2 and row["total_units"] == 54
    assert len(row["fingerprint"]) == 64


def test_restocking_an_unlisted_product_keeps_it_unlisted(manager):
    manager.delete(f"/api/admin/products/{APPLES_ID}")

    preview = upload(manager, PREVIEW).get_json()
    assert preview["lines"][0]["is_listed"] is False

    upload(manager, APPLY)
    assert stock_of(APPLES_ID) == 64
    assert database.query_one("SELECT is_listed FROM products WHERE product_id = %s",
                              (APPLES_ID,))["is_listed"] == 0


# =====================================================================
# Who may upload, and what counts as an upload
# =====================================================================

@pytest.mark.parametrize("path", [PREVIEW, APPLY])
def test_employees_and_customers_are_refused(employee, customer, path):
    assert upload(employee, path).status_code == 403
    assert upload(customer, path).status_code == 403
    assert stock_of(APPLES_ID) == 40


@pytest.mark.parametrize("path", [PREVIEW, APPLY])
def test_signed_out_visitors_are_refused(client, path):
    assert upload(client, path).status_code == 401


@pytest.mark.parametrize("path", [PREVIEW, APPLY])
def test_a_request_without_a_file_is_refused(manager, path):
    response = manager.post(path, data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert error_code(response) == "MISSING_FILE"
