import os
import re
import uuid
from pathlib import Path

from flask import Blueprint, Response, request

import db
from common import STAFF, ApiError, ok, require_role
from routes.inventory import _load, inventory_json

product_images_bp = Blueprint("product_images", __name__)

UPLOAD_DIR = Path(os.environ.get("PRODUCT_IMAGE_DIR")
                  or Path(__file__).resolve().parent.parent / "uploads" / "products")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
KEY_PREFIX = "upload:"
FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")
MIME_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


# Identifies JPEG, PNG or WebP from the file's first bytes.
def _detect_type(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


# Returns the uploaded file name inside an image key, if it is one.
def _stored_filename(image_key):
    if image_key and image_key.startswith(KEY_PREFIX):
        name = image_key[len(KEY_PREFIX):]
        if FILENAME_PATTERN.match(name):
            return name
    return None


# Forgets an uploaded picture (its database row and any old file) when it is replaced or removed.
def _delete_picture(image_key):
    name = _stored_filename(image_key)
    if name:
        with db.transaction() as cur:
            cur.execute("DELETE FROM product_pictures WHERE filename = %s", (name,))
        (UPLOAD_DIR / name).unlink(missing_ok=True)


# POST /api/admin/products/<int:product_id>/image: Saves a staff member's picture for a product and points the product at it.
@product_images_bp.post("/api/admin/products/<int:product_id>/image")
@require_role(*STAFF)
def upload_image(product_id):
    product = _load(product_id)
    upload = request.files.get("image")
    if upload is None:
        raise ApiError("Choose a picture to upload", code="NO_IMAGE")

    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError("The picture must be 5 MB or smaller", 413, "IMAGE_TOO_LARGE")
    kind = _detect_type(data)
    if kind is None:
        raise ApiError("The picture must be a JPEG, PNG or WebP file", 415, "UNSUPPORTED_IMAGE")

    name = f"{uuid.uuid4().hex}.{kind}"
    with db.transaction() as cur:
        cur.execute("INSERT INTO product_pictures (filename, mime_type, data) VALUES (%s, %s, %s)",
                    (name, MIME_TYPES[kind], data))
        cur.execute("UPDATE products SET image_key = %s WHERE product_id = %s",
                    (f"{KEY_PREFIX}{name}", product_id))

    _delete_picture(product["image_key"])
    return ok(product=inventory_json(_load(product_id)))


# DELETE /api/admin/products/<int:product_id>/image: Removes a product's picture (the shop then shows a placeholder).
@product_images_bp.delete("/api/admin/products/<int:product_id>/image")
@require_role(*STAFF)
def remove_image(product_id):
    product = _load(product_id)
    with db.transaction() as cur:
        cur.execute("UPDATE products SET image_key = NULL WHERE product_id = %s", (product_id,))
    _delete_picture(product["image_key"])
    return ok(product=inventory_json(_load(product_id)))


# Finds a picture in the database; one that is still only a file on this computer is copied in first.
def _picture(filename, kind):
    row = db.query_one("SELECT mime_type, data FROM product_pictures WHERE filename = %s", (filename,))
    if row is None and (UPLOAD_DIR / filename).is_file():
        data = (UPLOAD_DIR / filename).read_bytes()
        with db.transaction() as cur:
            cur.execute("INSERT IGNORE INTO product_pictures (filename, mime_type, data) VALUES (%s, %s, %s)",
                        (filename, MIME_TYPES[kind], data))
        row = {"mime_type": MIME_TYPES[kind], "data": data}
    return row


# GET /api/product-images/<filename>: Serves an uploaded picture to the shop.
@product_images_bp.get("/api/product-images/<filename>")
def serve_image(filename):
    match = FILENAME_PATTERN.match(filename)
    row = _picture(filename, match.group(1)) if match else None
    if row is None:
        raise ApiError("No such picture", 404, "NOT_FOUND")
    return Response(row["data"], mimetype=row["mime_type"], headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})
