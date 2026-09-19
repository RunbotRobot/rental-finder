"""Turn a listing's (often vague) location text into coordinates.

Craigslist listings sometimes carry an exact map pin already (handled in
sources/craigslist.py). When they don't, we're generally geocoding a
neighborhood name or cross-street, not a real address — so precision here is
"good enough to check whether a candidate is worth a closer look," not
"good enough to submit to a CCO." Every listing's `location_precision` field
should be surfaced in the final report so low-confidence matches aren't
silently treated the same as an exact pin.

Primary: US Census Bureau geocoder (free, no API key, no rate-limit hassle).
Fallback: Nominatim/OpenStreetMap (free, but strict 1 req/sec usage policy —
respected here via the shared request_delay_seconds).

NOTE: the Census `benchmark` parameter value is versioned and occasionally
renamed by the Census Bureau. If geocoding starts failing outright, check
https://geocoding.geo.census.gov/geocoder/benchmarks for the current name.
"""

from __future__ import annotations

import logging
import time

import requests

from .config import Settings

logger = logging.getLogger(__name__)

CENSUS_BENCHMARK = "Public_AR_Current"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode_census(address: str, settings: Settings, session: requests.Session) -> tuple[float, float] | None:
    params = {"address": address, "benchmark": CENSUS_BENCHMARK, "format": "json"}
    try:
        resp = session.get(CENSUS_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        coords = matches[0]["coordinates"]
        return float(coords["y"]), float(coords["x"])  # lat, lon
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.debug("Census geocode failed for %r: %s", address, exc)
        return None


def geocode_nominatim(address: str, settings: Settings, session: requests.Session) -> tuple[float, float] | None:
    params = {
        "q": f"{address}, King County, WA",
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": settings.geocode_user_agent}
    try:
        resp = session.get(
            NOMINATIM_URL, params=params, headers=headers, timeout=settings.request_timeout_seconds
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
        logger.debug("Nominatim geocode failed for %r: %s", address, exc)
        return None
    finally:
        # Nominatim's usage policy caps free use at 1 req/sec.
        time.sleep(max(settings.request_delay_seconds, 1.0))


def geocode(address: str, settings: Settings, session: requests.Session | None = None) -> tuple[float, float] | None:
    session = session or requests.Session()
    result = geocode_census(address, settings, session)
    if result is not None:
        return result
    return geocode_nominatim(address, settings, session)
