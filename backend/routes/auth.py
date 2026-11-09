"""Authentication and accounts (API design table I) and staff accounts
(table II).

    POST   /api/auth/register          public    create a customer account
    POST   /api/auth/login             public    start a session, returns the role
    POST   /api/auth/logout            signed in
    GET    /api/auth/me                signed in
    PATCH  /api/users/me               signed in  edit own name, phone, email, password

    GET    /api/admin/staff            manager
    POST   /api/admin/staff            manager   create an employee or manager
    PATCH  /api/admin/staff/<id>       manager   edit details or role, or reactivate
    DELETE /api/admin/staff/<id>       manager   deactivate (never deleted)

Passwords are stored only as salted PBKDF2 hashes. The session is a
signed cookie holding the user id; the role is re-read from the database
on every request (see common.current_user).
"""

import re

from flask import Blueprint, session
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import db
from common import (ANY_USER, CUSTOMER, MANAGER, ApiError, body, current_user, ok,
                    optional_text, require_role, require_text, user_json)
from routes import cart as cart_routes

auth_bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
STAFF_ROLES = ("employee", "manager")


def _hash(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


def _valid_email(data):
    email = require_text(data, "email").lower()
    if not EMAIL_PATTERN.match(email):
        raise ApiError("Please enter a valid email", code="INVALID_EMAIL")
    return email


def _valid_password(data, field="password"):
    password = data.get(field)
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
                       code="WEAK_PASSWORD")
    return password


def _create_user(email, password, full_name, role, phone=None):
    try:
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role) "
                "VALUES (%s, %s, %s, %s, %s)",
                (email, _hash(password), full_name, phone, role),
            )
            return cur.lastrowid
    except IntegrityError:
        # The UNIQUE constraint on email, which also covers two sign-ups
        # racing each other with the same address.
        raise ApiError("An account with that email already exists", 409, "EMAIL_TAKEN") from None


def _load_user(user_id):
    return db.query_one(
        "SELECT user_id, email, full_name, phone, role, is_active, is_guest, contact_email, "
        "       created_at FROM users WHERE user_id = %s",
        (user_id,),
    )


def _start_session(user):
    # Anything a signed-out visitor put in their cart survives sign-in.
    guest_cart = session.get("guest_cart")
    session.clear()
    session["user_id"] = user["user_id"]
    if user["role"] == "customer" and guest_cart:
        cart_routes.merge_guest_cart(user["user_id"], guest_cart)


# =====================================================================
# Own account
# =====================================================================

@auth_bp.post("/api/auth/register")
def register():
    data = body()
    email = _valid_email(data)
    password = _valid_password(data)
    full_name = require_text(data, "full_name", 120)
    phone = optional_text(data, "phone", 30)

    user_id = _create_user(email, password, full_name, "customer", phone)
    user = _load_user(user_id)
    _start_session(user)
    return ok(201, message="Account created", user=user_json(user))


@auth_bp.post("/api/auth/login")
def login():
    data = body()
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""

    row = db.query_one("SELECT * FROM users WHERE email = %s", (email,))
    # Same message whether the email or the password was wrong, so the
    # login form cannot be used to find out who has an account.
    if row is None or not check_password_hash(row["password_hash"], password):
        raise ApiError("Invalid email or password", 401, "INVALID_CREDENTIALS")
    if not row["is_active"]:
        raise ApiError("This account has been deactivated", 403, "ACCOUNT_INACTIVE")

    _start_session(row)
    return ok(message="Signed in", user=user_json(row))


@auth_bp.post("/api/auth/logout")
@require_role(*ANY_USER)
def logout():
    session.clear()
    return ok(message="Signed out")


@auth_bp.get("/api/auth/me")
@require_role(*ANY_USER)
def me():
    return ok(user=user_json(current_user()))


