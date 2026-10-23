"""Mapping service: turn addresses into coordinates, and plan routes.

One interface, three providers, chosen by MAP_PROVIDER in .env:

    fake     (default) works offline, same answer every time
    google   Google Geocoding + Routes APIs       (needs GOOGLE_MAPS_API_KEY)
    mapbox   Mapbox Geocoding + Optimization APIs (needs MAPBOX_ACCESS_TOKEN)

Every provider offers the same two calls:

    geocode(street, city, state, zip_code) -> GeoPoint, or None if not found
    route(origin, stops)                   -> Route

`stops` is a list of (key, GeoPoint). The route visits every stop once,
starting and ending at the store, in whatever order is fastest given
current traffic, and says when it reaches each stop.

Provider contracts are tested with mocked HTTP responses, so automated tests
never use quota or require secrets. A live-key smoke test is still required
before a team demo that selects Google or Mapbox (backlog T-14).
"""

import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal


class MappingError(Exception):
    """The provider could not be reached or could not plan the route."""


@dataclass
class GeoPoint:
    latitude: Decimal
    longitude: Decimal


@dataclass
class Route:
    stop_order: list            # stop keys, in visiting order
    arrival_seconds: dict       # stop key -> seconds after leaving the store
    path: list = field(default_factory=list)   # [[lat, lng], ...] to draw on a map
    total_seconds: int = 0
    provider: str = ""


def store_location():
    return GeoPoint(
        Decimal(os.environ.get("STORE_LATITUDE", "37.335200")),
        Decimal(os.environ.get("STORE_LONGITUDE", "-121.881100")),
    )


def _q6(value):
    return Decimal(str(value)).quantize(Decimal("0.000001"))


# =====================================================================
# Fake provider
# =====================================================================

class FakeMapProvider:
    """Deterministic stand-in for a real mapping service.

    An address is "not found" when its ZIP code is not five digits, its
    street has no house number, or it contains the word "nowhere". Any
    other address gets a fixed point within a few miles of the store,
    derived from the address text, so the same address always lands in
    the same place.

    Routes use nearest-next-stop ordering at 25 mph average city speed,
    plus three minutes at each stop.
    """

    SPEED_MPH = 25
    MINUTES_PER_STOP = 3

    def __init__(self):
        self.calls = []

    def geocode(self, street, city, state, zip_code):
        self.calls.append(("geocode", street, zip_code))
        text = f"{street} {city} {state} {zip_code}"
        if (not re.fullmatch(r"\d{5}(-\d{4})?", zip_code.strip())
                or not re.search(r"\d", street)
                or "nowhere" in text.lower()):
            return None

        digest = hashlib.sha256(text.lower().encode()).digest()
        store = store_location()
        # Up to about 0.05 degrees (3 to 4 miles) from the store.
        lat_offset = (digest[0] / 255 - 0.5) * 0.1
        lng_offset = (digest[1] / 255 - 0.5) * 0.1
        return GeoPoint(_q6(float(store.latitude) + lat_offset),
                        _q6(float(store.longitude) + lng_offset))

    def route(self, origin, stops):
        self.calls.append(("route", [key for key, _ in stops]))
        remaining = list(stops)
        here = origin
        elapsed = 0.0
        order, arrivals, path = [], {}, [[float(origin.latitude), float(origin.longitude)]]

        while remaining:
            remaining.sort(key=lambda stop: _miles(here, stop[1]))
            key, point = remaining.pop(0)
            elapsed += _miles(here, point) / self.SPEED_MPH * 3600
            arrivals[key] = int(elapsed)
            elapsed += self.MINUTES_PER_STOP * 60
            order.append(key)
            path.append([float(point.latitude), float(point.longitude)])
            here = point

        elapsed += _miles(here, origin) / self.SPEED_MPH * 3600
        path.append([float(origin.latitude), float(origin.longitude)])
        return Route(order, arrivals, path, int(elapsed), "fake")


def _miles(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (
        float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude)))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(h))


# =====================================================================
# Real providers
# =====================================================================

