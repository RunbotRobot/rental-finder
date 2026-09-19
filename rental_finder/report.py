"""Turn a scored/filtered list of Listings into a human-reviewable report.

Deliberately does not auto-reject or auto-contact anything — output is a
ranked list for a person to look at, per the plan to review every candidate
manually before it goes anywhere near a CCO or a landlord.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import Settings
from .models import Listing


def _map_link(listing: Listing) -> str:
    if listing.latitude is None or listing.longitude is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={listing.latitude}&mlon={listing.longitude}#map=17"


def rank_listings(listings: list[Listing], settings: Settings) -> list[Listing]:
    def sort_key(listing: Listing):
        clears_tightest = listing.clears_buffer(settings.buffer_tiers_ft[0], settings.facility_types)
        return (
            listing.spam_score,
            0 if clears_tightest else (1 if clears_tightest is None else 2),
            -(listing.price or 0),
        )

    return sorted(listings, key=sort_key)


def write_csv(listings: list[Listing], settings: Settings, out_path: str | Path) -> None:
    out_path = Path(out_path)
    fieldnames = [
        "title",
        "price",
        "neighborhood",
        "url",
        "location_precision",
        "map_link",
        "spam_score",
        "spam_flags",
    ] + [f"clears_{ft}ft" for ft in settings.buffer_tiers_ft] + [
        f"nearest_{f}_ft" for f in settings.facility_types
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for listing in rank_listings(listings, settings):
            row = {
                "title": listing.title,
                "price": listing.price,
                "neighborhood": listing.neighborhood,
                "url": listing.url,
                "location_precision": listing.location_precision,
                "map_link": _map_link(listing),
                "spam_score": listing.spam_score,
                "spam_flags": "; ".join(listing.spam_flags),
            }
            for tier in settings.buffer_tiers_ft:
                clears = listing.clears_buffer(tier, settings.facility_types)
                row[f"clears_{tier}ft"] = "unknown" if clears is None else clears
            for ftype in settings.facility_types:
                dist = listing.nearest_facility_ft.get(ftype)
                row[f"nearest_{ftype}_ft"] = "" if dist is None else round(dist)
            writer.writerow(row)
