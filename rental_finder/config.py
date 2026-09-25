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
    # South of this, drop it -- Kent's southern edge. Chosen deliberately
    # over a looser "Auburn's fine, just not further" line: Auburn (~47.31,
    # further south than Kent) already got an outreach draft before this
    # boundary existed, but the owner picked the strict Kent/Des Moines
    # line anyway, which means Auburn is out going forward too. Applied to
    # listing.latitude, which is set at AREA precision (the CL map pin) as
    # well as ADDRESS precision -- only PRECISION_NONE listings (no
    # latitude at all) skip this check, kept rather than dropped since
    # there's nothing to measure yet.
    min_latitude: float = 47.35

    # Affordability
    max_rent: float = 1900.0
    # A separate, higher cap for manual_listings.txt entries only (see
    # sources/craigslist.py's fetch_manual_listing()). Each one is already a
    # listing the owner personally reviewed and chose to add -- unlike
    # max_rent, which exists to keep an automated, unreviewed search from
    # pulling in things nobody looked at, a manual addition has already had
    # that judgment call made for it. Still a real cap, not unlimited, as a
    # backstop against a wildly-expensive listing slipping through
    # unnoticed if this file ever grows long. Raised from max_rent's $1900
    # after the owner asked to pursue a $2,000 + half-utilities listing;
    # adjust freely if a future one needs more headroom.
    manual_max_rent: float = 2200.0

    # Compliance buffers (feet) to report side-by-side, since there's no
    # single target -- a tighter buffer sharply shrinks inventory, and
    # above the legal floor it's the CCO's discretion, not a fixed rule.
    # Seeing the count at each tier is meant to give you and your CCO
    # something concrete to negotiate over, instead of guessing blind.
    # The first tier is 550, not a round 500 -- the owner's CCO confirmed
    # 550 ft is the actual statutory minimum distance from a school/
    # playground; above that, approval is the CCO's case-by-case call
    # (1000 ft is "much more likely" to be approved, per the CCO, but not
    # a hard requirement -- a listing between 550 and 1000 can still be
    # fine). Don't round this back to 500 -- that was never the real
    # number, just this project's original placeholder tier.
    buffer_tiers_ft: tuple[int, ...] = (550, 1000, 1320, 2640)  # last two are 1/4 and 1/2 mile

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
    # Optional plain-text file, one Craigslist listing URL per line (# for
    # comments), for a listing found directly rather than through the
    # normal search-page scrape -- see sources/craigslist.py's
    # fetch_manual_listing() and main.py's load_manual_listing_urls(). A
    # committed repo file, not something fetched from the Worker each run,
    # since it's edited by a check-in session (like this file), not the
    # owner directly.
    manual_listings_path: str = "manual_listings.txt"

    # RentCast (sources/rentcast.py): a paid structured-listings API, skipped
    # entirely if no key is configured. Centered on the same SeaTac point as
    # the Craigslist search (postal_code 98188) since RentCast searches by
    # lat/lon + radius rather than postal code.
    rentcast_api_key: str | None = None
    rentcast_latitude: float = 47.4435
    rentcast_longitude: float = -122.2960

    # Outreach (email_draft.py, mailer.py, main.py's send gate). Disabled by
    # default -- only an explicit --send-emails flag (used by the scheduled
    # GitHub Action, never a plain local run) allows any email to actually
    # go out, regardless of how many listings clear the gate below.
    send_emails: bool = False
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    # A listing must clear every enabled facility type at this buffer to be
    # auto-sendable; should be one of buffer_tiers_ft. Independent of the
    # tiers shown in the report, which stay untouched by this setting.
    # Lowered from 1000 to 550 (buffer_tiers_ft's new first tier) after the
    # owner confirmed with their CCO that 550 ft is the actual statutory
    # floor, not just this project's original round-number placeholder.
    # The owner explicitly asked for this, understanding what it does and
    # doesn't mean: outreach is not a violation and does not commit to
    # anything -- final approval is still the CCO's case-by-case call once
    # an actual address is in hand, made well before any lease is signed.
    # The realistic downside of contacting a 550-999 ft listing that the
    # CCO later declines is losing a non-refundable application fee, not a
    # supervision violation. Since clearing 1000 ft always also clears 550,
    # this is a strict widening of the auto-send pool, not a replacement --
    # it never makes anything that used to qualify stop qualifying.
    auto_send_buffer_ft: int = 550
    # Local files the Action fetches from the Worker before each run: which
    # listings you've already contacted (so a rerun never double-emails),
    # and your applicant profile (name/contact/disclosure text for the
    # email body -- see email_draft.py).
    emailed_path: str = "emailed.json"
    profile_path: str = "applicant_profile.json"

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
