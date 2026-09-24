"""Drops age-restricted (55+/62+/senior) housing.

Unlike room_share_filter.py, this needs no "haven't looked yet" carve-out:
age restrictions are almost always advertised right in the title (posters
want to attract qualifying renters, not waste anyone's time), so this
applies from the moment a listing is seen, off whatever text is available
-- title alone for a listing not yet detail-fetched, title + description
once it has been. It only ever excludes on an explicit signal; there's no
default-exclude side to this one; a listing with no such language is
simply not age-restricted as far as this tool can tell.

Applies to both sources -- RentCast's aggregated listings can include
senior communities same as Craigslist's.
"""

from __future__ import annotations

import re

from .models import Listing

_SENIOR_RE = re.compile(
    "|".join(
        [
            r"\b55\s*\+",
            r"\b55\s*(?:and\s*)?(?:better|older|up)\b",
            r"\b62\s*\+",
            r"\b62\s*(?:and\s*)?(?:better|older|up)\b",
            r"senior\s*(?:living|community|communities|housing|apartments?|residence)",
            r"independent living",
            r"active adult community",
            r"age[\s-]?restricted",
            r"age[\s-]?qualified",
            r"retirement community",
        ]
    ),
    re.IGNORECASE,
)


def is_age_restricted(listing: Listing) -> bool:
    """True if the listing's own text advertises an age restriction (55+,
    62+, "senior living", ...). Never a guess -- only ever True on an
    explicit match."""
    text = " ".join(filter(None, [listing.title, listing.description]))
    return bool(_SENIOR_RE.search(text))
