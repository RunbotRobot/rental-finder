"""Memory between runs.

You'll run this every day or two for weeks. Without state, every run would
re-fetch every detail page, re-geocode every address, re-query every GIS
layer, and hand you the same 300 listings with no way to tell which ones
are new. This keeps a JSON file of everything expensive we've learned about
each listing, keyed by its Craigslist id, plus when we first saw it.

Distances are cached as raw feet, not as pass/fail per tier, so changing
the buffer tiers in config doesn't invalidate anything.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .models import Listing

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
MAX_AGE_DAYS = 60

# Reserved key for cross-run bookkeeping that isn't a listing (no Craigslist
# or RentCast id starts with "_"). Currently just the RentCast quota gate.
_META_KEY = "_meta"

# Fields restore() copies onto a listing this run's fetch already produced --
# supplementary state a fresh basic search result doesn't carry (geocoding,
# distance checks, detail-page content that may not have been re-fetched this
# run). Never fields the current fetch already set authoritatively: doing so
# would silently freeze that field at whatever the FIRST-ever sighting
# happened to return, even after a source starts supplying something better
# (a price change, a contact email that becomes available) -- restore()
# would keep re-imposing the stale value from that first sighting forever.
_RESTORE_FIELDS = (
    "posted_at",
    "bedrooms",
    "description",
    "map_address",
    "room_attrs",
    "details_fetched",
    "pin_lat",
    "pin_lon",
    "pin_accuracy",
    "latitude",
    "longitude",
    "location_precision",
    "county",
    "nearest_facility_ft",
    "facility_checked",
)

# Superset of _RESTORE_FIELDS: also the fields needed to fully reconstruct a
# listing that wasn't fetched at all this run -- see all_source_listings().
_CACHED_FIELDS = _RESTORE_FIELDS + (
    "source",
    "url",
    "title",
    "price",
    "category",
    "location_text",
    "contact_name",
    "contact_email",
)


class Cache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version") == CACHE_VERSION:
                    self.entries = data.get("listings", {})
            except (OSError, ValueError) as exc:
                logger.warning("Ignoring unreadable cache %s: %s", self.path, exc)

    def restore(self, listing: Listing) -> bool:
        """Copy cached fields onto the listing. Returns False if unseen."""
        entry = self.entries.get(listing.source_id)
        if entry is None:
            return False
        for name in _RESTORE_FIELDS:
            if name in entry:
                setattr(listing, name, entry[name])
        listing.first_seen = entry.get("first_seen")
        listing.is_new = False
        return True

    def all_source_listings(self, source: str) -> list[Listing]:
        """Reconstruct full Listing objects for every cached entry from this
        source. Used when a run skips fetching that source entirely (e.g.
        RentCast's once-a-day quota gate) but the site should still show
        those listings rather than have them vanish until the next fetch."""
        listings = []
        for source_id, entry in self.entries.items():
            if source_id == _META_KEY or entry.get("source") != source:
                continue
            listing = Listing(
                source=entry["source"],
                source_id=source_id,
                url=entry.get("url", ""),
                title=entry.get("title", ""),
                price=entry.get("price"),
                category=entry.get("category", ""),
                location_text=entry.get("location_text"),
                contact_name=entry.get("contact_name"),
                contact_email=entry.get("contact_email"),
            )
            self.restore(listing)
            listings.append(listing)
        return listings

    def geocoded_from(self, listing: Listing) -> str | None:
        entry = self.entries.get(listing.source_id)
        return entry.get("geocoded_from") if entry else None

    def store(self, listing: Listing, geocoded_from: str | None, today: date) -> None:
        entry = {name: getattr(listing, name) for name in _CACHED_FIELDS}
        entry["geocoded_from"] = geocoded_from
        entry["first_seen"] = listing.first_seen or today.isoformat()
        entry["last_seen"] = today.isoformat()
        self.entries[listing.source_id] = entry
        listing.first_seen = entry["first_seen"]

    def prune(self, today: date) -> None:
        cutoff = (today - timedelta(days=MAX_AGE_DAYS)).isoformat()
        self.entries = {
            k: v for k, v in self.entries.items() if k == _META_KEY or v.get("last_seen", "") >= cutoff
        }

    def should_fetch_rentcast(self, today: date) -> bool:
        """RentCast is a paid, quota-limited API queried once per run; this
        run may be one of several the same day (the Action runs every 6
        hours). True at most once per calendar day, so a free-tier budget
        sized for "once a day" isn't quietly burned by run frequency."""
        return self.entries.get(_META_KEY, {}).get("rentcast_fetched_on") != today.isoformat()

    def mark_rentcast_fetched(self, today: date) -> None:
        self.entries.setdefault(_META_KEY, {})["rentcast_fetched_on"] = today.isoformat()

    def save(self) -> None:
        payload = {"version": CACHE_VERSION, "listings": self.entries}
        self.path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
