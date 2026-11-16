"""HTTP fakes for the real Google and Mapbox adapters; never use live keys."""
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


class MappingHTTPFake:
    def __init__(self, name):
        self.name, self.mode, self.calls = name, 'ok', []

    def request(self, url, *, payload=None, headers=None):
        self.calls.append(url.split('?')[0])
        if self.mode == 'down':
            raise mapping.MappingError('Mapping service unavailable')
        route = payload is not None or 'optimized-trips' in url
        if not route:
            if self.name == 'google':
                return {'status': 'ZERO_RESULTS'} if self.mode == 'not_found' else {
                    'status': 'OK', 'results': [{'geometry': {'location': {'lat': 37.34, 'lng': -121.89}}}]}
            return {'features': []} if self.mode == 'not_found' else {'features': [{'center': [-121.89, 37.34]}]}
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
