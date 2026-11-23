from urllib.parse import urlsplit

from services import mapping


def polyline(points):
    last_lat = last_lng = 0
    result = ''
    for lat, lng in points:
        lat, lng = round(lat * 100000), round(lng * 100000)
        for delta in (lat - last_lat, lng - last_lng):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 32:
                result += chr((32 | (value & 31)) + 63); value >>= 5
            result += chr(value + 63)
        last_lat, last_lng = lat, lng
    return result


# Splits "200 E Santa Clara St, San Jose, CA 95113" (the way the adapters send it) back into its parts.
def typed_address(text):
    street, city, rest = [part.strip() for part in text.split(",")[:3]]
    state, zip_code = rest.split()[:2]
    return street, city, state, zip_code


# What Google answers when it found exactly the typed address.
def google_found(text):
    street, city, state, zip_code = typed_address(text)
    number, route = street.split(" ", 1)
    parts = [("street_number", number, number), ("route", route, route), ("locality", city, city),
             ("administrative_area_level_1", state, state), ("postal_code", zip_code, zip_code)]
    return {"status": "OK", "results": [{
        "geometry": {"location": {"lat": 37.34, "lng": -121.89}, "location_type": "ROOFTOP"},
        "address_components": [{"types": [kind], "long_name": long, "short_name": short} for kind, long, short in parts]}]}


# What Mapbox answers when it found exactly the typed address.
def mapbox_found(text):
    street, city, state, zip_code = typed_address(text)
    number, route = street.split(" ", 1)
    return {"features": [{"center": [-121.89, 37.34], "relevance": 1, "address": number, "text": route,
                          "properties": {"accuracy": "rooftop"},
                          "context": [{"id": "postcode.1", "text": zip_code}, {"id": "place.1", "text": city},
                                      {"id": "region.1", "text": state, "short_code": f"US-{state}"}]}]}


class MappingHTTPFake:
    def __init__(self, name):
        self.name, self.mode, self.calls = name, 'ok', []

    # The address the adapter asked about, read back out of the request address.
    def typed(self, url):
        from urllib.parse import parse_qs, unquote
        if self.name == 'google':
            return parse_qs(urlsplit(url).query)['address'][0]
        return unquote(urlsplit(url).path.rsplit('/', 1)[1].removesuffix('.json'))

    def request(self, url, *, payload=None, headers=None):
        self.calls.append(url.split('?')[0])
        if self.mode == 'down':
            raise mapping.MappingError('Mapping service unavailable')
        route = payload is not None or 'optimized-trips' in url
        if not route:
            if self.name == 'google':
                return {'status': 'ZERO_RESULTS'} if self.mode == 'not_found' else google_found(self.typed(url))
            return {'features': []} if self.mode == 'not_found' else mapbox_found(self.typed(url))
        if self.mode == 'no_route':
            return {'routes': [], 'error': {'message': 'No route'}} if self.name == 'google' else {'code': 'NoRoute'}
        if self.name == 'google':
            def point(waypoint):
                p = waypoint['location']['latLng']; return [p['latitude'], p['longitude']]
            origin = point(payload['origin'])
            stops = [point(p) for p in payload['intermediates']]
        else:
            coords = urlsplit(url).path.rsplit('/', 1)[1].split(';')
            points = [[float(v) for v in pair.split(',')][::-1] for pair in coords]
            origin, stops = points[0], points[1:]
        path = [origin, *reversed(stops), origin]
        n = len(stops)
        if self.name == 'google':
            return {'routes': [{'optimizedIntermediateWaypointIndex': list(reversed(range(n))),
                'legs': [{'duration': '100s'} for _ in range(n + 1)],
                'polyline': {'encodedPolyline': polyline(path)}}]}
        return {'code': 'Ok', 'waypoints': [{'waypoint_index': i} for i in [0, *range(n, 0, -1)]],
            'trips': [{'legs': [{'duration': 100} for _ in range(n + 1)],
                       'geometry': {'coordinates': [[lng, lat] for lat, lng in path]}}]}


def adapter(monkeypatch, name):
    transport = MappingHTTPFake(name)
    monkeypatch.setattr(mapping, '_request_json', transport.request)
    monkeypatch.setattr(mapping, '_get_json', transport.request)
    provider = mapping.GoogleMapProvider('test-only-key') if name == 'google' else mapping.MapboxProvider('test-only-token')
    return provider, transport
