"""Tunable settings for the search.

Nothing here is a legal or clinical determination. Buffer distances in
particular are a starting point for a conversation with your CCO, not a
guarantee that a listing clearing these checks will be approved, or that
one flagged as "too close" would actually be rejected.
"""

from dataclasses import dataclass, field


@dataclass
class Settings:
    # Craigslist search
    cl_subdomain: str = "seattle"
    cl_categories: tuple[str, ...] = ("apa", "roo")  # apts/housing, rooms/shared
    # Center search on SeaTac and pull in the rest of King County around it.
    postal_code: str = "98188"
    search_radius_miles: int = 25

    # Affordability
    max_rent: float = 1900.0

    # Compliance buffers (feet) to report side-by-side, since there's no
    # documented rule to target and a tighter buffer sharply shrinks
    # inventory. Seeing the count at each tier is meant to give you and your
    # CCO something concrete to negotiate over, instead of guessing blind.
    buffer_tiers_ft: tuple[int, ...] = (500, 1000, 1320, 2640)  # last two are 1/4 and 1/2 mile

    # Facility types to check proximity against. Keep "childcare" enabled
    # even at looser buffers given the nature of the offense.
    facility_types: tuple[str, ...] = ("school", "park", "childcare")

    # Geocoding
    geocode_user_agent: str = "rental-finder-personal-use (contact: set ME_CONTACT_EMAIL)"

    # Networking politeness — keep this low. This is a single person's
    # personal housing search, not a bulk crawl.
    request_delay_seconds: float = 3.0
    request_timeout_seconds: float = 15.0


DEFAULT_SETTINGS = Settings()
