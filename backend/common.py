"""Pieces every route module shares: error responses, reading request
bodies, and the sign-in and role checks.

Errors: raise ApiError anywhere in a request and the app turns it into

    {"ok": false, "error": {"code": "NOT_FOUND", "message": "..."}}

with the right HTTP status, so route code never builds error responses
by hand.

Roles: put @require_role(...) on a route. The signed-in user is loaded
from the database on every request, so a deactivated account loses
access immediately rather than when its session cookie expires.
"""

from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import jsonify, request, session

import db

CUSTOMER = ("customer",)
STAFF = ("employee", "manager")      # inventory work: managers can do it too
MANAGER = ("manager",)
ANY_USER = ("customer", "employee", "manager")


class ApiError(Exception):
    def __init__(self, message, status=400, code="BAD_REQUEST", **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.extra = extra


def error_response(exc):
    body = {"ok": False, "error": {"code": exc.code, "message": exc.message, **exc.extra}}
    return jsonify(body), exc.status


def ok(http_status=200, /, **data):
    # Positional-only, so a response field named "status" stays a field.
    return jsonify({"ok": True, **data}), http_status


# =====================================================================
# Reading the request body
# =====================================================================

def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def require_text(data, field, max_length=255):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"{field} is required")
    value = value.strip()
    if len(value) > max_length:
        raise ApiError(f"{field} must be at most {max_length} characters")
    return value


def optional_text(data, field, max_length=255):
    if data.get(field) is None:
        return None
    return require_text(data, field, max_length)


def require_int(data, field, minimum=None):
    value = data.get(field)
    # bool is a subclass of int in Python; true must not mean 1 here.
    if isinstance(value, bool):
        raise ApiError(f"{field} must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a whole number") from None
    if isinstance(value, float) and value != number:
        raise ApiError(f"{field} must be a whole number")
    if minimum is not None and number < minimum:
        raise ApiError(f"{field} must be at least {minimum}")
    return number


def require_decimal(data, field):
    """Money and weight arrive as strings ("4.99"). Numbers are accepted
    too but go through str() first so a float never touches the math."""
    value = data.get(field)
    if value is None or isinstance(value, bool):
        raise ApiError(f"{field} is required, as a decimal string like \"4.99\"")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ApiError(f"{field} must be a decimal value like \"4.99\"") from None
    if not number.is_finite():
        raise ApiError(f"{field} must be a decimal value like \"4.99\"")
    return number


def query_arg_decimal(name):
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ApiError(f"{name} must be a number") from None


# =====================================================================
# Sign-in and roles
# =====================================================================

def current_user():
    """The signed-in, active user, or None. Looked up once per request
    and kept on the request object, which never outlives the request."""
    if hasattr(request, "ofs_user"):
        return request.ofs_user
    user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = db.query_one(
            "SELECT user_id, email, full_name, phone, role, is_active "
            "FROM users WHERE user_id = %s",
            (user_id,),
        )
        if user is None or not user["is_active"]:
            session.clear()
            user = None
    request.ofs_user = user
    return user


def require_role(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                raise ApiError("Please sign in first", 401, "UNAUTHENTICATED")
            if user["role"] not in roles:
                raise ApiError("Your account does not have access to this", 403, "FORBIDDEN")
            return view(*args, **kwargs)
        return wrapper
    return decorator


def user_json(user):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "phone": user.get("phone"),
        "role": user["role"],
    }