@auth_bp.patch("/api/users/me")
@require_role(*ANY_USER)
def update_me():
    """Body: any of full_name, phone, email, and new_password (which also
    needs current_password). Role and active status cannot be changed
    here."""
    data = body()
    user = current_user()
    changes = {}

    if "full_name" in data:
        changes["full_name"] = require_text(data, "full_name", 120)
    if "phone" in data:
        changes["phone"] = optional_text(data, "phone", 30)
    if "email" in data:
        changes["email"] = _valid_email(data)
    if "new_password" in data:
        stored = db.query_one("SELECT password_hash FROM users WHERE user_id = %s",
                              (user["user_id"],))
        current = data.get("current_password")
        if not isinstance(current, str) or not check_password_hash(stored["password_hash"], current):
            raise ApiError("Current password is incorrect", 403, "WRONG_PASSWORD")
        changes["password_hash"] = _hash(_valid_password(data, "new_password"))

    if not changes:
        raise ApiError("Nothing to update")

    _update_user(user["user_id"], changes)
    return ok(user=user_json(_load_user(user["user_id"])))


@auth_bp.delete("/api/users/me")
@require_role(*CUSTOMER)
def delete_me():
    """Body: password. Closes the customer's own account.

    Past orders and payments are business records, so the account row stays
    but is anonymised and deactivated: the name, email, phone and password
    are replaced, the cart is emptied, and saved addresses are removed (the
    ones that past orders were delivered to are only hidden). The email
    becomes free to register again. Refused while an order is still on its
    way."""
    user = current_user()
    if user.get("is_guest"):
        raise ApiError("Guest checkouts have no account to delete", 400, "GUEST_ACCOUNT")

    stored = db.query_one("SELECT password_hash FROM users WHERE user_id = %s", (user["user_id"],))
    password = body().get("password")
    if not isinstance(password, str) or not check_password_hash(stored["password_hash"], password):
        raise ApiError("Password is incorrect", 403, "WRONG_PASSWORD")

    active = db.query_one(
        "SELECT COUNT(*) AS n FROM orders WHERE user_id = %s AND status <> 'delivered'",
        (user["user_id"],))
    if active["n"]:
        raise ApiError("You still have orders that have not been delivered. "
                       "You can delete your account once they arrive.", 409, "ACTIVE_ORDERS")

    user_id = user["user_id"]
    with db.transaction() as cur:
        cart_routes.clear(cur, user_id)
        cur.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))
        cur.execute(
            "DELETE FROM addresses WHERE user_id = %s AND address_id NOT IN "
            "(SELECT address_id FROM orders WHERE user_id = %s)", (user_id, user_id))
        cur.execute("UPDATE addresses SET is_deleted = TRUE WHERE user_id = %s", (user_id,))
        cur.execute(
            "UPDATE users SET email = %s, full_name = 'Deleted customer', phone = NULL, "
            "contact_email = NULL, password_hash = %s, is_active = FALSE WHERE user_id = %s",
            (f"deleted-{user_id}@deleted.ofs.invalid", "!", user_id))
    session.clear()
    return ok(message="Your account has been deleted")


def _update_user(user_id, changes):
    assignments = ", ".join(f"{column} = %s" for column in changes)
    try:
        with db.transaction() as cur:
            cur.execute(f"UPDATE users SET {assignments} WHERE user_id = %s",
                        (*changes.values(), user_id))
    except IntegrityError:
        raise ApiError("An account with that email already exists", 409, "EMAIL_TAKEN") from None


# =====================================================================
# Staff accounts (manager only)
# =====================================================================

def _staff_json(row):
    return {**user_json(row), "is_active": bool(row["is_active"]), "created_at": row["created_at"]}


def _load_staff(user_id):
    row = _load_user(user_id)
    if row is None or row["role"] not in STAFF_ROLES:
        raise ApiError("No staff account with that id", 404, "NOT_FOUND")
    return row


def _staff_role(data):
    role = data.get("role")
    if role not in STAFF_ROLES:
        raise ApiError("role must be 'employee' or 'manager'", code="INVALID_ROLE")
    return role


