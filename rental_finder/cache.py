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

_CACHED_FIELDS = (
    "posted_at",
    "bedrooms",
    "description",
    "map_address",
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
        for name in _CACHED_FIELDS:
            if name in entry:
                setattr(listing, name, entry[name])
        listing.first_seen = entry.get("first_seen")
        listing.is_new = False
        return True

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
        self.entries = {k: v for k, v in self.entries.items() if v.get("last_seen", "") >= cutoff}

    def save(self) -> None:
        payload = {"version": CACHE_VERSION, "listings": self.entries}
        self.path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
