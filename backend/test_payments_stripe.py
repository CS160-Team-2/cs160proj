"""The Stripe payment gateway (services/payments.py), with Stripe itself
replaced by canned answers. Nothing here touches the internet or needs
MySQL: each test scripts what "Stripe" replies and checks what OFS sent
and what it made of the reply.

The answers are shaped like Stripe's documented API responses.
"""

import urllib.error
import urllib.parse
from decimal import Decimal

import pytest

from services import payments
from services.payments import PaymentGatewayError, StripePaymentGateway


class ScriptedStripe(StripePaymentGateway):
    """A StripePaymentGateway whose HTTP call returns scripted replies."""

    RETRY_DELAYS = (0, 0)

    def __init__(self, *replies):
        super().__init__("sk_test_123")
        self.replies = list(replies)
        self.requests = []

    def _send(self, method, path, params, idempotency_key):
        self.requests.append({"method": method, "path": path,
                              "params": dict(params or []), "key": idempotency_key})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def intent(status="succeeded", last4="4242", intent_id="pi_123"):
    return 200, {"id": intent_id, "object": "payment_intent", "status": status,
                 "payment_method": {"id": "pm_1", "card": {"last4": last4}}}


def card_error(decline_code="generic_decline", code="card_declined", last4="0002"):
    return 402, {"error": {
        "type": "card_error", "code": code, "decline_code": decline_code,
        "message": "Your card was declined.",
        "payment_intent": {"id": "pi_declined", "status": "requires_payment_method"},
        "payment_method": {"id": "pm_2", "card": {"last4": last4}},
    }}


# ---------------------------------------------------------------------
# Charging
# ---------------------------------------------------------------------

def test_an_approved_charge_returns_the_payment_and_last_four():
    stripe = ScriptedStripe(intent(last4="4242"))
    result = stripe.charge(Decimal("23.48"), "tok_visa", idempotency_key="checkout-1")

    assert result.approved
    assert result.gateway_ref == "pi_123"
    assert result.card_last4 == "4242"

    sent = stripe.requests[0]
    assert sent["path"] == "/payment_intents"
    assert sent["params"]["amount"] == 2348
    assert sent["params"]["currency"] == "usd"
    assert sent["params"]["confirm"] == "true"
    assert sent["params"]["payment_method_data[card][token]"] == "tok_visa"
    assert sent["key"].startswith("ofs-charge-")


def test_a_payment_method_from_stripe_elements_is_sent_as_is():
    stripe = ScriptedStripe(intent())
    stripe.charge("5.00", "pm_card_visa", idempotency_key="checkout-1")

    params = stripe.requests[0]["params"]
    assert params["payment_method"] == "pm_card_visa"
    assert "payment_method_data[card][token]" not in params


def test_amounts_are_rounded_to_whole_cents():
    assert payments.to_cents(Decimal("10.005")) == 1001
    assert payments.to_cents("0.10") == 10
    assert payments.to_cents(Decimal("1234.50")) == 123450


@pytest.mark.parametrize("decline_code, reason", [
    ("generic_decline", "Card declined"),
    ("expired_card", "Card expired"),
    ("insufficient_funds", "Insufficient funds"),
    ("something_new", "Card declined"),
])
def test_declines_come_back_as_a_reason_not_an_error(decline_code, reason):
    stripe = ScriptedStripe(card_error(decline_code=decline_code))
    result = stripe.charge("10.00", "tok_chargeDeclined", idempotency_key="checkout-1")

    assert not result.approved
    assert result.decline_reason == reason
    assert result.gateway_ref == "pi_declined"
    assert result.card_last4 == "0002"


def test_an_unknown_token_is_an_invalid_token_decline():
    stripe = ScriptedStripe((400, {"error": {
        "type": "invalid_request_error", "code": "resource_missing",
        "param": "payment_method_data[card][token]", "message": "No such token: 'tok_nope'"}}))
    result = stripe.charge("10.00", "tok_nope", idempotency_key="checkout-1")

    assert not result.approved
    assert result.decline_reason == "Invalid payment token"


def test_tokens_that_are_not_stripe_tokens_are_never_sent():
    stripe = ScriptedStripe()
    assert stripe.charge("10.00", "4242424242424242").decline_reason == "Invalid payment token"
    assert stripe.charge("0.00", "tok_visa").decline_reason == "Amount must be above zero"
    assert stripe.requests == []


