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
from common import (ANY_USER, MANAGER, ApiError, body, current_user, ok,
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
        "SELECT user_id, email, full_name, phone, role, is_active, created_at "
        "FROM users WHERE user_id = %s",
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

    user_id = _create_user(email, password, full_name, role, phone)
    return ok(201, staff=_staff_json(_load_user(user_id)))


@auth_bp.patch("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def update_staff(user_id):
    """Body: any of full_name, phone, email, role, is_active (true only,
    to reactivate; use DELETE to deactivate)."""
    data = body()
    _load_staff(user_id)
    changes = {}

    if "full_name" in data:
        changes["full_name"] = require_text(data, "full_name", 120)
    if "phone" in data:
        changes["phone"] = optional_text(data, "phone", 30)
    if "email" in data:
        changes["email"] = _valid_email(data)
    if "role" in data:
        changes["role"] = _staff_role(data)
        if user_id == current_user()["user_id"] and changes["role"] != "manager":
            raise ApiError("You cannot remove your own manager role", 409, "SELF_DEMOTION")
    if "is_active" in data:
        if data["is_active"] is not True:
            raise ApiError("Use DELETE to deactivate an account")
        changes["is_active"] = True

    if not changes:
        raise ApiError("Nothing to update")

    _update_user(user_id, changes)
    return ok(staff=_staff_json(_load_user(user_id)))


@auth_bp.delete("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def deactivate_staff(user_id):
    _load_staff(user_id)
    if user_id == current_user()["user_id"]:
        raise ApiError("You cannot deactivate your own account", 409, "SELF_DEACTIVATION")
    with db.transaction() as cur:
        cur.execute("UPDATE users SET is_active = FALSE WHERE user_id = %s", (user_id,))
    return ok(staff=_staff_json(_load_user(user_id)))
