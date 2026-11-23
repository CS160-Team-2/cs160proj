import io
import re

import db as database

import pytest

from conftest import APPLES_ID, error_code, make_product, requires_mysql
from routes import product_images

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 200
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture(autouse=True)
def picture_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(product_images, "UPLOAD_DIR", tmp_path)
    return tmp_path


# Every picture row in the database, as (filename, mime type, bytes).
def stored():
    return [(r["filename"], r["mime_type"], bytes(r["data"])) for r in
            database.query_all("SELECT filename, mime_type, data FROM product_pictures ORDER BY filename")]


# Sends a picture to the upload route.
def upload(user, product_id, data, name="photo.jpg", field="image"):
    return user.post(f"/api/admin/products/{product_id}/image",
                     data={field: (io.BytesIO(data), name)}, content_type="multipart/form-data")


# The image key the shop has for a product.
def key_of(client, product_id):
    return client.get(f"/api/products/{product_id}").get_json()["product"]["image_key"]


@pytest.mark.parametrize("data, extension, mime", [(JPEG, "jpg", "image/jpeg"), (PNG, "png", "image/png"), (WEBP, "webp", "image/webp")])
def test_a_real_picture_is_saved_and_shown_by_the_shop(employee, client, picture_folder, data, extension, mime):
    response = upload(employee, APPLES_ID, data, name=f"anything.{extension}")

    assert response.status_code == 200
    key = key_of(client, APPLES_ID)
    assert re.fullmatch(rf"upload:[0-9a-f]{{32}}\.{extension}", key)
    assert stored() == [(key.removeprefix("upload:"), mime, data)]
    assert list(picture_folder.iterdir()) == []
    served = client.get(f"/api/product-images/{key.removeprefix('upload:')}")
    assert served.status_code == 200 and served.data == data
    assert served.mimetype == mime and served.headers["X-Content-Type-Options"] == "nosniff"
    assert "immutable" in served.headers["Cache-Control"]


@pytest.mark.parametrize("data, name", [
    (b"this is just text", "photo.jpg"),
    (SVG, "logo.svg"),
    (SVG, "logo.png"),
    (b"", "empty.png"),
    (b"GIF89a" + b"\x00" * 50, "pic.gif"),
    (b"%PDF-1.7 " + b"\x00" * 50, "doc.jpg"),
])
def test_anything_that_is_not_jpeg_png_or_webp_is_refused(employee, client, picture_folder, data, name):
    before = key_of(client, APPLES_ID)

    response = upload(employee, APPLES_ID, data, name=name)

    assert response.status_code == 415 and error_code(response) == "UNSUPPORTED_IMAGE"
    assert key_of(client, APPLES_ID) == before and stored() == []


def test_a_picture_over_five_megabytes_is_refused_and_nothing_is_saved(employee, client, picture_folder):
    response = upload(employee, APPLES_ID, JPEG + b"\x00" * (5 * 1024 * 1024))

    assert response.status_code == 413 and error_code(response) == "IMAGE_TOO_LARGE"
    assert stored() == []


def test_a_picture_of_exactly_five_megabytes_is_accepted(employee, picture_folder):
    data = JPEG + b"\x00" * (5 * 1024 * 1024 - len(JPEG))

    assert upload(employee, APPLES_ID, data).status_code == 200


def test_the_request_must_carry_a_picture(employee):
    response = upload(employee, APPLES_ID, JPEG, field="file")

    assert response.status_code == 400 and error_code(response) == "NO_IMAGE"


def test_an_unknown_product_is_a_404_and_saves_nothing(employee, picture_folder):
    assert upload(employee, 99999, JPEG).status_code == 404
    assert employee.delete("/api/admin/products/99999/image").status_code == 404
    assert stored() == []


def test_only_staff_may_upload_or_remove_a_picture(customer, client, picture_folder):
    assert upload(customer, APPLES_ID, JPEG).status_code == 403
    assert upload(client, APPLES_ID, JPEG).status_code == 401
    assert customer.delete(f"/api/admin/products/{APPLES_ID}/image").status_code == 403
    assert client.delete(f"/api/admin/products/{APPLES_ID}/image").status_code == 401
    assert stored() == []


