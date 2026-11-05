"""Restocking from a delivery manifest. Managers only.

    POST /api/admin/inventory/manifest/preview   multipart, field "file": what would change
    POST /api/admin/inventory/manifest           multipart, field "file": apply it

The file rules are in manifest.py. Preview never changes anything. Apply
reads the file again itself rather than trusting an earlier preview, and
saves every line in one transaction, or nothing at all: a manifest with
any problem is refused whole. Each stock change goes into inventory_log
like a manual adjustment, with the reason
"Delivery manifest #<id> (<filename>)", so it shows in the stock history.

A file whose contents were already applied is refused (delivery_manifests
keeps each file's fingerprint), so one delivery cannot be counted twice.
"""

import os

from flask import Blueprint, request
from pymysql.err import IntegrityError

import db
from common import MANAGER, ApiError, current_user, ok, require_role
from manifest import MAX_BYTES, fingerprint, read_manifest
from routes.inventory import MAX_INVENTORY_INT

manifests_bp = Blueprint("manifests", __name__)


def _upload():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("Choose a CSV file to upload", 400, "MISSING_FILE")
    # One byte past the limit is enough for read_manifest to refuse it.
    raw = upload.stream.read(MAX_BYTES + 1)
    return os.path.basename(upload.filename)[:255], raw


def _catalog():
    return db.query_all("SELECT product_id, name, is_listed FROM products ORDER BY product_id")


def _applied_before(file_fingerprint):
    row = db.query_one(
        "SELECT m.manifest_id, m.filename, m.applied_at, u.full_name AS applied_by "
        "FROM delivery_manifests m JOIN users u ON u.user_id = m.applied_by "
        "WHERE m.fingerprint = %s", (file_fingerprint,))
    return row


def _already_applied_error(previous):
    return ApiError(f"This delivery manifest was already applied as manifest "
                    f"#{previous['manifest_id']} by {previous['applied_by']}. "
                    "Nothing was changed.", 409, "MANIFEST_ALREADY_APPLIED")


@manifests_bp.post("/api/admin/inventory/manifest/preview")
@require_role(*MANAGER)
def preview_manifest():
    filename, raw = _upload()
    result = read_manifest(raw, _catalog())

    stock = {}
    if result.lines:
        ids = [line["product_id"] for line in result.lines]
        rows = db.query_all(
            f"SELECT product_id, quantity_in_stock FROM inventory "
            f"WHERE product_id IN ({db.placeholders(ids)})", tuple(ids))
        stock = {row["product_id"]: row["quantity_in_stock"] for row in rows}

    previous = _applied_before(fingerprint(raw))
    return ok(
        filename=filename,
        lines=[{**line, "stock_now": stock.get(line["product_id"], 0),
                "stock_after": stock.get(line["product_id"], 0) + line["quantity"]}
               for line in result.lines],
        problems=result.problems,
        can_apply=result.ok and previous is None,
        already_applied=previous,
    )


@manifests_bp.post("/api/admin/inventory/manifest")
@require_role(*MANAGER)
def apply_manifest():
    filename, raw = _upload()
    result = read_manifest(raw, _catalog())
    if not result.ok:
        raise ApiError("This manifest has problems, so nothing was changed. "
                       "Fix the file and upload it again.", 422, "MANIFEST_INVALID",
                       problems=result.problems)

    file_fingerprint = fingerprint(raw)
    previous = _applied_before(file_fingerprint)
    if previous:
        raise _already_applied_error(previous)

    manager_id = current_user()["user_id"]
    total_units = sum(line["quantity"] for line in result.lines)
    applied = []
    with db.transaction() as cur:
        try:
            cur.execute(
                "INSERT INTO delivery_manifests (fingerprint, filename, applied_by, line_count, "
                "total_units) VALUES (%s, %s, %s, %s, %s)",
                (file_fingerprint, filename, manager_id, len(result.lines), total_units))
        except IntegrityError:
            # Another manager applied the same file between our check and this insert.
            raise _already_applied_error(_applied_before(file_fingerprint)) from None
        manifest_id = cur.lastrowid
        reason = f"Delivery manifest #{manifest_id} ({filename})"[:255]

        # Lock rows in product order so two uploads at once cannot deadlock.
        for line in sorted(result.lines, key=lambda entry: entry["product_id"]):
            cur.execute("SELECT quantity_in_stock FROM inventory WHERE product_id = %s FOR UPDATE",
                        (line["product_id"],))
            old = cur.fetchone()["quantity_in_stock"]
            new = old + line["quantity"]
            if new > MAX_INVENTORY_INT:
                raise ApiError(f'"{line["name"]}" would go over the stock limit. Nothing was changed.',
                               409, "STOCK_LIMIT")
            cur.execute("UPDATE inventory SET quantity_in_stock = %s WHERE product_id = %s",
                        (new, line["product_id"]))
            cur.execute(
                "INSERT INTO inventory_log (product_id, changed_by, change_qty, old_quantity, "
                "new_quantity, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                (line["product_id"], manager_id, line["quantity"], old, new, reason))
            applied.append({**line, "stock_now": old, "stock_after": new})

    return ok(201,
              manifest={"manifest_id": manifest_id, "filename": filename,
                        "line_count": len(result.lines), "total_units": total_units},
              lines=applied)
