"""Turn the scored, checked listings into something a person reviews.

Ranking, best first:
  1. spam score (clean listings first)
  2. how many buffer tiers it clears, with "unknown" (no street address yet)
     slotted between "clears one tier" and "clears none" -- a listing known
     to be 300 ft from a school ranks below one we simply haven't located
  3. price, cheapest first

Nothing here decides anything; it's ordering for your attention.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .config import Settings
from .models import PRECISION_ADDRESS, Listing


def _map_link(listing: Listing) -> str:
    if listing.latitude is None or listing.longitude is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={listing.latitude}&mlon={listing.longitude}#map=17"


def _clearance_rank(listing: Listing, settings: Settings) -> float:
    num_tiers = len(settings.buffer_tiers_ft)
    if listing.location_precision != PRECISION_ADDRESS:
        return num_tiers - 0.5
    return num_tiers - listing.tiers_cleared(settings.buffer_tiers_ft, settings.facility_types)


def rank_listings(listings: list[Listing], settings: Settings) -> list[Listing]:
    return sorted(
        listings,
        key=lambda l: (
            l.spam_score,
            _clearance_rank(l, settings),
            l.price if l.price is not None else float("inf"),
        ),
    )


def _tier_label(listing: Listing, tier: int, settings: Settings) -> str:
    clears = listing.clears_buffer(tier, settings.facility_types)
    return "unknown" if clears is None else ("yes" if clears else "no")


def write_csv(listings: list[Listing], settings: Settings, out_path: str | Path) -> None:
    fieldnames = (
        ["rank", "new", "first_seen", "posted", "category", "bedrooms", "price", "title", "location",
         "county", "location_precision", "spam_score", "spam_flags"]
        + [f"clears_{tier}ft" for tier in settings.buffer_tiers_ft]
        + [f"nearest_{ftype}_ft" for ftype in settings.facility_types]
        + ["url", "map_link", "description_snippet"]
    )
    with Path(out_path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, listing in enumerate(rank_listings(listings, settings), start=1):
            row = {
                "rank": rank,
                "new": "yes" if listing.is_new else "",
                "first_seen": listing.first_seen or "",
                "posted": (listing.posted_at or "")[:10],
                "category": {"apa": "apartment", "roo": "room"}.get(listing.category, listing.category),
                "bedrooms": listing.bedrooms if listing.bedrooms is not None else "",
                "price": listing.price,
                "title": listing.title,
                "location": listing.best_address or "",
                "county": listing.county or "",
                "location_precision": listing.location_precision,
                "spam_score": listing.spam_score,
                "spam_flags": "; ".join(listing.spam_flags),
                "url": listing.url,
                "map_link": _map_link(listing),
                "description_snippet": (listing.description or "")[:160],
            }
            for tier in settings.buffer_tiers_ft:
                row[f"clears_{tier}ft"] = _tier_label(listing, tier, settings)
            for ftype in settings.facility_types:
                if listing.clearance(ftype, settings.buffer_tiers_ft[0]) is None:
                    row[f"nearest_{ftype}_ft"] = ""
                else:
                    dist = listing.nearest_facility_ft.get(ftype)
                    row[f"nearest_{ftype}_ft"] = f">{max(settings.buffer_tiers_ft)}" if dist is None else round(dist)
            writer.writerow(row)


def summarize(listings: list[Listing], settings: Settings) -> str:
    """The inventory-vs-buffer numbers: how many candidates survive at each
    tier. This is the thing to bring to the conversation with your CCO."""
    clean = [l for l in listings if l.spam_score == 0]
    located = [l for l in clean if l.location_precision == PRECISION_ADDRESS]
    lines = [
        f"{len(listings)} listings in {settings.county} at or under ${settings.max_rent:,.0f}"
        f" ({sum(1 for l in listings if l.is_new)} new since last run)",
        f"  {len(clean)} with no spam flags",
        f"  {len(located)} of those have a street address and were distance-checked",
        f"  {len(clean) - len(located)} need an address from the poster before they can be checked",
        "",
        "Of the distance-checked, clean listings, how many clear EVERY facility type at:",
    ]
    for tier in settings.buffer_tiers_ft:
        n = sum(1 for l in located if l.clears_buffer(tier, settings.facility_types) is True)
        lines.append(f"  {tier:>5} ft: {n}")
    blockers = Counter()
    for l in located:
        for ftype in settings.facility_types:
            if l.clearance(ftype, settings.buffer_tiers_ft[0]) is False:
                blockers[ftype] += 1
    if blockers:
        lines.append("")
        lines.append(f"What's blocking at the tightest tier ({settings.buffer_tiers_ft[0]} ft):")
        for ftype, n in blockers.most_common():
            lines.append(f"  {ftype}: {n} listings")
    return "\n".join(lines)
