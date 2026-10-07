from decimal import Decimal


class FakePaymentGateway:
    """Predictable replacement for the real payment provider."""

    def __init__(self, outcome="approved"):
        self.outcome = outcome
        self.calls = []

    def charge(self, amount, payment_token):
        amount = Decimal(str(amount))

        self.calls.append(
            {
                "amount": amount,
                "payment_token": payment_token,
            }
        )

        if self.outcome == "timeout":
            raise TimeoutError("Payment gateway timed out")

        if self.outcome == "declined":
            return {
                "approved": False,
                "reason": "card_declined",
            }

        return {
            "approved": True,
            "transaction_id": "test_transaction_001",
            "last_four": "4242",
        }


class FakeMappingService:
    """Predictable replacement for Google Maps or Mapbox."""

    def __init__(self, route_failure=False):
        self.route_failure = route_failure
        self.geocode_calls = []
        self.route_calls = []

    def geocode(self, address):
        self.geocode_calls.append(address)

        if address == "UNFINDABLE ADDRESS":
            return {
                "ok": False,
                "reason": "address_not_found",
            }

        return {
            "ok": True,
            "coordinates": {
                "latitude": 37.3352,
                "longitude": -121.8811,
            },
        }

    def optimize_route(self, locations, use_current_traffic=True):
        self.route_calls.append(
            {
                "locations": locations,
                "use_current_traffic": use_current_traffic,
            }
        )

        if self.route_failure:
            return {
                "ok": False,
                "reason": "mapping_service_unavailable",
            }

        return {
            "ok": True,
            "ordered_stops": list(locations),
            "estimated_minutes": [
                10 * (index + 1) for index in range(len(locations))
            ],
        }


class FakeVehicleInterface:
    """Predictable replacement for the self-driving delivery robot."""

    def __init__(self, accepted=True):
        self.accepted = accepted
        self.dispatch_calls = []

    def dispatch(self, trip_id, ordered_stops):
        self.dispatch_calls.append(
            {
                "trip_id": trip_id,
                "ordered_stops": ordered_stops,
            }
        )

        if not self.accepted:
            return {
                "accepted": False,
                "reason": "vehicle_unavailable",
            }

        return {
            "accepted": True,
            "vehicle_reference": "test_vehicle_001",
        }