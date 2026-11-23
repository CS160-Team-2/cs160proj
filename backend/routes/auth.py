import re

from flask import Blueprint, request, session
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import db
import ratelimit
from common import (ANY_USER, CUSTOMER, MANAGER, ApiError, body, current_user, ok,
                    optional_text, require_role, require_text, user_json)
from routes import cart as cart_routes

auth_bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
NO_SUCH_USER_HASH = generate_password_hash("no account has this password")
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
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ApiError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters", code="WEAK_PASSWORD")
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
        raise ApiError("An account with that email already exists", 409, "EMAIL_TAKEN") from None


def _load_user(user_id):
    return db.query_one(
        "SELECT user_id, email, full_name, phone, role, is_active, is_guest, contact_email, "
        "       created_at FROM users WHERE user_id = %s",
        (user_id,),
    )


# Reads the "Remember me" choice; only an explicit false turns it off, so older callers keep the 14-day sign-in.
def _remember(data):
    return data.get("remember") is not False


def _start_session(user, remember=True):
    guest_cart = session.get("guest_cart")
    session.clear()
    session["user_id"] = user["user_id"]
    session.permanent = user["role"] == "customer" and remember
    if user["role"] == "customer" and guest_cart:
        cart_routes.merge_guest_cart(user["user_id"], guest_cart)


# POST /api/auth/register: Creates a customer account and signs it in.
@auth_bp.post("/api/auth/register")
def register():
    data = body()
    email = _valid_email(data)
    password = _valid_password(data)
    full_name = require_text(data, "full_name", 120)
    phone = optional_text(data, "phone", 30)

    user_id = _create_user(email, password, full_name, "customer", phone)
    user = _load_user(user_id)
    _start_session(user, _remember(data))
    return ok(201, message="Account created", user=user_json(user))


# POST /api/auth/login: Signs a customer or staff member in.
@auth_bp.post("/api/auth/login")
def login():
    data = body()
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    password = data.get("password") if isinstance(data.get("password"), str) else ""

    address = request.remote_addr or "unknown"
    keys = (f"{address}|{email}", address)
    ratelimit.SIGN_IN.check(keys[0])
    ratelimit.SIGN_IN_ANY.check(address)

    row = db.query_one("SELECT * FROM users WHERE email = %s", (email,))
    stored_hash = row["password_hash"] if row is not None else NO_SUCH_USER_HASH
    password_ok = check_password_hash(stored_hash, password)
    if row is None or not password_ok:
        ratelimit.SIGN_IN.fail(keys[0])
        ratelimit.SIGN_IN_ANY.fail(address)
        raise ApiError("Invalid email or password", 401, "INVALID_CREDENTIALS")
    ratelimit.SIGN_IN.clear(keys[0])
    if not row["is_active"]:
        raise ApiError("This account has been deactivated", 403, "ACCOUNT_INACTIVE")

    _start_session(row, _remember(data))
    return ok(message="Signed in", user=user_json(row))


# POST /api/auth/logout: Signs the current user out.
@auth_bp.post("/api/auth/logout")
@require_role(*ANY_USER)
def logout():
    session.clear()
    return ok(message="Signed out")


# GET /api/auth/me: Returns the signed-in user.
@auth_bp.get("/api/auth/me")
@require_role(*ANY_USER)
def me():
    return ok(user=user_json(current_user()))


# PATCH /api/users/me: Updates the signed-in user's name, phone, email or password.
@auth_bp.patch("/api/users/me")
@require_role(*ANY_USER)
def update_me():
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
        ratelimit.PASSWORD_CHECK.check(f"user:{user['user_id']}")
        if not isinstance(current, str) or not check_password_hash(stored["password_hash"], current):
            ratelimit.PASSWORD_CHECK.fail(f"user:{user['user_id']}")
            raise ApiError("Current password is incorrect", 403, "WRONG_PASSWORD")
        ratelimit.PASSWORD_CHECK.clear(f"user:{user['user_id']}")
        changes["password_hash"] = _hash(_valid_password(data, "new_password"))

    if not changes:
        raise ApiError("Nothing to update")

    _update_user(user["user_id"], changes)
    return ok(user=user_json(_load_user(user["user_id"])))


# DELETE /api/users/me: Body: password. Closes the customer's own account.
@auth_bp.delete("/api/users/me")
@require_role(*CUSTOMER)
def delete_me():
    user = current_user()
    if user.get("is_guest"):
        raise ApiError("Guest checkouts have no account to delete", 400, "GUEST_ACCOUNT")

    stored = db.query_one("SELECT password_hash FROM users WHERE user_id = %s", (user["user_id"],))
    password = body().get("password")
    ratelimit.PASSWORD_CHECK.check(f"user:{user['user_id']}")
    if not isinstance(password, str) or not check_password_hash(stored["password_hash"], password):
        ratelimit.PASSWORD_CHECK.fail(f"user:{user['user_id']}")
        raise ApiError("Password is incorrect", 403, "WRONG_PASSWORD")
    ratelimit.PASSWORD_CHECK.clear(f"user:{user['user_id']}")

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


# Serialize staff changes and re-check permission using current rows.
def _lock_staff(cur):
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


# Apply validated fields with self/last-manager protection in one transaction.
def _change_staff(user_id, changes):
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


# GET /api/admin/staff: Lists staff accounts.
@auth_bp.get("/api/admin/staff")
@require_role(*MANAGER)
def list_staff():
    rows = db.query_all(
        "SELECT user_id, email, full_name, phone, role, is_active, created_at "
        "FROM users WHERE role IN ('employee', 'manager') ORDER BY role, full_name"
    )
    return ok(staff=[_staff_json(r) for r in rows])


# POST /api/admin/staff: Adds an employee or manager account.
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


# PATCH /api/admin/staff/<int:user_id>: Body: any of full_name, phone, email, role, is_active (true only, to reactivate; use DELETE to deactivate).
@auth_bp.patch("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def update_staff(user_id):
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


# DELETE /api/admin/staff/<int:user_id>
@auth_bp.delete("/api/admin/staff/<int:user_id>")
@require_role(*MANAGER)
def deactivate_staff(user_id):
    _change_staff(user_id, {"is_active": False})
    return ok(staff=_staff_json(_load_user(user_id)))
