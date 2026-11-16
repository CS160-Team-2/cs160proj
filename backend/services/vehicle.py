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
        # The recovery worker discovers committed trips. Starting timers here
        # would race the dispatch transaction and lose their state on restart.
        return True

    def tick(self, trip_id):
        """Advance one persisted leg using the database's clock and row lock.

        A restart never resets the leg clock. Multiple Flask processes may
        poll, but the trip lock and idempotent completion serialize them.
        Downtime counts toward the current leg; subsequent legs start when
        their preceding stop is recorded delivered.
        """
        if self.seconds_per_stop <= 0:
            return
        import db
        from routes.delivery import _stops, _trip, complete_stop
        with db.transaction() as cur:
            trip = _trip(trip_id, cur, lock=True)
            if trip['status'] != 'out_for_delivery':
                return
            stops = _stops(trip_id, cur)
            index = next((i for i, stop in enumerate(stops) if stop['delivered_at'] is None), None)
            if index is None or not trip['started_at']:
                return
            route = trip['route_json'] or {}
            if isinstance(route, str):
                route = json.loads(route)
            if not trip['route_planned_at'] or not route.get('path'):
                return
            cur.execute('SELECT NOW(6) AS clock')
            now = cur.fetchone()['clock']
            previous = [s['delivered_at'] for s in stops[:index] if s['delivered_at']]
            leg_started = max(previous) if previous else trip['started_at']
            fraction = min(1, max(0, (now - leg_started).total_seconds() / self.seconds_per_stop))
            segments = route_segments(route['path'], stops)
            latitude, longitude = position_on_path(segments[index], fraction)
            report = 'en_route'
            if fraction >= 1:
                status = complete_stop(trip_id, stops[index]['order_id'], source='simulation', cursor=cur)
                report = 'completed' if status == 'completed' else 'at_stop'
            cur.execute('UPDATE delivery_trips SET last_latitude=%s, last_longitude=%s, '
                        'last_report=%s, last_report_at=NOW() WHERE trip_id=%s',
                        (round(latitude, 6), round(longitude, 6), report, trip_id))

    def resume_pending(self):
        import db
        rows = db.query_all("SELECT trip_id FROM delivery_trips WHERE status='out_for_delivery'")
        for row in rows:
            try:
                self.tick(row['trip_id'])
            except Exception:
                logging.getLogger(__name__).exception('Simulation tick failed for trip %s', row['trip_id'])


_recovery_thread = None
_recovery_lock = threading.Lock()


def start_recovery():
    """Start once per process; retry discovery if MySQL is temporarily down."""
    global _recovery_thread
    if os.environ.get('VEHICLE_LINK', 'simulated') != 'simulated':
        return
    try:
        seconds = float(os.environ.get('VEHICLE_SIMULATION_SECONDS', '0'))
    except ValueError:
        logging.getLogger(__name__).warning('Invalid VEHICLE_SIMULATION_SECONDS; automatic simulation disabled')
        return
    if not math.isfinite(seconds) or seconds <= 0:
        return
    with _recovery_lock:
        if _recovery_thread is not None and _recovery_thread.is_alive():
            return _recovery_thread
        def run():
            worker = SimulatedVehicleLink(seconds)
            while True:
                try:
                    worker.resume_pending()
                except Exception:
                    logging.getLogger(__name__).exception('Simulation discovery will retry')
                threading.Event().wait(max(.05, min(1, seconds / 5)))
        _recovery_thread = threading.Thread(target=run, name='ofs-simulation-recovery', daemon=True)
        _recovery_thread.start()
        return _recovery_thread


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
