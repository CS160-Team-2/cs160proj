from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import jsonify, request, session

import db

CUSTOMER = ("customer",)
STAFF = ("employee", "manager")
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
    response = jsonify(body)
    response.status_code = exc.status
    if "retry_after" in exc.extra:
        response.headers["Retry-After"] = str(exc.extra["retry_after"])
    return response


def ok(http_status=200, /, **data):
    return jsonify({"ok": True, **data}), http_status


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


# Money and weight arrive as strings ("4.99").
def require_decimal(data, field):
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


# A whole number from the query string, or the default when it is missing.
def query_arg_int(name, default):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        raise ApiError(f"{name} must be a whole number") from None


def query_arg_decimal(name):
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ApiError(f"{name} must be a number") from None


# The signed-in, active user, or None.
def current_user():
    if hasattr(request, "ofs_user"):
        return request.ofs_user
    user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = db.query_one(
            "SELECT user_id, email, full_name, phone, role, is_active, is_guest, contact_email "
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
    is_guest = bool(user.get("is_guest"))
    return {
        "user_id": user["user_id"],
        "email": user.get("contact_email") if is_guest else user["email"],
        "is_guest": is_guest,
        "full_name": user["full_name"],
        "phone": user.get("phone"),
        "role": user["role"],
    }
