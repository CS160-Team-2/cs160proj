"""Product pictures uploaded by staff.

    POST   /api/admin/products/<id>/image   multipart form, field "image"; replaces the picture
    DELETE /api/admin/products/<id>/image   removes it (the shop shows a grey placeholder)
    GET    /api/product-images/<filename>   serves an uploaded picture, public

The picture file is saved on the server, in backend/uploads/products (or
PRODUCT_IMAGE_DIR), under a random name. The database stores only a
short reference in products.image_key: "upload:<random name>". Products
that ship with the app keep a plain name like "apple", which the
frontend maps to a bundled picture, so both kinds work side by side.

The file is judged by its first bytes, never by the name or type the
browser claims, and only JPEG, PNG and WebP are accepted (not SVG, which
can carry scripts). Files are limited to 5 MB.
"""

import os
import re
import uuid
from pathlib import Path

from flask import Blueprint, request, send_from_directory

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


def _detect_type(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _stored_filename(image_key):
    if image_key and image_key.startswith(KEY_PREFIX):
        name = image_key[len(KEY_PREFIX):]
        if FILENAME_PATTERN.match(name):
            return name
    return None


def _delete_file(image_key):
    name = _stored_filename(image_key)
    if name:
        (UPLOAD_DIR / name).unlink(missing_ok=True)


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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{kind}"
    (UPLOAD_DIR / name).write_bytes(data)
    try:
        with db.transaction() as cur:
            cur.execute("UPDATE products SET image_key = %s WHERE product_id = %s",
                        (f"{KEY_PREFIX}{name}", product_id))
    except Exception:
        (UPLOAD_DIR / name).unlink(missing_ok=True)
        raise

    _delete_file(product["image_key"])
    return ok(product=inventory_json(_load(product_id)))


@product_images_bp.delete("/api/admin/products/<int:product_id>/image")
@require_role(*STAFF)
def remove_image(product_id):
    product = _load(product_id)
    with db.transaction() as cur:
        cur.execute("UPDATE products SET image_key = NULL WHERE product_id = %s", (product_id,))
    _delete_file(product["image_key"])
    return ok(product=inventory_json(_load(product_id)))


@product_images_bp.get("/api/product-images/<filename>")
def serve_image(filename):
    match = FILENAME_PATTERN.match(filename)
    if not match:
        raise ApiError("No such picture", 404, "NOT_FOUND")
    response = send_from_directory(UPLOAD_DIR, filename, mimetype=MIME_TYPES[match.group(1)],
                                   max_age=31536000)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
