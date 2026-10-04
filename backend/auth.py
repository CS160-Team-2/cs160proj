import db

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# Register
@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()

    # Validate input
    if "@" not in email:
        return jsonify({"error": "Please enter a valid email"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not full_name:
        return jsonify({"error": "Full name is required"}), 400

    # Check if email exist
    if db.get_user_by_email(email):
        return jsonify({"error": "Email already exists"}), 409

    # Hash pw before saving
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    user_id = db.create_user(email, password_hash, full_name)

    return jsonify({ "message": "Account created", "user_id": user_id}), 201


# Login
@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = db.get_user_by_email(email)

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    # Account is deactivated
    if not user["is_active"]:
        return jsonify({"error": "This account is deactivated"}), 403

    session.clear()
    session["user_id"] = user["user_id"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Login successful",
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "role": user["role"]
    })


# Logout
@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"})


# Check current user
@auth_bp.get("/me")
def me():
    user_id = session.get("user_id")

    if user_id is None:
        return jsonify({"error": "Not logged in"}), 401
    user = db.get_user_by_id(user_id)

    # User deleted after log in
    if user is None or not user["is_active"]:
        session.clear()
        return jsonify({"error": "Not logged in"}), 401

    return jsonify({
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"]
    })