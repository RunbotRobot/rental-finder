"""Turn a listing's location text into coordinates -- honestly.

The trap here is false precision. A listing that only says "Seattle, WA"
will happily geocode to the city's centroid, and a distance check run on
that point produces confident-looking numbers that mean nothing. (This
happened in an early smoke test: a "Seattle, WA" listing was reported as
"536 ft from the nearest park" -- the park nearest downtown's centroid.)

So the rule is: buffer distances are only ever computed from a street
address with a house number. Anything vaguer is classified as area-level,
used only to work out which county the listing is in, and reported as
unknown for every buffer tier.

Primary geocoder: US Census Bureau (free, no key, no usage-policy hassle).
Its `geographies` endpoint returns the county along with the coordinates,
which is how out-of-county listings get filtered. Fallback: Nominatim/OSM,
accepted only when it resolves to a specific building (it reports a house
number), with its 1 request/second usage policy respected.

The Census `benchmark`/`vintage` values are versioned and occasionally
renamed. If geocoding starts failing outright, check
https://geocoding.geo.census.gov/geocoder/benchmarks?format=json and
https://geocoding.geo.census.gov/geocoder/vintages?benchmark=Public_AR_Current&format=json
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from .config import Settings
from .geometry import distance_ft
from .models import has_street_number  # noqa: F401  (re-exported; the rule lives with the model)

logger = logging.getLogger(__name__)

CENSUS_BENCHMARK = "Public_AR_Current"
CENSUS_VINTAGE = "Current_Current"
CENSUS_ADDRESS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
CENSUS_COORDS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    county: str | None
    state: str | None


def _census_name(geographies: dict, layer: str) -> str | None:
    entries = geographies.get(layer) or []
    return entries[0].get("NAME") if entries else None


def _geocode_census(address: str, settings: Settings, session: requests.Session) -> GeocodeResult | None:
    params = {
        "address": address,
        "benchmark": CENSUS_BENCHMARK,
        "vintage": CENSUS_VINTAGE,
        "format": "json",
    }
    try:
        resp = session.get(CENSUS_ADDRESS_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        match = matches[0]
        geographies = match.get("geographies", {})
        return GeocodeResult(
            latitude=float(match["coordinates"]["y"]),
            longitude=float(match["coordinates"]["x"]),
            county=_census_name(geographies, "Counties"),
            state=_census_name(geographies, "States"),
        )
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        logger.debug("Census geocode failed for %r: %s", address, exc)
        return None


def _geocode_nominatim(address: str, settings: Settings, session: requests.Session) -> GeocodeResult | None:
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
        "addressdetails": 1,
    }
    try:
        resp = session.get(NOMINATIM_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        top = results[0]
        details = top.get("address", {})
        # Without a house number this is a street, neighborhood, or city
        # centroid -- exactly the false precision we're refusing to report.
        if not details.get("house_number"):
            return None
        return GeocodeResult(
            latitude=float(top["lat"]),
            longitude=float(top["lon"]),
            county=details.get("county"),
            state=details.get("state"),
        )
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        logger.debug("Nominatim geocode failed for %r: %s", address, exc)
        return None
    finally:
        time.sleep(max(settings.request_delay_seconds, 1.0))


def is_plausible(result: GeocodeResult, pin_lat: float | None, pin_lon: float | None, max_pin_miles: float = 25.0) -> bool:
    """Guard against a bare street like '718 15th Ave' matching the wrong
    town entirely (seen live: a Seattle listing geocoded to Weld County,
    Colorado). Must be in Washington, and if Craigslist gave us a map pin
    -- coarse, but not a thousand miles off -- must be near it."""
    if result.state and result.state != "Washington":
        return False
    if pin_lat is not None and pin_lon is not None:
        if distance_ft(result.latitude, result.longitude, pin_lat, pin_lon) > max_pin_miles * 5280:
            return False
    return True


def geocode_address(address: str, settings: Settings, session: requests.Session) -> GeocodeResult | None:
    """Address-level geocode, or None. Callers should only pass text that
    passes has_street_number(); this won't stop you, but the result for a
    bare city name is meaningless."""
    result = _geocode_census(address, settings, session)
    if result is not None:
        return result
    return _geocode_nominatim(address, settings, session)


def county_for_point(lat: float, lon: float, settings: Settings, session: requests.Session) -> str | None:
    params = {
        "x": lon,
        "y": lat,
        "benchmark": CENSUS_BENCHMARK,
        "vintage": CENSUS_VINTAGE,
        "format": "json",
    }
    try:
        resp = session.get(CENSUS_COORDS_URL, params=params, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        return _census_name(resp.json().get("result", {}).get("geographies", {}), "Counties")
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        logger.debug("Census county lookup failed for %s,%s: %s", lat, lon, exc)
        return None
