"""PayPal payments (customer backlog C5b): the PayPal gateway with PayPal itself replaced by scripted
answers, the config the checkout page reads, creating a PayPal order, and placing an order paid with PayPal."""

from decimal import Decimal

import pytest

from conftest import APPLES_ID, CUSTOMER, CUSTOMER_ADDRESS_ID, error_code, requires_mysql, signed_in
from services import payments
from services.paypal import FakePayPalGateway, PayPalPaymentGateway


# A PayPalPaymentGateway whose HTTP calls return scripted replies instead of reaching PayPal.
class ScriptedPayPal(PayPalPaymentGateway):

    def __init__(self, *replies):
        super().__init__("client-id", "client-secret")
        self.replies = list(replies)
        self.requests = []
        self._access_token = "token"
        self._access_expires = 10 ** 12

    def _send(self, method, path, body=None, headers=None, form=None, basic=None):
        self.requests.append({"method": method, "path": path, "body": body, "headers": headers or {}})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


# PayPal's answer to "what is this order": approved, for this amount.
def order_reply(value="23.48", status="APPROVED", currency="USD", captures=None):
    unit = {"amount": {"currency_code": currency, "value": value}}
    if captures:
        unit["payments"] = {"captures": captures}
    return 200, {"id": "ORDER12345", "status": status, "purchase_units": [unit]}


# PayPal's answer to a successful capture.
def capture_reply(capture_id="CAP98765"):
    return 201, {"status": "COMPLETED", "purchase_units": [{"payments": {"captures": [
        {"id": capture_id, "status": "COMPLETED"}]}}]}


# --- The gateway ----------------------------------------------------------

# An approved order for the right amount is captured and the capture id is kept as the reference.
def test_an_approved_order_for_the_right_amount_is_captured():
    paypal = ScriptedPayPal(order_reply("23.48"), capture_reply())

    result = paypal.charge(Decimal("23.48"), "paypal:ORDER12345", idempotency_key="checkout-1")

    assert result.approved and result.gateway_ref == "paypal_CAP98765" and result.card_last4 is None
    assert paypal.requests[1]["path"] == "/v2/checkout/orders/ORDER12345/capture"
    assert paypal.requests[1]["headers"]["PayPal-Request-Id"] == "ofs-capture-checkout-1"


# A PayPal order for a different amount is refused and nothing is captured.
def test_an_order_for_a_different_amount_is_refused_without_capturing():
    paypal = ScriptedPayPal(order_reply("0.01"))

    result = paypal.charge(Decimal("23.48"), "paypal:ORDER12345")

    assert not result.approved and "does not match" in result.decline_reason
    assert len(paypal.requests) == 1


# A different currency is refused too.
def test_an_order_in_another_currency_is_refused():
    paypal = ScriptedPayPal(order_reply("23.48", currency="EUR"))

    assert not paypal.charge(Decimal("23.48"), "paypal:ORDER12345").approved


# An order the customer never approved is refused without capturing.
def test_an_order_that_was_not_approved_is_refused():
    paypal = ScriptedPayPal(order_reply("23.48", status="CREATED"))

    result = paypal.charge(Decimal("23.48"), "paypal:ORDER12345")

    assert not result.approved and len(paypal.requests) == 1


# Retrying after a capture that already worked returns the same capture instead of charging twice.
def test_an_already_captured_order_returns_its_capture():
    done = [{"id": "CAP98765", "status": "COMPLETED"}]
    paypal = ScriptedPayPal(order_reply("23.48", status="COMPLETED", captures=done))

    result = paypal.charge(Decimal("23.48"), "paypal:ORDER12345")

    assert result.approved and result.gateway_ref == "paypal_CAP98765" and len(paypal.requests) == 1


