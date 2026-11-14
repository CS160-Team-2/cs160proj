"""The checkout page asks which payment gateway is on (customer backlog C5)."""

import pytest

from conftest import requires_mysql

pytestmark = [requires_mysql, pytest.mark.usefixtures("fresh_db")]


# The fake gateway is the default, with US dollars.
def test_the_fake_gateway_is_reported_by_default(client, monkeypatch):
    for name in ("PAYMENT_GATEWAY", "STRIPE_CURRENCY", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_CURRENCY"):
        monkeypatch.delenv(name, raising=False)

    body = client.get("/api/payments/config").get_json()

    assert body == {"ok": True, "gateway": "fake", "currency": "usd",
                    "paypal": {"enabled": False, "client_id": "", "currency": "USD"}}


# Switching to Stripe is reported, and the currency follows the setting.
def test_stripe_and_its_currency_are_reported_when_switched_on(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_GATEWAY", "stripe")
    monkeypatch.setenv("STRIPE_CURRENCY", "EUR")

    body = client.get("/api/payments/config").get_json()

    assert body["gateway"] == "stripe" and body["currency"] == "eur"


# Signed-out visitors can read it, and it holds no secrets.
def test_the_config_is_public_and_holds_no_keys(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_should_never_appear")

    response = client.get("/api/payments/config")

    assert response.status_code == 200
    assert "sk_test" not in response.get_data(as_text=True)
