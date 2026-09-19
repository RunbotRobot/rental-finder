"""Facility-proximity checks against real King County / WA state open data.

Sources (verified live before wiring this up -- see PR description for how):

- Schools (public AND private): King County GIS "School Sites" layer.
- Parks: King County GIS's countywide "Parks in King County" polygon layer,
  which covers city, county, and state-owned park sites throughout the
  county (confirmed live: returns City of Seattle parks as well as county
  and state ones, so no separate per-city source is needed).
- Licensed childcare: WA DCYF's open dataset on data.wa.gov. King County GIS
  does not publish a childcare layer at all.

(An older, separately-hosted King County parks service at
gismaps.kingcounty.gov was tried first and consistently returned a generic
"Unable to perform query operation" error on every query -- including the
simplest possible one -- suggesting it's currently broken server-side
independent of anything this code sends it. The AGOL-hosted layer used here
is a different, working service with better coverage anyway.)

Two different strategies depending on how each source is queried:
- Schools and parks are ArcGIS FeatureServers, queried live per listing at
  the single largest configured buffer tier, then an exact distance in feet
  is computed client-side from the returned geometry (point or polygon) --
  one query covers every tier at once instead of one query per tier.
- Childcare comes from a flat, small (~900 active King County providers)
  dataset that's cheaper to fetch once per run and check locally than to
  query remotely per listing.

None of these datasets are guaranteed complete or current (a park or
provider that opened recently might not show up yet). Treat every result
here as a starting point for manual verification against a map -- never as
a final answer, and NEVER as a substitute for your CCO's own judgment.

A query that fails outright (network error, bad response) is recorded as
*unverified* (None), not as a pass -- a failed check should never silently
read as "far enough away."
"""

from __future__ import annotations

import logging

import requests

from .config import Settings
from .geometry import distance_ft, distance_ft_to_esri_geometry
from .models import Listing

logger = logging.getLogger(__name__)

SCHOOLS_URL = (
    "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/"
    "SCHSITE_POINT_107/FeatureServer/0/query"
)
PARKS_URL = (
    "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/"
    "PARK_AREA_228/FeatureServer/0/query"
)
DCYF_CHILDCARE_URL = "https://data.wa.gov/resource/was8-3ni8.json"

# Sentinel: the query failed, so the distance is genuinely unknown -- distinct
# from a successful query that found nothing within the max tier (which does
# mean "clear at every configured buffer").
UNVERIFIED = object()


def _arcgis_query(
    url: str, lat: float, lon: float, max_distance_ft: float, out_fields: str, settings: Settings, session: requests.Session
) -> tuple[bool, list[dict]]:
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
            return False, []
        return True, data.get("features", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("ArcGIS query failed for %s: %s", url, exc)
        return False, []


def _nearest_distance_ft(features: list[dict], lat: float, lon: float) -> float | None:
    best = None
    for feature in features:
        dist = distance_ft_to_esri_geometry(lat, lon, feature.get("geometry"))
        if dist is not None and (best is None or dist < best):
            best = dist
    return best


def _fetch_childcare_providers(settings: Settings, session: requests.Session) -> tuple[bool, list[dict]]:
    params = {
        "physicalcounty": "KING",
        "latestoperatingstatus": "Active",
        "$select": "providername,physciallatitude,physicallongitude",
        "$limit": 5000,
    }
    try:
        resp = session.get(DCYF_CHILDCARE_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        rows = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Failed to fetch DCYF childcare data: %s", exc)
        return False, []

    providers = []
    for row in rows:
        try:
            providers.append(
                {
                    "name": row.get("providername"),
                    "lat": float(row["physciallatitude"]),
                    "lon": float(row["physicallongitude"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return True, providers


def _apply_result(listing: Listing, facility_type: str, nearest_ft, settings: Settings) -> None:
    if nearest_ft is UNVERIFIED:
        listing.nearest_facility_ft[facility_type] = None
        listing.facility_clearance[facility_type] = {tier: None for tier in settings.buffer_tiers_ft}
        return

    listing.nearest_facility_ft[facility_type] = nearest_ft
    if nearest_ft is None:
        listing.facility_clearance[facility_type] = {tier: True for tier in settings.buffer_tiers_ft}
    else:
        listing.facility_clearance[facility_type] = {
            tier: nearest_ft >= tier for tier in settings.buffer_tiers_ft
        }


def annotate_distances(listings: list[Listing], settings: Settings, session: requests.Session) -> None:
    """Mutates each listing's nearest_facility_ft / facility_clearance in place."""
    max_tier = max(settings.buffer_tiers_ft)

    childcare_providers: list[dict] = []
    childcare_ok = True
    if "childcare" in settings.facility_types:
        childcare_ok, childcare_providers = _fetch_childcare_providers(settings, session)

    for listing in listings:
        if listing.latitude is None or listing.longitude is None:
            for ftype in settings.facility_types:
                _apply_result(listing, ftype, UNVERIFIED, settings)
            continue

        lat, lon = listing.latitude, listing.longitude

        if "school" in settings.facility_types:
            ok, features = _arcgis_query(SCHOOLS_URL, lat, lon, max_tier, "NAME,ADDRESS", settings, session)
            dist = _nearest_distance_ft(features, lat, lon) if ok else UNVERIFIED
            _apply_result(listing, "school", dist, settings)

        if "park" in settings.facility_types:
            ok, features = _arcgis_query(PARKS_URL, lat, lon, max_tier, "SITENAME,OWNER", settings, session)
            dist = _nearest_distance_ft(features, lat, lon) if ok else UNVERIFIED
            _apply_result(listing, "park", dist, settings)

        if "childcare" in settings.facility_types:
            if not childcare_ok:
                dist = UNVERIFIED
            else:
                nearest = None
                for provider in childcare_providers:
                    d = distance_ft(lat, lon, provider["lat"], provider["lon"])
                    if nearest is None or d < nearest:
                        nearest = d
                dist = nearest
            _apply_result(listing, "childcare", dist, settings)