def _lock_staff(cur):
    """Serialize staff changes and re-check permission using current rows.

    Two managers may both pass the request's initial role check, then try
    to remove each other. Taking the same ordered locks before either
    mutation makes the second request see the first request's committed
    role/active changes instead of relying on its cached sign-in data.
    """
    cur.execute(
        "SELECT user_id, role, is_active FROM users "
        "WHERE role IN ('employee', 'manager') ORDER BY user_id FOR UPDATE"
    )
    staff = {row["user_id"]: row for row in cur.fetchall()}
    actor = staff.get(current_user()["user_id"])
    if actor is None or not actor["is_active"]:
        raise ApiError("Please sign in again", 401, "UNAUTHENTICATED")
    if actor["role"] != "manager":
        raise ApiError("Your account does not have access to this", 403, "FORBIDDEN")
    return staff


def _change_staff(user_id, changes):
    """Apply validated fields with self/last-manager protection in one transaction."""
    try:
        with db.transaction() as cur:
            staff = _lock_staff(cur)
            target = staff.get(user_id)
            if target is None:
                raise ApiError("No staff account with that id", 404, "NOT_FOUND")
            if user_id == current_user()["user_id"]:
                if changes.get("is_active") is False:
                    raise ApiError("You cannot deactivate your own account", 409,
                                   "SELF_DEACTIVATION")
                if changes.get("role", "manager") != "manager":
                    raise ApiError("You cannot remove your own manager role", 409,
                                   "SELF_DEMOTION")
            removing_manager = (
                target["role"] == "manager" and target["is_active"] and
                (changes.get("role", "manager") != "manager" or
                 changes.get("is_active") is False)
            )
            active_managers = sum(row["role"] == "manager" and bool(row["is_active"])
                                  for row in staff.values())
            if removing_manager and active_managers <= 1:
                raise ApiError("At least one active manager must remain", 409, "LAST_MANAGER")
            assignments = ", ".join(f"{column} = %s" for column in changes)
            cur.execute(f"UPDATE users SET {assignments} WHERE user_id = %s",
                        (*changes.values(), user_id))
    except IntegrityError:
        raise ApiError("An account with that email already exists", 409, "EMAIL_TAKEN") from None


@auth_bp.get("/api/admin/staff")
@require_role(*MANAGER)
def list_staff():
    rows = db.query_all(
        "SELECT user_id, email, full_name, phone, role, is_active, created_at "
        "FROM users WHERE role IN ('employee', 'manager') ORDER BY role, full_name"
    )
    return ok(staff=[_staff_json(r) for r in rows])


@auth_bp.post("/api/admin/staff")
@require_role(*MANAGER)
def create_staff():
    data = body()
    email = _valid_email(data)
    password = _valid_password(data)
    full_name = require_text(data, "full_name", 120)
    role = _staff_role(data)
    phone = optional_text(data, "phone", 30)

    password_hash = _hash(password)
    try:
        with db.transaction() as cur:
            _lock_staff(cur)
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name, phone, role) "
                "VALUES (%s, %s, %s, %s, %s)",
                (email, password_hash, full_name, phone, role),
            )
            user_id = cur.lastrowid
    except IntegrityError:
        raise ApiError("An account with that email already exists", 409, "EMAIL_TAKEN") from None
    return ok(201, staff=_staff_json(_load_user(user_id)))


@auth_bp.patch("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def update_staff(user_id):
    """Body: any of full_name, phone, email, role, is_active (true only,
    to reactivate; use DELETE to deactivate)."""
    data = body()
    changes = {}

    if "full_name" in data:
        changes["full_name"] = require_text(data, "full_name", 120)
    if "phone" in data:
        changes["phone"] = optional_text(data, "phone", 30)
    if "email" in data:
        changes["email"] = _valid_email(data)
    if "role" in data:
        changes["role"] = _staff_role(data)
    if "is_active" in data:
        if data["is_active"] is not True:
            raise ApiError("Use DELETE to deactivate an account")
        changes["is_active"] = True

    if not changes:
        raise ApiError("Nothing to update")

    _change_staff(user_id, changes)
    return ok(staff=_staff_json(_load_user(user_id)))


@auth_bp.delete("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def deactivate_staff(user_id):
    _change_staff(user_id, {"is_active": False})
    return ok(staff=_staff_json(_load_user(user_id)))
