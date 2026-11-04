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
import json
import logging
import math


def position_on_path(path, fraction):
    """Interpolate by distance, not vertex count, along [latitude, longitude]."""
    if len(path) == 1:
        return path[0]
    distances = [math.hypot(b[0] - a[0], (b[1] - a[1]) *
                            math.cos(math.radians((a[0] + b[0]) / 2)))
                 for a, b in zip(path, path[1:])]
    remaining = sum(distances) * min(1, max(0, fraction))
    for a, b, distance in zip(path, path[1:], distances):
        if distance and remaining <= distance:
            ratio = remaining / distance
            return [a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio]
        remaining -= distance
    return path[-1]


def route_segments(path, stops):
    """Cut the saved road geometry at the nearest vertex to each stop."""
    path = [[float(lat), float(lng)] for lat, lng in path]
    segments = []
    start = 0
    for stop in stops:
        target = [float(stop["latitude"]), float(stop["longitude"])]
        if not path:
            segments.append([target])
            continue
        end = min(range(start, len(path)),
                  key=lambda index: (path[index][0] - target[0]) ** 2 +
                  (path[index][1] - target[1]) ** 2)
        segments.append(path[start:end + 1])
        start = end
    return segments


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
            self._drive(trip_id, stops)
        return True

    def _drive(self, trip_id, stops):
        # Imported here: delivery imports this module, so a top-level import
        # would be circular.
        from routes.delivery import complete_stop
        import db

        interval = min(2, self.seconds_per_stop / 5)
        frames = max(1, math.ceil(self.seconds_per_stop / interval))
        state = {"segments": None, "stop": 0, "frame": 0}

        def step():
            try:
                trip = db.query_one("SELECT status, route_json FROM delivery_trips WHERE trip_id = %s",
                                    (trip_id,))
                if not trip or trip["status"] != "out_for_delivery" or state["stop"] >= len(stops):
                    return
                if state["segments"] is None:
                    route = trip["route_json"] or {}
                    if isinstance(route, str):
                        route = json.loads(route)
                    state["segments"] = route_segments(route.get("path", []), stops)
                state["frame"] += 1
                latitude, longitude = position_on_path(
                    state["segments"][state["stop"]], state["frame"] / frames)
                arrived = state["frame"] >= frames
                with db.transaction() as cur:
                    cur.execute(
                        "UPDATE delivery_trips SET last_latitude = %s, last_longitude = %s, "
                        "last_report = %s, last_report_at = NOW() "
                        "WHERE trip_id = %s AND status = 'out_for_delivery'",
                        (round(latitude, 6), round(longitude, 6),
                         "at_stop" if arrived else "en_route", trip_id),
                    )
                if arrived:
                    status = complete_stop(trip_id, stops[state["stop"]]["order_id"])
                    if status == "completed":
                        with db.transaction() as cur:
                            cur.execute("UPDATE delivery_trips SET last_report = 'completed', "
                                        "last_report_at = NOW() WHERE trip_id = %s", (trip_id,))
                        return
                    state["stop"] += 1
                    state["frame"] = 0
            except Exception:                         # noqa: BLE001
                logging.getLogger(__name__).exception("Vehicle simulation stopped for trip %s", trip_id)
                return
            timer = threading.Timer(interval, step)
            timer.daemon = True
            timer.start()

        timer = threading.Timer(interval, step)
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
