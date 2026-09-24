"""Tells an actual shared room apart from a self-contained unit that
happened to get posted in Craigslist's "rooms & shares" category.

That category ("roo") mixes two very different things: a private bedroom
in someone else's occupied home (shared kitchen/common areas -- what most
people mean by "room for rent"), and self-contained mother-in-law suites,
ADUs, and studios that some posters file there anyway (the unit is an
extra structure/carve-out on the same lot, so "rooms & shares" can feel
like the closest fit even though nothing is actually shared).

The rule: once a "roo" listing has actually been read (detail page
fetched), it's an occupied shared room BY DEFAULT -- that's what the
category means -- unless the listing itself says otherwise (an explicit
self-contained signal: ADU, in-law, private entrance, studio, detached,
...). A "private bath" attribute or an otherwise-neutral description of
the house is not that signal on its own: renting a bedroom with its own
bathroom in someone else's occupied home is still renting a room, not a
self-contained unit (confirmed against a real, live listing: "private
room" + "private bath," a whole-house-sounding description, and NO
self-contained language of any kind -- that's a room, not an ADU, and
should be excluded).

Not yet detail-fetched (no description, no room_attrs) is the one case
this doesn't judge: there's nothing to go on yet, so it's kept until a
future run actually reads it -- the same "don't drop what you haven't
verified" instinct as the county filter, but for "haven't looked" rather
than "looked and it's unclear."

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


def is_occupied_shared_room(listing: Listing) -> bool:
    """True for a Craigslist "rooms & shares" listing that's been read and
    doesn't say it's self-contained -- an occupied shared room, by default,
    since that's what the category means. False for every other category,
    and for a "roo" listing not yet detail-fetched (nothing to judge from
    yet) or one with an explicit self-contained signal."""
    if listing.source != "craigslist" or listing.category != "roo":
        return False
    if not listing.details_fetched:
        return False

    text = " ".join(filter(None, [listing.title, listing.description]))
    attrs_text = " ".join(listing.room_attrs)

    if _SELF_CONTAINED_RE.search(text) or "in-law" in attrs_text or "in law" in attrs_text:
        return False
    return True