def test_replacing_a_picture_deletes_the_old_one(employee, client, picture_folder):
    upload(employee, APPLES_ID, JPEG)
    first = key_of(client, APPLES_ID).removeprefix("upload:")

    upload(employee, APPLES_ID, PNG, name="new.png")

    second = key_of(client, APPLES_ID).removeprefix("upload:")
    assert first != second and second.endswith(".png")
    assert [name for name, _, _ in stored()] == [second]
    assert client.get(f"/api/product-images/{first}").status_code == 404


def test_removing_a_picture_clears_the_product_and_deletes_it(employee, client, picture_folder):
    upload(employee, APPLES_ID, JPEG)

    response = employee.delete(f"/api/admin/products/{APPLES_ID}/image")

    assert response.status_code == 200
    assert key_of(client, APPLES_ID) is None
    assert stored() == []


def test_removing_the_picture_of_a_product_that_has_none_is_fine(employee, client):
    product_id = make_product(name="Plain Item")

    assert employee.delete(f"/api/admin/products/{product_id}/image").status_code == 200
    assert key_of(client, product_id) is None


def test_a_bundled_picture_name_is_not_an_upload_so_nothing_else_is_deleted(employee, client, picture_folder):
    upload(employee, 2, JPEG)
    (picture_folder / "keep.txt").write_text("untouched")
    assert key_of(client, APPLES_ID) == "apple"

    employee.delete(f"/api/admin/products/{APPLES_ID}/image")

    assert (picture_folder / "keep.txt").exists() and len(stored()) == 1


@pytest.mark.parametrize("name", [
    "../app.py", "..%2Fapp.py", "%2e%2e/app.py", "a.jpg", "A" * 32 + ".jpg", "0" * 32 + ".gif",
    "0" * 31 + ".jpg", "0" * 33 + ".jpg", "0" * 32 + ".jpg.exe", "0" * 32 + ".svg",
])
def test_the_public_picture_address_serves_only_real_picture_names(client, name):
    assert client.get(f"/api/product-images/{name}").status_code == 404


def test_a_well_formed_name_with_no_file_is_a_404(client):
    assert client.get(f"/api/product-images/{'0' * 32}.jpg").status_code == 404


# EB3: the picture belongs to the database, so a copy of the database has it, wherever it is used.
def test_the_picture_comes_back_after_the_files_folder_is_gone(employee, client, picture_folder):
    upload(employee, APPLES_ID, PNG, name="a.png")
    name = key_of(client, APPLES_ID).removeprefix("upload:")
    picture_folder.rmdir()

    served = client.get(f"/api/product-images/{name}")

    assert served.status_code == 200 and served.data == PNG


def test_an_old_picture_that_is_only_a_file_is_still_shown_and_is_copied_into_the_database(employee, client, picture_folder):
    name = "0123456789abcdef0123456789abcdef.png"
    (picture_folder / name).write_bytes(PNG)
    with database.transaction() as cur:
        cur.execute("UPDATE products SET image_key = %s WHERE product_id = %s", (f"upload:{name}", APPLES_ID))
    assert stored() == []

    served = client.get(f"/api/product-images/{name}")

    assert served.status_code == 200 and served.data == PNG and served.mimetype == "image/png"
    assert stored() == [(name, "image/png", PNG)]
    (picture_folder / name).unlink()
    assert client.get(f"/api/product-images/{name}").data == PNG


def test_removing_an_old_file_picture_deletes_the_file_and_the_copy(employee, client, picture_folder):
    name = "fedcba9876543210fedcba9876543210.jpg"
    (picture_folder / name).write_bytes(JPEG)
    with database.transaction() as cur:
        cur.execute("UPDATE products SET image_key = %s WHERE product_id = %s", (f"upload:{name}", APPLES_ID))
    client.get(f"/api/product-images/{name}")

    employee.delete(f"/api/admin/products/{APPLES_ID}/image")

    assert stored() == [] and not (picture_folder / name).exists()
