"""Tells an actual shared room apart from a self-contained unit that
happened to get posted in Craigslist's "rooms & shares" category.

That category ("roo") mixes two very different things: a private bedroom
in someone else's occupied home (shared kitchen/bathroom/common areas --
what most people mean by "room for rent"), and self-contained mother-in-law
suites, ADUs, and studios that some posters file there anyway (the unit is
an extra structure/carve-out on the same lot, so "rooms & shares" can feel
like the closest fit even though nothing is actually shared).

Like spam_filter.py, this is a signal, not a verdict, and it's
deliberately conservative in the same direction as the county filter
(_same_county() in main.py): when the available text and structured
attributes don't clearly say "you'll be sharing common space with someone
else," this KEEPS the listing rather than risk dropping a real
mother-in-law suite/ADU/studio for want of the right keyword. A listing is
only ever excluded on a real signal that it's occupied, shared housing --
Craigslist's own "no private bath" attribute, or explicit language like
"roommate"/"shared kitchen" -- and an explicit self-contained signal (ADU,
in-law, private entrance, ...) always wins over an ambiguous or absent
shared-housing signal.

Only ever applies to source == "craigslist", category == "roo" -- RentCast
has no room-share equivalent, and Craigslist's "apa" (apartments/housing)
category is never a shared room by definition.
"""

from __future__ import annotations

import re

from .models import Listing

_SELF_CONTAINED_RE = re.compile(
    "|".join(
        [
            r"mother[\s-]?in[\s-]?law",
            r"in[\s-]?law suite",
            r"\bmil suite\b",
            r"\badu\b",
            r"accessory dwelling",
            r"(?:private|separate|own) entrance",
            r"(?:own|private) kitchen",
            r"kitchenette",
            r"\bstudio\b",
            r"\bdetached\b",
            r"guest\s?house",
            r"\bcasita\b",
            r"backyard cottage",
            r"carriage house",
            r"basement apartment",
            r"daylight basement",
            r"tiny (?:home|house)",
        ]
    ),
    re.IGNORECASE,
)

_SHARED_HOUSE_RE = re.compile(
    "|".join(
        [
            r"room\s?mate",
            r"house\s?mate",
            r"shared kitchen",
            r"share (?:the |our |my )?kitchen",
            r"shared common",
            r"share (?:the |our |my )?common",
            r"shared bathroom",
            r"share (?:the |our |my )?bath(?:room)?",
            r"shared living",
            r"co-?living",
            r"other tenants?",
            r"\bshared room\b",
            r"share (?:the |our |my )?house\b",
            r"share (?:the |our |my )?home\b",
        ]
    ),
    re.IGNORECASE,
)


def is_occupied_shared_room(listing: Listing) -> bool:
    """True only for a Craigslist "rooms & shares" listing with a real
    signal that you'd be sharing the home with someone else. False (keep
    it) for every other category, and for "roo" listings that are
    ambiguous, self-contained, or not yet detail-fetched -- there's nothing
    to go on yet in that last case, and the county-filter convention this
    project already follows is to keep an unverified listing, not drop it."""
    if listing.source != "craigslist" or listing.category != "roo":
        return False

    text = " ".join(filter(None, [listing.title, listing.description]))
    attrs_text = " ".join(listing.room_attrs)

    if _SELF_CONTAINED_RE.search(text) or "in-law" in attrs_text or "in law" in attrs_text:
        return False

    if "no private bath" in attrs_text or "shared room" in attrs_text:
        return True
    return bool(_SHARED_HOUSE_RE.search(text))
