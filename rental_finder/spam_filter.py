"""Heuristic spam/scam flags for Craigslist rental listings.

These are signals, not verdicts. A listing with flags isn't necessarily
fake, and one with none isn't guaranteed real — the goal is to sort your
manual-review effort, not to auto-reject anything.
"""

from __future__ import annotations

import re
from collections import Counter

from .models import Listing

_SCAM_PHRASES = [
    r"western union",
    r"wire transfer",
    r"moneygram",
    r"ship(?:ping)? (?:you |the )?(?:the )?keys",
    r"out of (?:the )?(?:country|state) (?:right now|currently)",
    r"missionary",
    r"before you (?:can )?(?:view|see) the (?:house|property|apartment)",
    r"zelle",
    r"cash app",
    r"whatsapp",
    r"google hangout",
    r"text me (?:only|directly) at",
]
_SCAM_RE = re.compile("|".join(_SCAM_PHRASES), re.IGNORECASE)

_VAGUE_PHRASES = [
    r"safe and clean neighborhood",
    r"first,? last,? and deposit",
    r"available immediately",
]
_VAGUE_RE = re.compile("|".join(_VAGUE_PHRASES), re.IGNORECASE)


def _price_is_outlier(price: float | None, all_prices: list[float]) -> bool:
    if price is None or len(all_prices) < 5:
        return False
    sorted_prices = sorted(all_prices)
    median = sorted_prices[len(sorted_prices) // 2]
    return price < median * 0.5


def flag_listings(listings: list[Listing], descriptions: dict[str, str] | None = None) -> None:
    """Mutates each listing's spam_flags/spam_score in place.

    `descriptions` maps source_id -> full listing body text, for callers that
    fetched the detail page. If not provided, only title/metadata heuristics run.
    """
    descriptions = descriptions or {}
    all_prices = [l.price for l in listings if l.price is not None]

    title_price_counts = Counter((l.title.strip().lower(), l.price) for l in listings)

    for listing in listings:
        flags: list[str] = []
        text = " ".join(
            filter(None, [listing.title, descriptions.get(listing.source_id, "")])
        )

        if _SCAM_RE.search(text):
            flags.append("scam-phrasing")
        if _VAGUE_RE.search(text):
            flags.append("generic-boilerplate")
        if title_price_counts[(listing.title.strip().lower(), listing.price)] > 1:
            flags.append("duplicate-posting")
        if _price_is_outlier(listing.price, all_prices):
            flags.append("price-too-low-for-market")
        if not listing.raw_address_text and listing.location_precision == "none":
            flags.append("no-location-info")

        listing.spam_flags = flags
        listing.spam_score = len(flags)