# PayPal turning down the account or card is a decline with a readable reason.
def test_a_refused_capture_is_a_decline():
    refusal = (422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSTRUMENT_DECLINED"}]})
    paypal = ScriptedPayPal(order_reply("23.48"), refusal)

    result = paypal.charge(Decimal("23.48"), "paypal:ORDER12345")

    assert not result.approved and "could not take the payment" in result.decline_reason


# Tokens that are not PayPal order ids are invalid, including ones trying to change the request path.
@pytest.mark.parametrize("token", ["tok_visa", "paypal:", "paypal:../../x", "paypal:AB", None])
def test_other_tokens_are_invalid(token):
    paypal = ScriptedPayPal()

    result = paypal.charge(Decimal("5.00"), token)

    assert not result.approved and result.decline_reason == "Invalid payment token"
    assert paypal.requests == []


# An unknown order id is invalid, not a server error.
def test_an_unknown_order_id_is_invalid():
    paypal = ScriptedPayPal((404, {"name": "RESOURCE_NOT_FOUND"}))

    assert paypal.charge(Decimal("5.00"), "paypal:ORDER12345").decline_reason == "Invalid payment token"


# A PayPal outage is a gateway error (the customer is not charged), not a decline.
def test_a_paypal_server_error_is_a_gateway_error():
    paypal = ScriptedPayPal((503, {}))

    with pytest.raises(payments.PaymentGatewayError):
        paypal.charge(Decimal("5.00"), "paypal:ORDER12345")


# Creating an order sends the amount as two-decimal text and returns PayPal's id.
def test_creating_an_order_sends_the_amount_and_returns_the_id():
    paypal = ScriptedPayPal((201, {"id": "NEWORDER99", "status": "CREATED"}))

    assert paypal.create_order(Decimal("7.1")) == "NEWORDER99"
    sent = paypal.requests[0]["body"]["purchase_units"][0]["amount"]
    assert sent == {"currency_code": "USD", "value": "7.10"}


# Refunds go to the capture, and "already refunded" counts as done.
def test_refunds_target_the_capture_and_tolerate_a_repeat():
    paypal = ScriptedPayPal((201, {"id": "REF1"}), (422, {"details": [{"issue": "CAPTURE_FULLY_REFUNDED"}]}), (400, {}))

    assert paypal.refund("paypal_CAP98765")
    assert paypal.requests[0]["path"] == "/v2/payments/captures/CAP98765/refund"
    assert paypal.refund("paypal_CAP98765")
    assert not paypal.refund("paypal_CAP98765")


# A live PayPal account is refused unless it is allowed on purpose.
def test_live_mode_needs_an_explicit_switch():
    with pytest.raises(RuntimeError):
        PayPalPaymentGateway("id", "secret", live=True)
    assert PayPalPaymentGateway("id", "secret", live=True, allow_live=True).api.endswith("paypal.com")


# --- Config and routes --------------------------------------------------------

# PayPal is reported on, with its public client id and no secret, only when both keys are set.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_the_config_shows_paypal_only_when_it_is_set_up(client, monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "public-client-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "very-secret")

    response = client.get("/api/payments/config")

    assert response.get_json()["paypal"] == {"enabled": True, "client_id": "public-client-id", "currency": "USD"}
    assert "very-secret" not in response.get_data(as_text=True)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET")
    assert client.get("/api/payments/config").get_json()["paypal"]["enabled"] is False


@pytest.fixture
def fake_paypal():
    gateway = FakePayPalGateway()
    payments.use_paypal_gateway(gateway)
    yield gateway
    payments.use_paypal_gateway(None)


# A guest's cart total, worked out by the server, becomes the PayPal order.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_a_paypal_order_is_created_for_the_servers_cart_total(client, fake_paypal):
    client.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 2})
    expected = client.get("/api/checkout/estimate").get_json()["grand_total"]

    response = client.post("/api/payments/paypal/order")

    assert response.status_code == 201
    assert response.get_json()["id"].startswith("FAKEORDER")
    assert fake_paypal.created == [expected]


# An empty cart cannot start a PayPal payment, and neither can a visitor when PayPal is not set up.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_no_paypal_order_without_a_cart_or_without_paypal(client, fake_paypal, monkeypatch):
    assert error_code(client.post("/api/payments/paypal/order")) == "CART_EMPTY"
    payments.use_paypal_gateway(None)
    for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    assert error_code(client.post("/api/payments/paypal/order")) == "PAYPAL_UNAVAILABLE"


# A signed-in customer pays with PayPal: the order is placed, stock drops, and the order says it was PayPal.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_an_order_can_be_paid_with_paypal(app, fake_paypal):
    customer = signed_in(app, *CUSTOMER)
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    order_id = customer.post("/api/payments/paypal/order").get_json()["id"]

    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": f"paypal:{order_id}", "idempotency_key": "paypal-key-0001"})

    assert response.status_code == 201
    payment = response.get_json()["order"]["payment"]
    assert payment["method"] == "paypal" and payment["card_last4"] is None
    assert customer.get("/api/cart").get_json()["cart"]["item_count"] == 0


# A PayPal payment for the wrong amount is declined and the cart stays as it was.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_a_paypal_payment_for_another_amount_is_declined(app, fake_paypal):
    customer = signed_in(app, *CUSTOMER)
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})
    fake_paypal.created.append("0.01")

    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "paypal:FAKEORDER9999", "idempotency_key": "paypal-key-0002"})

    assert response.status_code == 402
    assert customer.get("/api/cart").get_json()["cart"]["item_count"] == 1


# A PayPal token is refused when PayPal is not set up, never sent to the card gateway.
@pytest.mark.usefixtures("fresh_db")
@requires_mysql
def test_a_paypal_token_is_refused_when_paypal_is_off(app, monkeypatch):
    for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    payments.use_paypal_gateway(None)
    customer = signed_in(app, *CUSTOMER)
    customer.post("/api/cart/items", json={"product_id": APPLES_ID, "quantity": 1})

    response = customer.post("/api/orders", json={
        "address_id": CUSTOMER_ADDRESS_ID, "payment_token": "paypal:SOMEORDER1", "idempotency_key": "paypal-key-0003"})

    assert error_code(response) == "PAYMENT_METHOD_UNAVAILABLE"