def test_a_card_that_needs_3d_secure_is_cancelled_and_declined():
    stripe = ScriptedStripe(intent(status="requires_action", intent_id="pi_3ds"),
                            (200, {"id": "pi_3ds", "status": "canceled"}))
    result = stripe.charge("10.00", "pm_card_authenticationRequired", idempotency_key="k-1")

    assert not result.approved
    assert "extra check from your bank" in result.decline_reason
    assert stripe.requests[1]["path"] == "/payment_intents/pi_3ds/cancel"


def test_a_bad_api_key_is_a_gateway_error_not_a_decline():
    stripe = ScriptedStripe((401, {"error": {"type": "invalid_request_error",
                                             "message": "Invalid API Key provided"}}))
    with pytest.raises(PaymentGatewayError):
        stripe.charge("10.00", "tok_visa", idempotency_key="checkout-1")


# ---------------------------------------------------------------------
# Retries and double-charge protection
# ---------------------------------------------------------------------

def test_a_dropped_connection_is_retried_with_the_same_key():
    stripe = ScriptedStripe(urllib.error.URLError("connection reset"),
                            (503, {}),
                            intent())
    result = stripe.charge("10.00", "tok_visa", idempotency_key="checkout-1")

    assert result.approved
    keys = {r["key"] for r in stripe.requests}
    assert len(stripe.requests) == 3 and len(keys) == 1


def test_giving_up_after_retries_is_a_gateway_error():
    stripe = ScriptedStripe(TimeoutError("timed out"), TimeoutError("timed out"),
                            TimeoutError("timed out"))
    with pytest.raises(PaymentGatewayError):
        stripe.charge("10.00", "tok_visa", idempotency_key="checkout-1")
    assert len(stripe.requests) == 3


def test_the_stripe_key_is_stable_per_attempt_and_differs_per_card():
    stripe = ScriptedStripe(intent(), intent(), intent(), intent())
    stripe.charge("10.00", "tok_visa", idempotency_key="checkout-1")
    stripe.charge("10.00", "tok_visa", idempotency_key="checkout-1")
    stripe.charge("10.00", "tok_mastercard", idempotency_key="checkout-1")
    stripe.charge("10.00", "tok_visa", idempotency_key="checkout-2")

    first, again, other_card, other_checkout = (r["key"] for r in stripe.requests)
    assert first == again
    assert len({first, other_card, other_checkout}) == 3


# ---------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------

def test_a_refund_is_sent_for_the_whole_payment():
    stripe = ScriptedStripe((200, {"id": "re_1", "status": "succeeded"}))
    assert stripe.refund("pi_123") is True

    sent = stripe.requests[0]
    assert sent["path"] == "/refunds"
    assert sent["params"] == {"payment_intent": "pi_123"}
    assert sent["key"].startswith("ofs-refund-")


def test_an_already_refunded_payment_counts_as_refunded():
    stripe = ScriptedStripe((400, {"error": {"code": "charge_already_refunded"}}))
    assert stripe.refund("pi_123") is True


def test_a_failed_refund_returns_false_instead_of_raising():
    stripe = ScriptedStripe(OSError("down"), OSError("down"), OSError("down"))
    assert stripe.refund("pi_123") is False


# ---------------------------------------------------------------------
# Choosing the gateway
# ---------------------------------------------------------------------

@pytest.fixture
def restore_gateway():
    before = payments._gateway
    payments._gateway = None
    yield
    payments._gateway = before


def test_payment_gateway_stripe_builds_a_stripe_gateway(monkeypatch, restore_gateway):
    monkeypatch.setenv("PAYMENT_GATEWAY", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    assert isinstance(payments.gateway(), StripePaymentGateway)


def test_stripe_without_a_key_refuses_to_start(monkeypatch, restore_gateway):
    monkeypatch.setenv("PAYMENT_GATEWAY", "stripe")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        payments.gateway()


def test_a_live_key_is_refused_unless_allowed():
    with pytest.raises(RuntimeError, match="live key"):
        StripePaymentGateway("sk_live_abc")
    assert StripePaymentGateway("sk_live_abc", allow_live=True)


def test_requests_are_form_encoded_with_the_key_as_bearer(monkeypatch):
    seen = {}

    class Reply:
        status = 200
        def read(self):
            return b'{"id": "re_1"}'
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout):
        seen["url"], seen["data"] = req.full_url, req.data
        seen["headers"] = dict(req.header_items())
        return Reply()
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    StripePaymentGateway("sk_test_abc").refund("pi_9")

    assert seen["url"] == "https://api.stripe.com/v1/refunds"
    assert urllib.parse.parse_qs(seen["data"].decode()) == {"payment_intent": ["pi_9"]}
    assert seen["headers"]["Authorization"] == "Bearer sk_test_abc"
    assert seen["headers"]["Idempotency-key"].startswith("ofs-refund-")