def _request_json(url, *, payload=None, headers=None):
    try:
        request = urllib.request.Request(
            url,
            data=(json.dumps(payload).encode() if payload is not None else None),
            headers=headers or {},
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as exc:                          # noqa: BLE001
        raise MappingError(f"Mapping service request failed: {exc}") from exc


def _get_json(url):
    return _request_json(url)


def _duration_seconds(value):
    """Turn a Google protobuf duration such as ``"12.5s"`` into seconds."""
    if not isinstance(value, str) or not value.endswith("s"):
        raise MappingError("Google Routes returned an invalid duration")
    try:
        return float(value[:-1])
    except ValueError:
        raise MappingError("Google Routes returned an invalid duration") from None


def directions_url(origin, destination):
    """A key-free Google Maps link from one GeoPoint to another."""
    query = urllib.parse.urlencode({
        "api": "1",
        "origin": f"{origin.latitude},{origin.longitude}",
        "destination": f"{destination.latitude},{destination.longitude}",
        "travelmode": "driving",
    })
    return f"https://www.google.com/maps/dir/?{query}"


class GoogleMapProvider:
    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

    def __init__(self, api_key):
        self.api_key = api_key

    def geocode(self, street, city, state, zip_code):
        query = urllib.parse.urlencode({
            "address": f"{street}, {city}, {state} {zip_code}",
            "components": "country:US",
            "key": self.api_key,
        })
        data = _get_json(f"{self.GEOCODE_URL}?{query}")
        if data.get("status") == "ZERO_RESULTS":
            return None
        if data.get("status") != "OK":
            raise MappingError(f"Google geocoding failed: {data.get('status')}")
        location = data["results"][0]["geometry"]["location"]
        return GeoPoint(_q6(location["lat"]), _q6(location["lng"]))

    def route(self, origin, stops):
        def waypoint(point):
            return {"location": {"latLng": {
                "latitude": float(point.latitude),
                "longitude": float(point.longitude),
            }}}

        payload = {
            "origin": waypoint(origin),
            "destination": waypoint(origin),
            "intermediates": [waypoint(point) for _, point in stops],
            "travelMode": "DRIVE",
            # Waypoint optimization supports TRAFFIC_AWARE, but not
            # TRAFFIC_AWARE_OPTIMAL.
            "routingPreference": "TRAFFIC_AWARE",
            "optimizeWaypointOrder": True,
            "polylineQuality": "OVERVIEW",
            "polylineEncoding": "ENCODED_POLYLINE",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "routes.duration,routes.legs.duration,routes.polyline.encodedPolyline,"
                "routes.optimizedIntermediateWaypointIndex"
            ),
        }
        data = _request_json(self.ROUTES_URL, payload=payload, headers=headers)
        routes = data.get("routes") or []
        if not routes:
            detail = data.get("error", {}).get("message", "no route returned")
            raise MappingError(f"Google Routes failed: {detail}")

        best = routes[0]
        indices = best.get("optimizedIntermediateWaypointIndex")
        if indices is None:
            indices = list(range(len(stops)))
        if sorted(indices) != list(range(len(stops))):
            raise MappingError("Google Routes returned an invalid waypoint order")

        order = [stops[i][0] for i in indices]
        legs = best.get("legs") or []
        if len(legs) != len(stops) + 1:
            raise MappingError("Google Routes returned the wrong number of route legs")

        arrivals, elapsed = {}, 0.0
        for key, leg in zip(order, legs):
            elapsed += _duration_seconds(leg.get("duration"))
            arrivals[key] = int(round(elapsed))
            elapsed += FakeMapProvider.MINUTES_PER_STOP * 60
        elapsed += _duration_seconds(legs[-1].get("duration"))

        encoded = best.get("polyline", {}).get("encodedPolyline")
        if not encoded:
            raise MappingError("Google Routes returned no route path")
        path = _decode_polyline(encoded)
        return Route(order, arrivals, path, int(round(elapsed)), "google")


class MapboxProvider:
    GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json"
    OPTIMIZE_URL = "https://api.mapbox.com/optimized-trips/v1/mapbox/driving-traffic/{coords}"

    def __init__(self, token):
        self.token = token

    def geocode(self, street, city, state, zip_code):
        text = urllib.parse.quote(f"{street}, {city}, {state} {zip_code}")
        query = urllib.parse.urlencode({
            "access_token": self.token, "country": "us", "types": "address", "limit": 1,
        })
        data = _get_json(f"{self.GEOCODE_URL.format(query=text)}?{query}")
        features = data.get("features") or []
        if not features:
            return None
        lng, lat = features[0]["center"]
        return GeoPoint(_q6(lat), _q6(lng))

    def route(self, origin, stops):
        points = [origin] + [p for _, p in stops]
        coords = ";".join(f"{p.longitude},{p.latitude}" for p in points)
        query = urllib.parse.urlencode({
            "access_token": self.token, "source": "first", "roundtrip": "true",
            "geometries": "geojson",
        })
        data = _get_json(f"{self.OPTIMIZE_URL.format(coords=coords)}?{query}")
        if data.get("code") != "Ok":
            raise MappingError(f"Mapbox optimization failed: {data.get('code')}")

        # waypoints[i] is input point i; waypoint_index is its place in the trip.
        positions = [w["waypoint_index"] for w in data["waypoints"]]
        order = [stops[i - 1][0] for i in sorted(range(1, len(points)), key=lambda i: positions[i])]
        trip = data["trips"][0]
        arrivals, elapsed = {}, 0
        for key, leg in zip(order, trip["legs"]):
            elapsed += int(leg["duration"])
            arrivals[key] = elapsed
            elapsed += FakeMapProvider.MINUTES_PER_STOP * 60
        elapsed += int(trip["legs"][-1]["duration"])
        path = [[lat, lng] for lng, lat in trip["geometry"]["coordinates"]]
        return Route(order, arrivals, path, elapsed, "mapbox")


def _decode_polyline(encoded):
    """Google's encoded polyline format to [[lat, lng], ...]."""
    points, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for axis in (0, 1):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lng += delta
        points.append([lat / 1e5, lng / 1e5])
    return points


# =====================================================================
# Choosing the provider
# =====================================================================

_provider = None


def provider():
    global _provider
    if _provider is None:
        name = os.environ.get("MAP_PROVIDER", "fake")
        if name == "fake":
            _provider = FakeMapProvider()
        elif name == "google":
            _provider = GoogleMapProvider(os.environ["GOOGLE_MAPS_API_KEY"])
        elif name == "mapbox":
            _provider = MapboxProvider(os.environ["MAPBOX_ACCESS_TOKEN"])
        else:
            raise RuntimeError(f"Unknown MAP_PROVIDER '{name}'")
    return _provider


def use_provider(instance):
    """Swap the provider, for tests."""
    global _provider
    _provider = instance
