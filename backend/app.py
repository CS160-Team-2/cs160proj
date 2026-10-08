"""OFS API server.

Run:  python app.py      (listens on http://localhost:5001)

Port 5001, not the Flask default of 5000, because macOS Monterey and
later run AirPlay Receiver on port 5000.

The endpoints follow the API design (Part II, section V). Each area of
it lives in its own module under routes/:

    routes/auth.py           sign-in, own account, staff accounts      tables I, II
    routes/addresses.py      delivery addresses                        table III
    routes/catalog.py        products and categories                   table IV
    routes/cart.py           shopping cart                             table V
    routes/orders.py         checkout, order history, tracking         table VI
    routes/admin_orders.py   manager order monitor                     table VII
    routes/inventory.py      products and stock for staff              table VIII
    routes/delivery.py       trips, routes, dispatch                   table IX
    routes/fleet.py          vehicle callbacks                         table X

Conventions, from the API design:
  - JSON in and out. Success: {"ok": true, ...}. Failure:
    {"ok": false, "error": {"code": "...", "message": "..."}}.
  - Money and weight are sent as strings ("38.94"), never JSON numbers.
  - Sign-in is a session cookie. The role is checked on the server on
    every request.
"""

import os
from datetime import date, datetime
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import db
from common import ApiError, error_response, ok
from routes.addresses import addresses_bp
from routes.admin_orders import admin_orders_bp
from routes.auth import auth_bp
from routes.cart import cart_bp
from routes.catalog import catalog_bp
from routes.delivery import delivery_bp
from routes.fleet import fleet_bp
from routes.inventory import inventory_bp
from routes.orders import orders_bp

DEV_SECRET_KEY = "dev-only-secret-change-me"


class OfsJSONProvider(DefaultJSONProvider):
    """Decimals become strings so no precision is lost on the way to the
    browser, which only displays them and never does arithmetic on them.
    Dates become ISO 8601 strings, which JavaScript's Date understands."""

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

    # Signs the session cookie. Anyone who knows it can forge a sign-in,
    # so anything other than a laptop must set its own SECRET_KEY.
    app.secret_key = os.environ.get("SECRET_KEY") or DEV_SECRET_KEY
    if app.secret_key == DEV_SECRET_KEY:
        app.logger.warning("SECRET_KEY is not set; using the development key")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )

    # In development React runs on a different port, so the browser treats
    # it as a different origin. supports_credentials lets the session cookie
    # through. Behind Apache (see deploy/) both share one origin.
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    CORS(app, resources={r"/api/*": {"origins": [frontend_origin]}}, supports_credentials=True)

    for blueprint in (auth_bp, addresses_bp, catalog_bp, cart_bp, orders_bp,
                      admin_orders_bp, inventory_bp, delivery_bp, fleet_bp):
        app.register_blueprint(blueprint)

    @app.get("/api/health")
    def health():
        try:
            version = db.db_version()
        except Exception:                             # noqa: BLE001
            version = None
        return ok(service="OFS API", database="up" if version else "down",
                  mysql_version=version)

    app.register_error_handler(ApiError, error_response)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        # 404 for unknown paths, 405 for wrong methods, and so on, as JSON.
        code = (exc.name or "ERROR").upper().replace(" ", "_")
        return error_response(ApiError(exc.description or exc.name, exc.code, code))

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception("Unhandled error")
        return error_response(ApiError("Something went wrong on our side", 500, "SERVER_ERROR"))

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True)
