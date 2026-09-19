"""Tunable settings for the search.

Nothing here is a legal or clinical determination. Buffer distances in
particular are a starting point for a conversation with your CCO, not a
guarantee that a listing clearing these checks will be approved, or that
one flagged as "too close" would actually be rejected.
"""

from dataclasses import dataclass


@dataclass
class Settings:
    # Craigslist search
    cl_subdomain: str = "seattle"
    cl_categories: tuple[str, ...] = ("apa", "roo")  # apts/housing, rooms/shared
    # Center the search on SeaTac and pull in the rest of King County around
    # it. The radius spills into Pierce and Snohomish counties; listings
    # confirmed to be outside `county` are dropped after geocoding.
    postal_code: str = "98188"
    search_radius_miles: int = 25
    county: str = "King County"

    # Affordability
    max_rent: float = 1900.0

    # Compliance buffers (feet) to report side-by-side, since there's no
    # documented rule to target and a tighter buffer sharply shrinks
    # inventory. Seeing the count at each tier is meant to give you and your
    # CCO something concrete to negotiate over, instead of guessing blind.
    buffer_tiers_ft: tuple[int, ...] = (500, 1000, 1320, 2640)  # last two are 1/4 and 1/2 mile

    # Facility types to check proximity against. See compliance.py for what
    # each one covers -- and, just as important, what it doesn't.
    facility_types: tuple[str, ...] = ("school", "park", "childcare")

    # Listing detail pages carry the full description (needed for real
    # spam detection), the post date, and sometimes a street address. Each
    # one is a separate request to Craigslist, so the count per run is
    # capped; results are cached, so later runs only fetch new listings.
    fetch_details: bool = True
    max_detail_fetches: int = 150

    # Local state between runs: which listings you've already seen, plus
    # cached geocoding and distance results so re-runs don't re-hit APIs.
    cache_path: str = "cache.json"
    # Optional CSV of `source_id,address` for addresses you got from a poster
    # after contacting them; these take priority over the listing's own text.
    overrides_path: str = "address_overrides.csv"

    # Identify yourself honestly to the services you're querying (Nominatim's
    # usage policy requires it). This worked fine live against Craigslist,
    # Census, and King County GIS.
    user_agent: str = "rental-finder (personal housing search; not a crawler)"

    # Networking politeness -- keep this high. This is one person's personal
    # housing search, not a bulk crawl, and Craigslist in particular will
    # block traffic that looks like one.
    request_delay_seconds: float = 3.0
    request_timeout_seconds: float = 20.0


DEFAULT_SETTINGS = Settings()
