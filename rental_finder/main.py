"""CLI entrypoint.

    python -m rental_finder.main --out candidates.csv -v

Pipeline: fetch search results (Craigslist + RentCast) -> drop over-budget
-> restore cache -> apply address overrides -> fetch detail pages (capped)
-> spam flags -> drop occupied shared rooms (keeping mother-in-law
suites/ADUs/studios) -> geocode/locate -> drop out-of-county -> distance
checks -> draft + (maybe) send outreach emails -> save cache -> CSV + JSON
+ summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import requests

import os

from . import compliance, outreach
from .applicant_profile import load_profile
from .cache import Cache
from .config import DEFAULT_SETTINGS, Settings
from .geocode import county_for_point, geocode_address, has_street_number, is_plausible
from .models import PRECISION_ADDRESS, PRECISION_AREA, PRECISION_NONE, Listing
from .report import summarize, to_json, write_csv
from .room_share_filter import is_occupied_shared_room
from .sources import craigslist, rentcast
from .spam_filter import flag_listings

logger = logging.getLogger(__name__)


def _same_county(county: str | None, expected: str) -> bool:
    """Lenient on purpose: RentCast's county field format isn't documented
    with an example value, so this doesn't assume it matches the Census
    geocoder's "King County" exactly -- "King", "KING", "King Co." all pass."""
    if not county:
        return True  # unknown -- keep it rather than risk dropping a real match
    bare_expected = expected.replace(" County", "").strip().lower()
    return bare_expected in county.lower()


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


