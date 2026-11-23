import difflib
import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal


# The provider could not be reached or could not plan the route.
class MappingError(Exception):
    pass


@dataclass
class GeoPoint:
    latitude: Decimal
    longitude: Decimal


@dataclass
class Route:
    stop_order: list
    arrival_seconds: dict
    path: list = field(default_factory=list)
    total_seconds: int = 0
    provider: str = ""


def store_location():
    return GeoPoint(
        Decimal(os.environ.get("STORE_LATITUDE", "37.335200")),
        Decimal(os.environ.get("STORE_LONGITUDE", "-121.881100")),
    )


# Straight-line miles between the store and a point.
def miles_from_store(point):
    return _miles(store_location(), point)


def _q6(value):
    return Decimal(str(value)).quantize(Decimal("0.000001"))


_SUFFIXES = {
    "street": "st", "st": "st", "drive": "dr", "dr": "dr", "road": "rd", "rd": "rd",
    "avenue": "ave", "ave": "ave", "av": "ave", "boulevard": "blvd", "blvd": "blvd",
    "lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "place": "pl", "pl": "pl",
    "square": "sq", "sq": "sq", "circle": "cir", "cir": "cir", "terrace": "ter", "ter": "ter",
    "parkway": "pkwy", "pkwy": "pkwy", "highway": "hwy", "hwy": "hwy", "way": "way",
    "trail": "trl", "trl": "trl", "plaza": "plz", "plz": "plz", "alley": "aly", "aly": "aly",
}
_DIRECTIONS = {"north": "n", "south": "s", "east": "e", "west": "w", "n": "n", "s": "s", "e": "e", "w": "w"}
_NAME_SYNONYMS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
    "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th",
    "twelfth": "12th", "saint": "st", "mount": "mt", "fort": "ft", "port": "pt",
}
_UNIT_WORDS = {"apt", "apartment", "unit", "suite", "ste", "fl", "floor", "room", "rm", "bldg", "building"}
_MIN_RELEVANCE = 0.6
_PRECISE = {"rooftop", "parcel", "point", "interpolated", "intersection"}


# Lower-cases a name and drops punctuation, returning its words.
def _words(text):
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower().replace("#", " # ")).split()


# Splits a typed street line into (house number, street-name words, street suffix), ignoring apartment details.
def _street_parts(street):
    words = _words(street)
    for index, word in enumerate(words):
        if word in _UNIT_WORDS or word == "#":
            words = words[:index]
            break
    number = words[0] if words and re.fullmatch(r"\d+[a-z]?", words[0]) else None
    rest = words[1:] if number else words
    suffix = _SUFFIXES.get(rest[-1]) if rest else None
    name = rest[:-1] if suffix else rest
    name = [_NAME_SYNONYMS.get(_DIRECTIONS.get(word, word), _DIRECTIONS.get(word, word)) for word in name]
    return number, " ".join(name), suffix


# True when two names are the same or differ by a small typo.
def _similar(a, b):
    a, b = " ".join(_words(a)), " ".join(_words(b))
    return bool(a) and bool(b) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)


# True when the found address is the typed address
def address_matches(typed_street, typed_city, typed_state, typed_zip,
                    found_number, found_street, found_city, found_state, found_zip):
    number, name, suffix = _street_parts(typed_street)
    f_number, f_name, f_suffix = _street_parts(f"{found_number or ''} {found_street or ''}")
    if not number or not f_number or number != f_number:
        return False
    if not _similar(name, f_name) or (suffix and f_suffix and suffix != f_suffix):
        return False
    state = " ".join(_words(typed_state))
    if found_state and state not in {" ".join(_words(found_state[0])), " ".join(_words(found_state[1]))}:
        return False
    city_ok = bool(found_city) and _similar(typed_city, found_city)
    zip_ok = bool(found_zip) and (typed_zip or "")[:3] == str(found_zip)[:3]
    if not found_city and not found_zip:
        return True
    return city_ok or zip_ok


# Deterministic stand-in for a real mapping service.
class FakeMapProvider:

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


# Turn a Google protobuf duration such as ``"12.5s"`` into seconds.
def _duration_seconds(value):
    if not isinstance(value, str) or not value.endswith("s"):
        raise MappingError("Google Routes returned an invalid duration")
    try:
        return float(value[:-1])
    except ValueError:
        raise MappingError("Google Routes returned an invalid duration") from None


# A key-free Google Maps link from one GeoPoint to another.
def directions_url(origin, destination):
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
        best = data["results"][0]
        if best.get("partial_match") or best["geometry"].get("location_type") not in ("ROOFTOP", "RANGE_INTERPOLATED"):
            return None
        found = {kind: component for component in best.get("address_components", [])
                 for kind in component.get("types", [])}

        # One piece of the found address, such as its street number.
        def piece(kind, key="long_name"):
            return (found.get(kind) or {}).get(key)

        region = found.get("administrative_area_level_1")
        if not address_matches(street, city, state, zip_code,
                               piece("street_number"), piece("route"),
                               piece("locality") or piece("sublocality") or piece("postal_town"),
                               (region["short_name"], region["long_name"]) if region else None,
                               piece("postal_code")):
            return None
        location = best["geometry"]["location"]
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
        best = features[0]
        if best.get("relevance", 1) < _MIN_RELEVANCE:
            return None
        if (best.get("properties") or {}).get("accuracy") not in _PRECISE:
            return None
        context = {item["id"].split(".")[0]: item for item in best.get("context", [])}
        region = context.get("region")
        short = (region or {}).get("short_code", "")
        if not address_matches(street, city, state, zip_code,
                               best.get("address"), best.get("text"),
                               (context.get("place") or {}).get("text"),
                               (short.split("-")[-1], region.get("text", "")) if region else None,
                               (context.get("postcode") or {}).get("text")):
            return None
        lng, lat = best["center"]
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


# Google's encoded polyline format to [[lat, lng], ...].
def _decode_polyline(encoded):
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


_provider = None


# Read the active adapter's identity without a network call or key lookup.
def provider_name():
    if _provider is None:
        return os.environ.get('MAP_PROVIDER', 'fake')
    for cls, name in ((GoogleMapProvider, 'google'), (MapboxProvider, 'mapbox'), (FakeMapProvider, 'fake')):
        if isinstance(_provider, cls):
            return name
    return getattr(_provider, 'name', 'custom')


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


# Swap the provider, for tests.
def use_provider(instance):
    global _provider
    _provider = instance
