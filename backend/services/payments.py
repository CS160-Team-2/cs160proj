"""Payment gateway.

OFS never sees a card number. The browser hands the card to the gateway
and gets back a token; OFS sends only that token and the amount, and
stores only what the gateway returns: approved or declined, a reference,
and the card's last four digits.

The fake gateway (the default, PAYMENT_GATEWAY=fake) understands these
test tokens, modelled on the ones card sandboxes publish:

    tok_visa             approved, card ending 4242
    tok_mastercard       approved, card ending 4444
    tok_<anything>_1234  approved, card ending 1234
    tok_declined         declined: "Card declined"
    tok_expired          declined: "Card expired"
    tok_insufficient     declined: "Insufficient funds"
    tok_gateway_down     the gateway cannot be reached (raises)

It also accepts Stripe's names for the three declining test cards
(listed below), so the same test cards work with either gateway.

The Stripe gateway (PAYMENT_GATEWAY=stripe, with STRIPE_SECRET_KEY) talks
to Stripe's API directly over HTTPS, so it needs no extra package. It
accepts either kind of token a browser can get from Stripe:

    pm_...   a PaymentMethod, which Stripe's card field (Stripe.js /
             Elements) creates in the browser
    tok_...  a card token. Stripe's published test tokens work with a
             test key: tok_visa, tok_mastercard, tok_chargeDeclined,
             tok_chargeDeclinedExpiredCard,
             tok_chargeDeclinedInsufficientFunds

It refuses a live key (sk_live_...) unless STRIPE_ALLOW_LIVE=1, so a
class demo can never take real money by accident.
"""

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


class PaymentGatewayError(Exception):
    """The gateway could not be reached or gave an unusable answer. The
    customer was not charged."""


@dataclass
class ChargeResult:
    approved: bool
    gateway_ref: str | None
    card_last4: str | None
    decline_reason: str | None = None


class FakePaymentGateway:
    DECLINES = {
        "tok_declined": "Card declined",
        "tok_expired": "Card expired",
        "tok_insufficient": "Insufficient funds",
        # Stripe's names for the same test cards, so one list of test
        # cards works with either gateway.
        "tok_chargeDeclined": "Card declined",
        "tok_chargeDeclinedExpiredCard": "Card expired",
        "tok_chargeDeclinedInsufficientFunds": "Insufficient funds",
    }
    KNOWN_CARDS = {"tok_visa": "4242", "tok_mastercard": "4444"}

    def __init__(self):
        self.refunds = []

    def charge(self, amount, token, idempotency_key=None):
        amount = Decimal(amount)
        if not isinstance(token, str) or not token.startswith("tok_"):
            return ChargeResult(False, None, None, "Invalid payment token")
        if token == "tok_gateway_down":
            raise PaymentGatewayError("Payment gateway is not responding")
        if token in self.DECLINES:
            return ChargeResult(False, f"fake_{uuid.uuid4().hex[:12]}", "0002",
                                self.DECLINES[token])
        if amount <= 0:
            return ChargeResult(False, None, None, "Amount must be above zero")

        last4 = self.KNOWN_CARDS.get(token)
        if last4 is None:
            match = re.search(r"(\d{4})$", token)
            last4 = match.group(1) if match else "4242"
        return ChargeResult(True, f"fake_{uuid.uuid4().hex[:12]}", last4)

    def refund(self, gateway_ref):
        self.refunds.append(gateway_ref)
        return True


# =====================================================================
# Stripe
# =====================================================================

log = logging.getLogger(__name__)