def load_emailed_ids(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable emailed-ids file %s: %s", path, exc)
        return set()


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


def run(
    settings: Settings,
    out_path: str,
    limit: int = 0,
    json_path: str | None = None,
    emailed_out_path: str | None = None,
    force_rentcast: bool = False,
) -> None:
    session = requests.Session()
    session.headers["User-Agent"] = settings.user_agent
    today = date.today()
    cache = Cache(settings.cache_path)

    listings = craigslist.fetch_listings(settings, session)
    if settings.rentcast_api_key:
        if force_rentcast or cache.should_fetch_rentcast(today):
            ok, rentcast_listings = rentcast.fetch_listings(settings, session)
            listings += rentcast_listings
            if ok:
                cache.mark_rentcast_fetched(today)
            else:
                logger.warning("RentCast fetch failed -- not counting today's quota slot as used; will retry next run")
        else:
            stale = cache.all_source_listings("rentcast")
            logger.info(
                "Skipping RentCast fetch this run (quota gate, already fetched today) -- "
                "reusing %d previously-fetched RentCast listing(s)",
                len(stale),
            )
            listings += stale
    listings = [l for l in listings if l.price is not None and l.price <= settings.max_rent]
    logger.info("%d listings within budget", len(listings))
    if limit:
        listings = listings[:limit]

    for listing in listings:
        cache.restore(listing)

    # room_share_filter.py needs Craigslist's structured room_attrs, which
    # didn't exist before that feature shipped. A "roo" listing already
    # marked details_fetched from before then has an empty room_attrs
    # that's indistinguishable from "this listing genuinely has no
    # attribute badges" (real ones always have a few) -- so re-queue those
    # for one more detail fetch rather than leave them impossible to
    # classify forever. Sorted AHEAD of brand-new listings (see below): a
    # backfill candidate already cleared geocoding/compliance once and is
    # known-active, so it's worth finishing over a listing that's merely
    # new (and costs nothing to leave for next run, since it stays "new").
    # An earlier version of this sorted backfill last, which meant a
    # steady stream of new listings could starve the backfill queue
    # indefinitely -- confirmed live: a run with 497 total needing details
    # and a 249-listing backfill queue spent its entire 150-listing cap on
    # new listings and backfilled none.
    needs_room_attrs_backfill = {
        l.source_id
        for l in listings
        if l.source == "craigslist" and l.category == "roo" and l.details_fetched and not l.room_attrs
    }
    if needs_room_attrs_backfill:
        logger.info("Re-queuing %d pre-existing room listing(s) to backfill room_attrs", len(needs_room_attrs_backfill))
        for listing in listings:
            if listing.source_id in needs_room_attrs_backfill:
                listing.details_fetched = False

    overrides = load_overrides(settings.overrides_path)
    for listing in listings:
        listing.override_address = overrides.get(listing.source_id)

    if settings.fetch_details:
        # room_attrs backfill first (see above), then listings that already
        # show a street address -- the actionable ones -- before the rest.
        todo = sorted(
            (l for l in listings if not l.details_fetched),
            key=lambda l: (l.source_id not in needs_room_attrs_backfill, 0 if has_street_number(l.location_text) else 1),
        )
        logger.info("Fetching detail pages for %d listings (cap %d)", len(todo), settings.max_detail_fetches)
        craigslist.fetch_details(todo, settings, session)

    flag_listings(listings)

    shared_room_ids = {l.source_id for l in listings if is_occupied_shared_room(l)}
    if shared_room_ids:
        listings = [l for l in listings if l.source_id not in shared_room_ids]
        logger.info(
            "Dropping %d occupied shared-room listing(s) (mother-in-law suites/ADUs/studios kept -- see room_share_filter.py)",
            len(shared_room_ids),
        )

    geocoded_from: dict[str, str | None] = {}
    for listing in listings:
        # RentCast already supplies real coordinates -- nothing to geocode.
        geocoded_from[listing.source_id] = None if listing.latitude is not None else locate(listing, cache, settings, session)

    in_county = [l for l in listings if _same_county(l.county, settings.county)]
    for listing in listings:
        if not _same_county(listing.county, settings.county):
            logger.info("Dropping %s (%s): %s", listing.county, listing.best_address or "no location", listing.url)
    logger.info("%d listings in %s (dropped %d confirmed elsewhere)", len(in_county), settings.county, len(listings) - len(in_county))

    compliance.annotate_distances(in_county, settings, session)

    profile = load_profile(settings.profile_path)
    already_emailed = load_emailed_ids(settings.emailed_path)
    newly_emailed = outreach.process(in_county, settings, profile, already_emailed)
    if newly_emailed:
        logger.info("Sent %d new outreach email(s)", len(newly_emailed))
    if emailed_out_path:
        Path(emailed_out_path).write_text(json.dumps(sorted(newly_emailed)), encoding="utf-8")

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
    parser.add_argument("--profile", default=DEFAULT_SETTINGS.profile_path)
    parser.add_argument("--emailed", default=DEFAULT_SETTINGS.emailed_path, help="Path to the list of already-emailed listing ids")
    parser.add_argument("--emailed-out", default=None, help="Write newly-emailed listing ids here, for the caller to persist")
    parser.add_argument(
        "--send-emails",
        action="store_true",
        help="Actually send outreach emails via this code path, for listings that clear the gate. "
        "The scheduled Action never passes this -- outreach is drafted and sent by a Claude session "
        "instead (see README). This flag exists for local testing of the Gmail-SMTP send path only.",
    )
    parser.add_argument("--auto-send-buffer-ft", type=int, default=DEFAULT_SETTINGS.auto_send_buffer_ft)
    parser.add_argument(
        "--force-rentcast",
        action="store_true",
        help="Fetch from RentCast even if already fetched today. RentCast is on a paid, "
        "quota-limited free tier sized for once a day; only override this for deliberate testing.",
    )
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
        profile_path=args.profile,
        emailed_path=args.emailed,
        send_emails=args.send_emails,
        auto_send_buffer_ft=args.auto_send_buffer_ft,
        rentcast_api_key=os.environ.get("RENTCAST_API_KEY") or None,
        gmail_address=os.environ.get("GMAIL_ADDRESS") or None,
        gmail_app_password=os.environ.get("GMAIL_APP_PASSWORD") or None,
    )
    run(
        settings,
        args.out,
        limit=args.limit,
        json_path=args.json,
        emailed_out_path=args.emailed_out,
        force_rentcast=args.force_rentcast,
    )


if __name__ == "__main__":
    main()
