import math

from rental_finder.geometry import distance_ft, distance_ft_to_esri_geometry


def test_distance_ft_same_point_is_zero():
    assert distance_ft(47.6, -122.3, 47.6, -122.3) == 0.0


def test_distance_ft_one_degree_latitude_is_roughly_364000_ft():
    dist = distance_ft(47.0, -122.0, 48.0, -122.0)
    assert math.isclose(dist, 364_000, rel_tol=0.01)


def test_distance_to_point_geometry():
    dist = distance_ft_to_esri_geometry(47.6, -122.3, {"x": -122.3, "y": 47.6})
    assert dist == 0.0


def test_distance_to_point_geometry_nonzero():
    # ~0.01 degrees latitude apart -> roughly 3640 ft
    dist = distance_ft_to_esri_geometry(47.60, -122.30, {"x": -122.30, "y": 47.61})
    assert math.isclose(dist, 3640, rel_tol=0.02)


def test_point_inside_polygon_is_zero_distance():
    square = {
        "rings": [
            [
                [-122.31, 47.60],
                [-122.29, 47.60],
                [-122.29, 47.62],
                [-122.31, 47.62],
                [-122.31, 47.60],
            ]
        ]
    }
    dist = distance_ft_to_esri_geometry(47.61, -122.30, square)
    assert dist == 0.0


def test_point_outside_polygon_is_positive_distance():
    square = {
        "rings": [
            [
                [-122.31, 47.60],
                [-122.29, 47.60],
                [-122.29, 47.62],
                [-122.31, 47.62],
                [-122.31, 47.60],
            ]
        ]
    }
    # well north of the square
    dist = distance_ft_to_esri_geometry(47.70, -122.30, square)
    assert dist is not None and dist > 0


def test_missing_geometry_returns_none():
    assert distance_ft_to_esri_geometry(47.6, -122.3, None) is None
    assert distance_ft_to_esri_geometry(47.6, -122.3, {}) is None
