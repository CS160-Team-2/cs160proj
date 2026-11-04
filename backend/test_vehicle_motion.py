"""Pure geometry tests; also runnable with python -m unittest."""
import unittest
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import patch
from services.vehicle import position_on_path, route_segments
from services.vehicle import SimulatedVehicleLink


class VehicleMotionTests(unittest.TestCase):
    def test_follows_the_road_vertices_rather_than_cutting_a_corner(self):
        path = [[0, 0], [0, 1], [1, 1]]
        self.assertEqual(position_on_path(path, 0), [0, 0])
        lat, lng = position_on_path(path, 0.75)
        self.assertAlmostEqual(lng, 1)
        self.assertAlmostEqual(lat, 0.5)
        self.assertEqual(position_on_path(path, 1), [1, 1])

    def test_uses_distance_not_the_number_of_vertices(self):
        lat, lng = position_on_path([[0, 0], [0, 0.1], [0, 1]], 0.5)
        self.assertEqual(lat, 0)
        self.assertAlmostEqual(lng, 0.5)

    def test_handles_repeated_coordinates_and_coincident_stops(self):
        self.assertEqual(position_on_path([[1, 2], [1, 2]], 0.5), [1, 2])
        self.assertEqual(position_on_path([[1, 2]], 1), [1, 2])

    def test_preserves_the_stop_order_and_excludes_the_return_leg(self):
        path = [[0, 0], [0, 1], [1, 1], [0, 0]]
        stops = [{"latitude": "0", "longitude": "1"}, {"latitude": "1", "longitude": "1"}]
        self.assertEqual(route_segments(path, stops), [[[0, 0], [0, 1]], [[0, 1], [1, 1]]])

    def test_clamps_progress_to_the_route(self):
        self.assertEqual(position_on_path([[0, 0], [0, 1]], -1), [0, 0])
        self.assertEqual(position_on_path([[0, 0], [0, 1]], 2), [0, 1])


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.callbacks = []
        self.reports = []
        self.completed = []
        self.trip = {'status': 'out_for_delivery', 'route_json': {'path': [[0, 0], [0, 1], [1, 1]]}}
        self.db = ModuleType('db')
        self.db.query_one = lambda *_: self.trip
        owner = self

        class Cursor:
            def execute(self, sql, parameters):
                if 'last_latitude' in sql:
                    owner.reports.append(parameters)
                else:
                    owner.assertIn("last_report = 'completed'", sql)

        @contextmanager
        def transaction():
            yield Cursor()
        self.db.transaction = transaction
        delivery = ModuleType('routes.delivery')

        def complete_stop(trip_id, order_id):
            self.completed.append((trip_id, order_id))
            self.trip['status'] = 'completed'
            return 'completed'
        delivery.complete_stop = complete_stop
        self.modules = patch.dict('sys.modules', {'db': self.db, 'routes.delivery': delivery})
        self.modules.start()
        self.addCleanup(self.modules.stop)

        class Timer:
            def __init__(timer, interval, callback):
                timer.callback = callback
            def start(timer):
                owner.callbacks.append(timer.callback)
        self.timers = patch('services.vehicle.threading.Timer', Timer)
        self.timers.start()
        self.addCleanup(self.timers.stop)

    def test_simulator_reports_progress_on_the_road_before_completing_the_stop(self):
        link = SimulatedVehicleLink(10)
        self.assertTrue(link.send_trip({'vehicle_id': 1}, 8, [
            {'order_id': 3, 'latitude': '1', 'longitude': '1'}]))
        self.callbacks.pop(0)()
        latitude, longitude, report, trip_id = self.reports[0]
        self.assertEqual(latitude, 0)
        self.assertGreater(longitude, 0)
        self.assertLess(longitude, 1)
        self.assertEqual((report, trip_id), ('en_route', 8))
        self.assertEqual(self.completed, [])
        while self.callbacks:
            self.callbacks.pop(0)()
        self.assertEqual(self.completed, [(8, 3)])
        self.assertEqual(self.reports[-1][:3], (1.0, 1.0, 'at_stop'))

    def test_simulator_stops_if_a_manager_already_finished_the_trip(self):
        SimulatedVehicleLink(10).send_trip({'vehicle_id': 1}, 8, [
            {'order_id': 3, 'latitude': '1', 'longitude': '1'}])
        self.trip['status'] = 'completed'
        self.callbacks.pop(0)()
        self.assertEqual(self.reports, [])
        self.assertEqual(self.completed, [])
        self.assertEqual(self.callbacks, [])


if __name__ == '__main__':
    unittest.main()
