"""Heuristic spam/scam flags for Craigslist rental listings.

These are signals, not verdicts. A flagged listing isn't necessarily fake
and an unflagged one isn't guaranteed real -- the point is to sort your
manual-review effort so the obvious junk sinks to the bottom.

Flags carry weights that add up to `spam_score`, which is the first sort
key in the report. Heavier weights go to signals that are nearly always
scams when present (wire-transfer language, the same canned description
posted under several different listings); lighter ones to things that are
merely suspicious on their own.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .models import Listing

_SCAM_PHRASES = [
    r"western union",
    r"wire transfer",
    r"moneygram",
    r"ship(?:ping)? (?:you |the )?keys",
    r"out of (?:the )?(?:country|state|town) (?:right now|currently|at the moment|for work|on)",
    r"missionary",
    r"before (?:you )?(?:can )?(?:view|see|tour|visit)",
    r"\bzelle\b",
    r"cash ?app",
    r"whatsapp",
    r"google (?:hangouts?|chat|voice)",
    r"\bkindly\b",
    r"god bless",
    r"text (?:me|us) (?:only|directly)",
    r"deposit (?:first|before|prior)",
]
_SCAM_RE = re.compile("|".join(_SCAM_PHRASES), re.IGNORECASE)

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WV", "WI", "WY",
}
# "Garfield, NJ" inside a listing that claims to be in Tacoma: a fake listing
# recycled from another market, a pattern seen live during testing.
_CITY_STATE_RE = re.compile(r"\b[A-Z][A-Za-z.]+,\s?([A-Z]{2})\b")

FLAG_WEIGHTS = {
    "scam-phrasing": 2,
    "duplicate-description": 2,
    "out-of-state-location": 1,
    "duplicate-title": 1,
    "price-far-below-market": 1,
    "very-short-description": 1,
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _out_of_state(text: str) -> bool:
    return any(state in _US_STATES for state in _CITY_STATE_RE.findall(text))


def _price_floor_by_category(listings: list[Listing]) -> dict[str, float]:
    """Half the median price within each category. Rooms are legitimately
    about half the price of apartments, so a single pooled median would flag
    every honest room listing."""
    by_category: dict[str, list[float]] = defaultdict(list)
    for listing in listings:
        if listing.price:
            by_category[listing.category].append(listing.price)
    floors = {}
    for category, prices in by_category.items():
        if len(prices) >= 5:
            prices.sort()
            floors[category] = prices[len(prices) // 2] * 0.5
    return floors


def flag_listings(listings: list[Listing]) -> None:
    """Sets spam_flags / spam_score on every listing in place."""
    floors = _price_floor_by_category(listings)
    title_counts = Counter(_normalize(l.title) for l in listings)
    description_counts = Counter(
        _normalize(l.description)[:150] for l in listings if l.description and len(l.description) >= 60
    )

    for listing in listings:
        flags: list[str] = []
        text = " ".join(filter(None, [listing.title, listing.description]))

        if _SCAM_RE.search(text):
            flags.append("scam-phrasing")
        if listing.description and description_counts[_normalize(listing.description)[:150]] > 1:
            flags.append("duplicate-description")
        if _out_of_state(listing.title):
            flags.append("out-of-state-location")
        if title_counts[_normalize(listing.title)] > 1:
            flags.append("duplicate-title")
        floor = floors.get(listing.category)
        if floor is not None and listing.price is not None and listing.price < floor:
            flags.append("price-far-below-market")
        if listing.details_fetched and len(listing.description or "") < 100:
            flags.append("very-short-description")

        listing.spam_flags = flags
        listing.spam_score = sum(FLAG_WEIGHTS[flag] for flag in flags)
