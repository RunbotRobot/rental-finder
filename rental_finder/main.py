"""CLI entrypoint: fetch -> filter -> geocode -> check compliance -> report.

Usage:
    python -m rental_finder.main --out candidates.csv
"""

from __future__ import annotations

import argparse
import logging

import requests

from . import compliance
from .config import DEFAULT_SETTINGS, Settings
from .geocode import geocode
from .report import write_csv
from .spam_filter import flag_listings
from .sources import craigslist


def run(settings: Settings, out_path: str) -> None:
    session = requests.Session()

    logging.info("Fetching Craigslist listings...")
    listings = craigslist.fetch_listings(settings, session)
    logging.info("Fetched %d listings", len(listings))

    flag_listings(listings)

    for listing in listings:
        if listing.location_precision == "exact":
            continue
        address = listing.raw_address_text or listing.neighborhood
        if not address:
            listing.location_precision = "none"
            continue
        coords = geocode(f"{address}, King County, WA", settings, session)
        if coords is None:
            listing.location_precision = "none"
            continue
        listing.latitude, listing.longitude = coords
        listing.location_precision = "geocoded"

    logging.info("Checking facility proximity...")
    compliance.annotate_distances(listings, settings, session)

    write_csv(listings, settings, out_path)
    logging.info("Wrote %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="candidates.csv", help="Output CSV path")
    parser.add_argument("--max-rent", type=float, default=DEFAULT_SETTINGS.max_rent)
    parser.add_argument("--postal", default=DEFAULT_SETTINGS.postal_code)
    parser.add_argument("--radius-miles", type=int, default=DEFAULT_SETTINGS.search_radius_miles)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    settings = Settings(
        max_rent=args.max_rent,
        postal_code=args.postal,
        search_radius_miles=args.radius_miles,
    )
    run(settings, args.out)


if __name__ == "__main__":
    main()
