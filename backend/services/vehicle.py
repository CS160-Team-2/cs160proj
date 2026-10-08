"""The link from OFS to the self-driving delivery vehicle.

OFS sends a dispatched trip to the vehicle: the trip id and its stops in
order. The vehicle reports back through the /api/fleet endpoints, using
its own token, as it completes each stop.

There is no real vehicle yet, so the only link is a simulated one
(VEHICLE_LINK=simulated, the default). It accepts every trip. If
VEHICLE_SIMULATION_SECONDS is set above zero, it also pretends to drive:
it completes one stop every that-many seconds, through the same code
path a real vehicle's callback would use. That makes the whole customer
tracking flow visible in a demo without anyone pressing buttons. Tests
leave it at zero and report stops themselves.
"""

import os
import threading


class SimulatedVehicleLink:
    def __init__(self, seconds_per_stop=0):
        self.seconds_per_stop = seconds_per_stop
        self.sent = []

    def send_trip(self, vehicle, trip_id, stops):
        """stops: [{"order_id", "order_number", "latitude", "longitude",
        "est_arrival"}, ...] in visiting order. Returns True if the
        vehicle accepted the trip."""
        self.sent.append({"vehicle_id": vehicle["vehicle_id"], "trip_id": trip_id, "stops": stops})
        if self.seconds_per_stop > 0:
            self._drive(trip_id, [s["order_id"] for s in stops])
        return True

    def _drive(self, trip_id, order_ids):
        # Imported here: delivery imports this module, so a top-level import
        # would be circular.
        from routes.delivery import complete_stop

        def step(remaining):
            if not remaining:
                return
            try:
                complete_stop(trip_id, remaining[0])
            except Exception:                         # noqa: BLE001
                return    # trip changed under us; a simulation just stops
            timer = threading.Timer(self.seconds_per_stop, step, [remaining[1:]])
            timer.daemon = True
            timer.start()

        timer = threading.Timer(self.seconds_per_stop, step, [order_ids])
        timer.daemon = True
        timer.start()


_link = None


def link():
    global _link
    if _link is None:
        name = os.environ.get("VEHICLE_LINK", "simulated")
        if name != "simulated":
            raise RuntimeError(f"Unknown VEHICLE_LINK '{name}'; only 'simulated' is built so far")
        _link = SimulatedVehicleLink(float(os.environ.get("VEHICLE_SIMULATION_SECONDS", "0")))
    return _link


def use_link(instance):
    """Swap the link, for tests."""
    global _link
    _link = instance
