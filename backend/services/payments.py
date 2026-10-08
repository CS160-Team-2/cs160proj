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

A real sandbox adapter would implement the same charge() and refund().
"""

import os
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal


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
    }
    KNOWN_CARDS = {"tok_visa": "4242", "tok_mastercard": "4444"}

    def __init__(self):
        self.refunds = []

    def charge(self, amount, token):
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


_gateway = None


def gateway():
    global _gateway
    if _gateway is None:
        name = os.environ.get("PAYMENT_GATEWAY", "fake")
        if name != "fake":
            raise RuntimeError(f"Unknown PAYMENT_GATEWAY '{name}'; only 'fake' is built so far")
        _gateway = FakePaymentGateway()
    return _gateway


def use_gateway(instance):
    """Swap the gateway, for tests."""
    global _gateway
    _gateway = instance