def to_cents(amount):
    """Dollars (Decimal or string) to whole cents, which is what Stripe takes."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class StripePaymentGateway:
    """Charges cards through a Stripe PaymentIntent, confirmed at once.

    Every request carries a Stripe idempotency key, so a request can be
    retried after a dropped connection without charging the card twice.
    The key is built from OFS's own checkout key plus the card and the
    amount: a retry of the same attempt reuses it, while a second try
    with a different card gets a fresh one.
    """

    API = "https://api.stripe.com/v1"
    TIMEOUT_SECONDS = 20
    RETRY_DELAYS = (0.5, 1.5)      # two retries after the first try
    RETRYABLE_STATUSES = {409, 429, 500, 502, 503, 504}

    # Stripe decline codes, in the same words the fake gateway uses.
    DECLINE_REASONS = {
        "expired_card": "Card expired",
        "insufficient_funds": "Insufficient funds",
        "incorrect_cvc": "Incorrect security code",
        "invalid_cvc": "Incorrect security code",
        "incorrect_number": "Incorrect card number",
        "invalid_expiry_month": "Card expiry date is not valid",
        "invalid_expiry_year": "Card expiry date is not valid",
        "lost_card": "Card declined",
        "stolen_card": "Card declined",
        "card_velocity_exceeded": "Card declined: too many recent attempts",
        "processing_error": "The card could not be processed",
    }

    def __init__(self, secret_key, currency="usd", allow_live=False):
        if not secret_key:
            raise RuntimeError("PAYMENT_GATEWAY=stripe needs STRIPE_SECRET_KEY in backend/.env")
        if "_live_" in secret_key and not allow_live:
            raise RuntimeError("STRIPE_SECRET_KEY is a live key, which takes real money. "
                               "Use a test key (sk_test_...), or set STRIPE_ALLOW_LIVE=1 "
                               "if you really mean it.")
        self.secret_key = secret_key
        self.currency = currency.lower()

    # --- HTTP ----------------------------------------------------------

    def _send(self, method, path, params, idempotency_key):
        """One HTTPS call. Returns (http_status, parsed JSON body).
        Raises urllib.error.URLError / OSError if Stripe cannot be reached."""
        data = urllib.parse.urlencode(params).encode() if params else None
        req = urllib.request.Request(f"{self.API}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.secret_key}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if idempotency_key:
            req.add_header("Idempotency-Key", idempotency_key)
        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode())
            except ValueError:
                return exc.code, {}

    def _call(self, method, path, params, idempotency_key):
        """_send, retried with the same idempotency key when the failure
        might be temporary. Raises PaymentGatewayError when retries run out."""
        problem = None
        for delay in (0, *self.RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                status, payload = self._send(method, path, params, idempotency_key)
            except (urllib.error.URLError, OSError) as exc:
                problem = f"could not reach Stripe: {exc}"
                continue
            if status in self.RETRYABLE_STATUSES:
                problem = f"Stripe answered HTTP {status}"
                continue
            return status, payload
        raise PaymentGatewayError(problem)

    # --- Charging ------------------------------------------------------

    def _stripe_key(self, prefix, *parts):
        digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
        return f"ofs-{prefix}-{digest[:40]}"

    def charge(self, amount, token, idempotency_key=None):
        cents = to_cents(amount)
        if not isinstance(token, str) or not token.startswith(("pm_", "tok_")):
            return ChargeResult(False, None, None, "Invalid payment token")
        if cents <= 0:
            return ChargeResult(False, None, None, "Amount must be above zero")

        params = [
            ("amount", cents),
            ("currency", self.currency),
            ("confirm", "true"),
            # Stripe picks payment methods from the dashboard settings now.
            # No redirects, since OFS confirms on the server with no return page.
            ("automatic_payment_methods[enabled]", "true"),
            ("automatic_payment_methods[allow_redirects]", "never"),
            ("expand[]", "payment_method"),
            ("metadata[ofs_checkout_key]", idempotency_key or ""),
        ]
        if token.startswith("pm_"):
            params.append(("payment_method", token))
        else:
            params += [("payment_method_data[type]", "card"),
                       ("payment_method_data[card][token]", token)]

        stripe_key = self._stripe_key("charge", idempotency_key or uuid.uuid4().hex, token, cents)
        status, payload = self._call("POST", "/payment_intents", params, stripe_key)

        if status == 200:
            return self._from_intent(payload)
        return self._from_error(status, payload.get("error") or {})

    def _from_intent(self, intent):
        ref = intent.get("id")
        last4 = _card_last4(intent.get("payment_method"))
        if intent.get("status") == "succeeded":
            return ChargeResult(True, ref, last4)
        if intent.get("status") in ("requires_action", "requires_payment_method",
                                    "requires_confirmation"):
            # Usually a bank asking for 3-D Secure, which needs the browser to
            # show the bank's own check. OFS cannot do that yet, so give up on
            # this attempt; nothing was charged.
            self._cancel(ref)
            return ChargeResult(False, ref, last4,
                                "This card needs an extra check from your bank, which we "
                                "cannot do yet. Please use another card")
        # "processing": the money may still move. Should not happen for cards.
        raise PaymentGatewayError(f"Stripe left payment {ref} in status {intent.get('status')}")

    def _from_error(self, status, error):
        intent = error.get("payment_intent") or {}
        ref = intent.get("id")
        last4 = _card_last4(error.get("payment_method") or intent.get("last_payment_error",
                                                                       {}).get("payment_method"))
        if error.get("type") == "card_error":
            code = error.get("decline_code") or error.get("code")
            return ChargeResult(False, ref, last4, self.DECLINE_REASONS.get(code, "Card declined"))
        if status == 400 and (error.get("code") in ("resource_missing", "token_already_used")
                              or str(error.get("param", "")).startswith("payment_method")):
            return ChargeResult(False, ref, None, "Invalid payment token")
        # A bad key, a malformed request, or anything else that is our fault
        # rather than the card's. The card was not charged.
        log.error("Stripe charge failed: HTTP %s %s", status, error.get("message"))
        raise PaymentGatewayError(f"Stripe refused the request: HTTP {status} "
                                  f"{error.get('message', '')}".strip())

    def _cancel(self, intent_id):
        if not intent_id:
            return
        try:
            self._call("POST", f"/payment_intents/{intent_id}/cancel", None,
                       self._stripe_key("cancel", intent_id))
        except PaymentGatewayError:
            log.warning("Could not cancel unfinished Stripe payment %s", intent_id)

    def refund(self, gateway_ref):
        """Refund a whole charge. True if Stripe accepted the refund (or it
        was already refunded); False if it did not, so staff can do it by hand."""
        try:
            status, payload = self._call("POST", "/refunds", [("payment_intent", gateway_ref)],
                                         self._stripe_key("refund", gateway_ref))
        except PaymentGatewayError as exc:
            log.error("Refund of Stripe payment %s failed: %s", gateway_ref, exc)
            return False
        if status == 200:
            return True
        error = payload.get("error") or {}
        if error.get("code") == "charge_already_refunded":
            return True
        log.error("Refund of Stripe payment %s refused: HTTP %s %s",
                  gateway_ref, status, error.get("message"))
        return False


def _card_last4(payment_method):
    if isinstance(payment_method, dict):
        return (payment_method.get("card") or {}).get("last4")
    return None


# =====================================================================
# Choosing the gateway
# =====================================================================

_gateway = None


def gateway():
    global _gateway
    if _gateway is None:
        name = os.environ.get("PAYMENT_GATEWAY", "fake")
        if name == "fake":
            _gateway = FakePaymentGateway()
        elif name == "stripe":
            _gateway = StripePaymentGateway(
                os.environ.get("STRIPE_SECRET_KEY", ""),
                currency=os.environ.get("STRIPE_CURRENCY", "usd"),
                allow_live=os.environ.get("STRIPE_ALLOW_LIVE") == "1",
            )
        else:
            raise RuntimeError(f"Unknown PAYMENT_GATEWAY '{name}'; use 'fake' or 'stripe'")
    return _gateway


def use_gateway(instance):
    """Swap the gateway, for tests."""
    global _gateway
    _gateway = instance
