import pytest

from tests.fakes import (
    FakeMappingService,
    FakePaymentGateway,
    FakeVehicleInterface,
)


def test_payment_gateway_approves_payment(fake_payment_gateway):
    result = fake_payment_gateway.charge("25.00", "test_token")

    assert result["approved"] is True
    assert result["transaction_id"] == "test_transaction_001"
    assert len(fake_payment_gateway.calls) == 1


def test_payment_gateway_declines_payment():
    gateway = FakePaymentGateway(outcome="declined")

    result = gateway.charge("25.00", "expired_card")

    assert result == {
        "approved": False,
        "reason": "card_declined",
    }


def test_payment_gateway_can_timeout():
    gateway = FakePaymentGateway(outcome="timeout")

    with pytest.raises(TimeoutError):
        gateway.charge("25.00", "test_token")


def test_mapping_service_returns_fixed_coordinates(fake_mapping_service):
    result = fake_mapping_service.geocode("1 Washington Sq, San Jose, CA")

    assert result["ok"] is True
    assert result["coordinates"]["latitude"] == 37.3352
    assert result["coordinates"]["longitude"] == -121.8811


def test_mapping_service_rejects_unfindable_address(fake_mapping_service):
    result = fake_mapping_service.geocode("UNFINDABLE ADDRESS")

    assert result == {
        "ok": False,
        "reason": "address_not_found",
    }


def test_mapping_service_returns_predictable_route(fake_mapping_service):
    locations = [
        {"latitude": 1, "longitude": 2},
        {"latitude": 3, "longitude": 4},
    ]

    result = fake_mapping_service.optimize_route(locations)

    assert result["ok"] is True
    assert result["ordered_stops"] == locations
    assert result["estimated_minutes"] == [10, 20]


def test_mapping_service_can_fail():
    mapping = FakeMappingService(route_failure=True)

    result = mapping.optimize_route([{"latitude": 1, "longitude": 2}])

    assert result == {
        "ok": False,
        "reason": "mapping_service_unavailable",
    }


def test_vehicle_accepts_dispatch(fake_vehicle_interface):
    result = fake_vehicle_interface.dispatch(
        trip_id=10,
        ordered_stops=["stop_1", "stop_2"],
    )

    assert result["accepted"] is True
    assert fake_vehicle_interface.dispatch_calls[0]["trip_id"] == 10


def test_vehicle_can_reject_dispatch():
    vehicle = FakeVehicleInterface(accepted=False)

    result = vehicle.dispatch(
        trip_id=10,
        ordered_stops=["stop_1"],
    )

    assert result == {
        "accepted": False,
        "reason": "vehicle_unavailable",
    }