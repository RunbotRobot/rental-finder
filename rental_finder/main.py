"""CLI entrypoint.

    python -m rental_finder.main --out candidates.csv -v

Pipeline: fetch search results -> drop over-budget -> restore cache ->
apply address overrides -> fetch detail pages (capped) -> spam flags ->
geocode -> drop out-of-county -> distance checks -> save cache -> CSV +
summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from . import compliance
from .cache import Cache
from .config import DEFAULT_SETTINGS, Settings
from .geocode import county_for_point, geocode_address, has_street_number, is_plausible
from .models import PRECISION_ADDRESS, PRECISION_AREA, PRECISION_NONE, Listing
from .report import summarize, to_json, write_csv
from .sources import craigslist
from .spam_filter import flag_listings

logger = logging.getLogger(__name__)


def load_overrides(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {
            row["source_id"].strip(): row["address"].strip()
            for row in csv.DictReader(f)
            if row.get("source_id") and row.get("address")
        }


def locate(listing: Listing, cache: Cache, settings: Settings, session: requests.Session) -> str | None:
    """Set coordinates, precision, and county. Returns the address string
    the coordinates came from (for the cache), or None."""
    address = listing.best_address
    if has_street_number(address):
        if listing.location_precision == PRECISION_ADDRESS and cache.geocoded_from(listing) == address:
            return address
        result = geocode_address(address, settings, session)
        if result is not None and not is_plausible(result, listing.pin_lat, listing.pin_lon):
            logger.info("Rejecting implausible geocode of %r -> %s, %s (%s)", address, result.county, result.state, listing.url)
            result = None
        if result is not None:
            listing.latitude, listing.longitude = result.latitude, result.longitude
            listing.county = result.county
            listing.location_precision = PRECISION_ADDRESS
            listing.nearest_facility_ft, listing.facility_checked = {}, {}
            return address
        logger.info("Could not geocode %r (%s)", address, listing.url)

    # Below address precision, any distances from an earlier address are stale.
    listing.nearest_facility_ft, listing.facility_checked = {}, {}
    if listing.location_precision == PRECISION_AREA and listing.county:
        return None
    if listing.pin_lat is not None and listing.pin_lon is not None:
        listing.latitude, listing.longitude = listing.pin_lat, listing.pin_lon
        listing.location_precision = PRECISION_AREA
        listing.county = county_for_point(listing.pin_lat, listing.pin_lon, settings, session)
    else:
        listing.latitude = listing.longitude = None
        listing.location_precision = PRECISION_NONE
    return None


def run(settings: Settings, out_path: str, limit: int = 0, json_path: str | None = None) -> None:
    session = requests.Session()
    session.headers["User-Agent"] = settings.user_agent
    today = date.today()

    listings = craigslist.fetch_listings(settings, session)
    listings = [l for l in listings if l.price is not None and l.price <= settings.max_rent]
    logger.info("%d listings within budget", len(listings))
    if limit:
        listings = listings[:limit]

    cache = Cache(settings.cache_path)
    for listing in listings:
        cache.restore(listing)

    overrides = load_overrides(settings.overrides_path)
    for listing in listings:
        listing.override_address = overrides.get(listing.source_id)

    if settings.fetch_details:
        # Listings that already show a street address are the actionable
        # ones, so their detail pages (description, post date) come first.
        todo = sorted(
            (l for l in listings if not l.details_fetched),
            key=lambda l: 0 if has_street_number(l.location_text) else 1,
        )
        logger.info("Fetching detail pages for %d listings (cap %d)", len(todo), settings.max_detail_fetches)
        craigslist.fetch_details(todo, settings, session)

    flag_listings(listings)

    geocoded_from: dict[str, str | None] = {}
    for listing in listings:
        geocoded_from[listing.source_id] = locate(listing, cache, settings, session)

    in_county = [l for l in listings if not l.county or l.county == settings.county]
    for listing in listings:
        if listing.county and listing.county != settings.county:
            logger.info("Dropping %s (%s): %s", listing.county, listing.best_address or "no location", listing.url)
    logger.info("%d listings in %s (dropped %d confirmed elsewhere)", len(in_county), settings.county, len(listings) - len(in_county))

    compliance.annotate_distances(in_county, settings, session)

    for listing in listings:
        cache.store(listing, geocoded_from[listing.source_id], today)
    cache.prune(today)
    cache.save()

    write_csv(in_county, settings, out_path)
    if json_path:
        payload = to_json(in_county, settings, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        Path(json_path).write_text(json.dumps(payload), encoding="utf-8")
    print(summarize(in_county, settings))
    print(f"\nWrote {out_path}" + (f" and {json_path}" if json_path else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-screen King County rentals for affordability and facility proximity.")
    parser.add_argument("--out", default="candidates.csv", help="Output CSV path")
    parser.add_argument("--json", default=None, help="Also write the web UI's data.json here")
    parser.add_argument("--max-rent", type=float, default=DEFAULT_SETTINGS.max_rent)
    parser.add_argument("--postal", default=DEFAULT_SETTINGS.postal_code)
    parser.add_argument("--radius-miles", type=int, default=DEFAULT_SETTINGS.search_radius_miles)
    parser.add_argument("--max-detail-fetches", type=int, default=DEFAULT_SETTINGS.max_detail_fetches)
    parser.add_argument("--no-details", action="store_true", help="Skip fetching listing pages this run")
    parser.add_argument("--cache", default=DEFAULT_SETTINGS.cache_path)
    parser.add_argument("--overrides", default=DEFAULT_SETTINGS.overrides_path)
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N listings (for a quick test run)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    settings = Settings(
        max_rent=args.max_rent,
        postal_code=args.postal,
        search_radius_miles=args.radius_miles,
        max_detail_fetches=args.max_detail_fetches,
        fetch_details=not args.no_details,
        cache_path=args.cache,
        overrides_path=args.overrides,
    )
    run(settings, args.out, limit=args.limit, json_path=args.json)


if __name__ == "__main__":
    main()
