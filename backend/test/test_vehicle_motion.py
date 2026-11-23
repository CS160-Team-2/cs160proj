import unittest
from services.vehicle import position_on_path, route_segments


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


if __name__ == '__main__':
    unittest.main()
