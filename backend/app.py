import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Flask, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import db
from services.vehicle import start_recovery
from common import ApiError, error_response, ok
from routes.addresses import addresses_bp
from routes.admin_orders import admin_orders_bp
from routes.admin_problems import admin_problems_bp
from routes.admin_vehicles import admin_vehicles_bp
from routes.auth import auth_bp
from routes.cart import cart_bp
from routes.catalog import catalog_bp
from routes.delivery import delivery_bp
from routes.fleet import fleet_bp
from routes.guest import guest_bp
from routes.inventory import inventory_bp
from routes.manifests import manifests_bp
from routes.orders import orders_bp
from routes.product_images import product_images_bp

DEV_SECRET_KEY = "dev-only-secret-change-me"
PRIVATE_PREFIXES = ("/api/auth", "/api/users", "/api/cart", "/api/checkout", "/api/orders", "/api/payments",
                    "/api/admin", "/api/staff")


# Turns decimals into strings and dates into ISO text for JSON.
class OfsJSONProvider(DefaultJSONProvider):

    @staticmethod
    def default(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return DefaultJSONProvider.default(value)


def create_app():
    app = Flask(__name__)
    app.json = OfsJSONProvider(app)
    app.json.sort_keys = False

    app.secret_key = os.environ.get("SECRET_KEY") or DEV_SECRET_KEY
    if app.secret_key == DEV_SECRET_KEY:
        app.logger.warning("SECRET_KEY is not set; using the development key")
        if os.environ.get("SESSION_COOKIE_SECURE") == "1":
            raise RuntimeError("SECRET_KEY must be set when SESSION_COOKIE_SECURE=1 (HTTPS). See SETUP.md, Security.")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.environ.get("CART_SESSION_DAYS", "14"))),
    )

    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    CORS(app, resources={r"/api/*": {"origins": [frontend_origin]}}, supports_credentials=True)

    for blueprint in (auth_bp, addresses_bp, catalog_bp, cart_bp, orders_bp,
                      admin_orders_bp, admin_problems_bp, admin_vehicles_bp, inventory_bp,
                      manifests_bp, delivery_bp, fleet_bp, guest_bp, product_images_bp):
        app.register_blueprint(blueprint)

    # GET /api/health: Reports whether the API and its database are up.
    @app.get("/api/health")
    def health():
        try:
            version = db.db_version()
        except Exception:                             # noqa: BLE001
            version = None
        return ok(service="OFS API", database="up" if version else "down",
                  mysql_version=version)

    proxies = int(os.environ.get("TRUSTED_PROXIES", "0") or 0)
    if proxies > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies)

    @app.after_request
    def safety_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith(PRIVATE_PREFIXES):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.register_error_handler(ApiError, error_response)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        code = (exc.name or "ERROR").upper().replace(" ", "_")
        return error_response(ApiError(exc.description or exc.name, exc.code, code))

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception("Unhandled error")
        return error_response(ApiError("Something went wrong on our side", 500, "SERVER_ERROR"))

    start_recovery()
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True)
