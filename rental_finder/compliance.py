"""Facility-proximity checks against real King County / WA state open data.

What each facility type covers -- and doesn't. Every endpoint below was
verified live before being wired in.

school     King County GIS "School Sites" layer. Public AND private K-12.
           Per its own description it does NOT include preschools.
park       King County GIS "Parks in King County" polygon layer: city,
           county, and state park sites countywide (confirmed live to
           include City of Seattle parks, so no separate city source).
           Distances are measured to the park boundary, and a point inside
           a park reports 0 ft.
childcare  Three WA DCYF open datasets on data.wa.gov, merged:
             - licensed child care CENTERS and school-age programs
             - ECEAP (state-funded preschool) sites
             - Head Start sites
           NOT COVERED: licensed FAMILY HOME child care (in-home daycares).
           DCYF does not publish those locations as open data -- they're
           only in its interactive Child Care Check tool. There are far
           more family homes than centers, and they're spread through
           residential neighborhoods, so a listing that clears every check
           here can still be next door to one. Check Child Care Check
           (findchildcarewa.org) by hand for any address you're serious
           about, and expect your CCO to.

An older, separately-hosted King County parks service (gismaps.kingcounty.gov)
was tried first and returned a generic "Unable to perform query operation"
on every query, including the simplest possible one -- broken server-side.
The AGOL-hosted layer used here is a different, working service.

Query strategy: schools and parks are ArcGIS FeatureServers, queried once
per listing at the largest configured buffer, with the exact distance then
computed client-side from the returned geometry so every smaller tier is
answered by the same query. The childcare datasets are small (~1,000 King
County points combined) and are fetched once per run and checked locally.

A query that fails (network error, bad response) leaves that facility type
unchecked, which the report shows as unknown. A failed check must never
read as "far enough away."
"""

from __future__ import annotations

import logging

import requests

from .config import Settings
from .geometry import distance_ft, distance_ft_to_esri_geometry
from .models import PRECISION_ADDRESS, Listing

logger = logging.getLogger(__name__)

SCHOOLS_URL = (
    "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/"
    "SCHSITE_POINT_107/FeatureServer/0/query"
)
PARKS_URL = (
    "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/"
    "PARK_AREA_228/FeatureServer/0/query"
)

# (url, params, lat_field, lon_field)
CHILDCARE_SOURCES = (
    (
        "https://data.wa.gov/resource/was8-3ni8.json",  # licensed centers + school-age programs
        {"physicalcounty": "KING", "latestoperatingstatus": "Active", "$limit": 5000},
        "physciallatitude",  # sic -- the field really is misspelled upstream
        "physicallongitude",
    ),
    (
        "https://data.wa.gov/resource/f8ky-qzze.json",  # ECEAP sites
        {"$where": "upper(physicalcounty)='KING'", "$limit": 5000},
        "latitude",
        "longitude",
    ),
    (
        "https://data.wa.gov/resource/adad-395d.json",  # Head Start sites
        {"$where": "upper(physicalcounty)='KING'", "$limit": 5000},
        "latitude",
        "longitude",
    ),
)


def _arcgis_query(
    url: str,
    lat: float,
    lon: float,
    max_distance_ft: float,
    out_fields: str,
    settings: Settings,
    session: requests.Session,
) -> list[dict] | None:
    """Features within max_distance_ft, or None if the query failed."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "distance": max_distance_ft,
        "units": "esriSRUnit_Foot",
        "outSR": 4326,
        "outFields": out_fields,
        "returnGeometry": "true",
        "f": "json",
    }
    try:
        resp = session.get(url, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.warning("ArcGIS query error from %s: %s", url, data["error"])
            return None
        return data.get("features", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("ArcGIS query failed for %s: %s", url, exc)
        return None


def _nearest_feature_ft(features: list[dict], lat: float, lon: float) -> float | None:
    distances = [distance_ft_to_esri_geometry(lat, lon, f.get("geometry")) for f in features]
    distances = [d for d in distances if d is not None]
    return min(distances) if distances else None


def fetch_childcare_points(settings: Settings, session: requests.Session) -> list[tuple[float, float]] | None:
    """All King County childcare points from every source, or None if any
    source failed -- a partial list would understate what's nearby."""
    points: set[tuple[float, float]] = set()
    for url, params, lat_field, lon_field in CHILDCARE_SOURCES:
        try:
            resp = session.get(url, params=params, timeout=settings.request_timeout_seconds)
            resp.raise_for_status()
            rows = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Failed to fetch childcare data from %s: %s", url, exc)
            return None
        added = 0
        for row in rows:
            try:
                points.add((round(float(row[lat_field]), 6), round(float(row[lon_field]), 6)))
                added += 1
            except (KeyError, TypeError, ValueError):
                continue
        logger.info("childcare source %s: %d points", url.rsplit("/", 1)[-1], added)
    return sorted(points)


def _nearest_point_ft(points: list[tuple[float, float]], lat: float, lon: float) -> float | None:
    return min((distance_ft(lat, lon, plat, plon) for plat, plon in points), default=None)


def annotate_distances(listings: list[Listing], settings: Settings, session: requests.Session) -> None:
    """For each address-precision listing, fill nearest_facility_ft and
    facility_checked for every configured facility type not already
    checked (cached results are skipped)."""
    max_tier = max(settings.buffer_tiers_ft)
    todo = [
        l for l in listings
        if l.location_precision == PRECISION_ADDRESS
        and not all(l.facility_checked.get(t) for t in settings.facility_types)
    ]
    if not todo:
        return

    childcare_points = None
    if "childcare" in settings.facility_types:
        childcare_points = fetch_childcare_points(settings, session)

    for listing in todo:
        lat, lon = listing.latitude, listing.longitude
        if lat is None or lon is None:
            continue

        if "school" in settings.facility_types and not listing.facility_checked.get("school"):
            features = _arcgis_query(SCHOOLS_URL, lat, lon, max_tier, "NAME,ADDRESS", settings, session)
            if features is not None:
                listing.nearest_facility_ft["school"] = _nearest_feature_ft(features, lat, lon)
                listing.facility_checked["school"] = True

        if "park" in settings.facility_types and not listing.facility_checked.get("park"):
            features = _arcgis_query(PARKS_URL, lat, lon, max_tier, "SITENAME,OWNER", settings, session)
            if features is not None:
                listing.nearest_facility_ft["park"] = _nearest_feature_ft(features, lat, lon)
                listing.facility_checked["park"] = True

        if childcare_points is not None and not listing.facility_checked.get("childcare"):
            listing.nearest_facility_ft["childcare"] = _nearest_point_ft(childcare_points, lat, lon)
            listing.facility_checked["childcare"] = True
