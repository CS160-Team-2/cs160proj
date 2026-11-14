"""PayPal payments through the Orders v2 API (customer backlog C5b).

How a PayPal payment goes:

  1. The checkout page asks OFS to create a PayPal order. OFS works out the
     total from the cart itself (never from the browser) and creates the
     order at PayPal. Only the PayPal order id goes back to the page.
  2. PayPal's own buttons take the customer through approval. The card,
     the PayPal login and any bank checks happen on PayPal's pages, so
     OFS never sees them.
  3. The page sends "paypal:<order id>" as the payment token. charge()
     asks PayPal about that order and refuses it unless it is approved and
     its amount and currency match this checkout exactly, so a customer
     cannot approve a cheap order and use it for a dearer one. Only then
     does it capture the money.

The same ChargeResult / refund() shape as the Stripe and fake gateways, so
routes/orders.py treats every gateway alike. Sandbox by default; a live
account is refused unless PAYPAL_ALLOW_LIVE=1.
"""

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.request
import uuid
from decimal import ROUND_HALF_UP, Decimal

from services.payments import ChargeResult, PaymentGatewayError

log = logging.getLogger(__name__)

ORDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{8,40}$")
REF_PREFIX = "paypal_"


# Formats a money amount the way PayPal wants it: two decimals, as text.
def money_text(amount):
    return format(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


class PayPalPaymentGateway:
    """Creates, checks and captures PayPal orders."""

    SANDBOX_API = "https://api-m.sandbox.paypal.com"
    LIVE_API = "https://api-m.paypal.com"
    TIMEOUT_SECONDS = 20

    # PayPal's reasons for a refused capture, in words a customer can follow.
    DECLINE_REASONS = {
        "INSTRUMENT_DECLINED": "PayPal could not take the payment from that account or card",
        "PAYER_ACTION_REQUIRED": "PayPal needs you to approve the payment again",
        "TRANSACTION_REFUSED": "PayPal refused the payment",
        "ORDER_NOT_APPROVED": "The PayPal payment was not approved",
    }

    def __init__(self, client_id, client_secret, currency="USD", live=False, allow_live=False):
        if not client_id or not client_secret:
            raise RuntimeError("PayPal needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env")
        if live and not allow_live:
            raise RuntimeError("PAYPAL_ENV=live takes real money. Use sandbox, "
                               "or set PAYPAL_ALLOW_LIVE=1 if you really mean it.")
        self.client_id = client_id
        self.client_secret = client_secret
        self.currency = currency.upper()
        self.api = self.LIVE_API if live else self.SANDBOX_API
        self._access_token = None
        self._access_expires = 0

    # --- HTTP ----------------------------------------------------------

    # One HTTPS call; returns (http status, parsed JSON). Raises URLError / OSError if PayPal cannot be reached.
    def _send(self, method, path, body=None, headers=None, form=None, basic=None):
        data = None
        request_headers = dict(headers or {})
        if form is not None:
            data = "&".join(f"{k}={v}" for k, v in form.items()).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        if basic:
            credentials = base64.b64encode(f"{basic[0]}:{basic[1]}".encode()).decode()
            request_headers["Authorization"] = f"Basic {credentials}"
        req = urllib.request.Request(f"{self.api}{path}", data=data, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as response:
                text = response.read().decode()
                return response.status, (json.loads(text) if text else {})
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode())
            except ValueError:
                return exc.code, {}

    # Gets (and remembers until it expires) the access token PayPal wants on every call.
    def _token(self):
        if self._access_token and time.time() < self._access_expires - 30:
            return self._access_token
        status, payload = self._send("POST", "/v1/oauth2/token", form={"grant_type": "client_credentials"},
                                     basic=(self.client_id, self.client_secret))
        if status != 200 or "access_token" not in payload:
            log.error("PayPal sign-in failed: HTTP %s %s", status, payload.get("error_description"))
            raise PaymentGatewayError("PayPal refused our credentials; check PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET")
        self._access_token = payload["access_token"]
        self._access_expires = time.time() + int(payload.get("expires_in", 300))
        return self._access_token

    # An authorised call; raises PaymentGatewayError when PayPal cannot be reached or has a server problem.
    def _call(self, method, path, body=None, request_id=None):
        headers = {"Authorization": f"Bearer {self._token()}"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        try:
            status, payload = self._send(method, path, body=body, headers=headers)
        except (urllib.error.URLError, OSError) as exc:
            raise PaymentGatewayError(f"could not reach PayPal: {exc}") from exc
        if status >= 500:
            raise PaymentGatewayError(f"PayPal answered HTTP {status}")
        return status, payload

    # --- Creating an order ---------------------------------------------

    # Creates a PayPal order for this amount and returns its id (the page hands it to PayPal's buttons).
    def create_order(self, amount, reference=""):
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "custom_id": str(reference)[:127],
                "amount": {"currency_code": self.currency, "value": money_text(amount)},
            }],
        }
        status, payload = self._call("POST", "/v2/checkout/orders", body, request_id=f"ofs-create-{uuid.uuid4().hex}")
        if status not in (200, 201) or not payload.get("id"):
            log.error("PayPal create order failed: HTTP %s %s", status, payload.get("message"))
            raise PaymentGatewayError(f"PayPal would not create the order: HTTP {status}")
        return payload["id"]

    # --- Charging ------------------------------------------------------

    # Checks the approved PayPal order matches this checkout, then captures it.
    def charge(self, amount, token, idempotency_key=None):
        order_id = token.split(":", 1)[1] if isinstance(token, str) and token.startswith("paypal:") else ""
        if not ORDER_ID_PATTERN.match(order_id):
            return ChargeResult(False, None, None, "Invalid payment token")
        if Decimal(str(amount)) <= 0:
            return ChargeResult(False, None, None, "Amount must be above zero")

        status, order = self._call("GET", f"/v2/checkout/orders/{order_id}")
        if status == 404:
            return ChargeResult(False, None, None, "Invalid payment token")
        if status != 200:
            raise PaymentGatewayError(f"PayPal refused the order lookup: HTTP {status}")

        unit = (order.get("purchase_units") or [{}])[0]
        paid = unit.get("amount") or {}
        if paid.get("currency_code") != self.currency or paid.get("value") != money_text(amount):
            return ChargeResult(False, None, None, "The PayPal payment does not match this order's total. Please start again")

        if order.get("status") == "COMPLETED":
            capture = ((unit.get("payments") or {}).get("captures") or [{}])[0]
            if capture.get("id") and capture.get("status") == "COMPLETED":
                return ChargeResult(True, REF_PREFIX + capture["id"], None)
        if order.get("status") != "APPROVED":
            return ChargeResult(False, None, None, self.DECLINE_REASONS["ORDER_NOT_APPROVED"])

        status, captured = self._call("POST", f"/v2/checkout/orders/{order_id}/capture", {},
                                      request_id=f"ofs-capture-{idempotency_key or order_id}")
        return self._from_capture(status, captured)

    # Turns PayPal's capture answer into approved or declined.
    def _from_capture(self, status, payload):
        if status in (200, 201) and payload.get("status") == "COMPLETED":
            unit = (payload.get("purchase_units") or [{}])[0]
            capture = ((unit.get("payments") or {}).get("captures") or [{}])[0]
            if capture.get("id") and capture.get("status") == "COMPLETED":
                return ChargeResult(True, REF_PREFIX + capture["id"], None)
            return ChargeResult(False, None, None, "PayPal has not finished taking the payment")
        issues = [d.get("issue") for d in payload.get("details") or []]
        for issue in issues + [payload.get("name")]:
            if issue in self.DECLINE_REASONS:
                return ChargeResult(False, None, None, self.DECLINE_REASONS[issue])
        if status == 422:
            return ChargeResult(False, None, None, "PayPal could not take the payment")
        log.error("PayPal capture failed: HTTP %s %s", status, payload.get("message"))
        raise PaymentGatewayError(f"PayPal refused the capture: HTTP {status}")

    # Refunds a whole capture; True if PayPal accepted it or it was already refunded.
    def refund(self, gateway_ref):
        capture_id = str(gateway_ref or "").removeprefix(REF_PREFIX)
        if not ORDER_ID_PATTERN.match(capture_id):
            return False
        try:
            status, payload = self._call("POST", f"/v2/payments/captures/{capture_id}/refund", {},
                                         request_id=f"ofs-refund-{capture_id}")
        except PaymentGatewayError as exc:
            log.error("Refund of PayPal capture %s failed: %s", capture_id, exc)
            return False
        if status in (200, 201):
            return True
        if any(d.get("issue") == "CAPTURE_FULLY_REFUNDED" for d in payload.get("details") or []):
            return True
        log.error("Refund of PayPal capture %s refused: HTTP %s %s", capture_id, status, payload.get("message"))
        return False


# A stand-in for tests: it never calls PayPal and understands a few scripted order ids.
class FakePayPalGateway:

    currency = "USD"

    def __init__(self):
        self.created = []
        self.refunds = []

    # Hands back a predictable order id and remembers the amount asked for.
    def create_order(self, amount, reference=""):
        self.created.append(money_text(amount))
        return "FAKEORDER" + str(len(self.created)).zfill(4)

    # FAKEORDERxxxx is approved for the amount created, FAKEDECLINED is refused, anything else is invalid.
    def charge(self, amount, token, idempotency_key=None):
        order_id = token.split(":", 1)[1] if isinstance(token, str) and token.startswith("paypal:") else ""
        if order_id == "FAKEDECLINED":
            return ChargeResult(False, None, None, "PayPal could not take the payment from that account or card")
        if order_id.startswith("FAKEORDER"):
            if money_text(amount) not in self.created:
                return ChargeResult(False, None, None, "The PayPal payment does not match this order's total. Please start again")
            return ChargeResult(True, REF_PREFIX + "CAP" + order_id[-4:], None)
        return ChargeResult(False, None, None, "Invalid payment token")

    # Records the refund and says yes.
    def refund(self, gateway_ref):
        self.refunds.append(gateway_ref)
        return True
