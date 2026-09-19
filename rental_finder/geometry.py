"""Small-scale planar distance helpers.

King County spans roughly 90 miles across -- small enough that a local
equirectangular projection (flat-earth approximation centered on each query
point) is accurate to a small fraction of a foot at the distances this tool
cares about (a few thousand feet at most). No real map projection library
needed.
"""

from __future__ import annotations

import math

METERS_PER_DEGREE_LAT = 111_320.0
FEET_PER_METER = 3.28084


def _project(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """(x_ft, y_ft) of (lat, lon) relative to origin (lat0, lon0)."""
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat0))
    x_ft = (lon - lon0) * meters_per_degree_lon * FEET_PER_METER
    y_ft = (lat - lat0) * METERS_PER_DEGREE_LAT * FEET_PER_METER
    return x_ft, y_ft


def distance_ft(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    x, y = _project(lat0, lon0, lat1, lon1)
    return math.hypot(x, y)


def _point_to_segment_ft(px, py, ax, ay, bx, by) -> float:
    abx, aby = bx - ax, by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_len_sq))
    closest_x, closest_y = ax + t * abx, ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def _point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_intersect:
                inside = not inside
    return inside


def distance_ft_to_esri_geometry(lat0: float, lon0: float, geometry: dict | None) -> float | None:
    """Distance from (lat0, lon0) to an Esri JSON geometry returned with
    outSR=4326 (lon/lat degrees) -- either a point ({x, y}) or a polygon
    ({rings: [[[lon, lat], ...], ...]}).

    Returns 0.0 if the point falls inside the polygon.
    """
    if not geometry:
        return None

    if "x" in geometry and "y" in geometry:
        return distance_ft(lat0, lon0, geometry["y"], geometry["x"])

    rings = geometry.get("rings")
    if not rings:
        return None

    projected_rings = [[_project(lat0, lon0, lat, lon) for lon, lat in ring] for ring in rings]

    if any(_point_in_ring(0.0, 0.0, ring) for ring in projected_rings):
        return 0.0

    best = math.inf
    for ring in projected_rings:
        n = len(ring)
        for i in range(n):
            ax, ay = ring[i]
            bx, by = ring[(i + 1) % n]
            best = min(best, _point_to_segment_ft(0.0, 0.0, ax, ay, bx, by))
    return best if best != math.inf else None
