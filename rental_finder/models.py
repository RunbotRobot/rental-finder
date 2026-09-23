import re
from dataclasses import dataclass, field

# How much we trust a listing's coordinates:
#   "address" -- geocoded from a street address with a house number; distance
#                checks are meaningful at the buffer sizes we care about.
#   "area"    -- only a city/neighborhood name, or a coarse map pin. Good
#                enough to tell which county it's in, NOT good enough to
#                measure feet to a school. Distance checks are skipped rather
#                than reported as fake precision.
#   "none"    -- no usable location at all.
PRECISION_ADDRESS = "address"
PRECISION_AREA = "area"
PRECISION_NONE = "none"

_STREET_NUMBER_RE = re.compile(r"^\s*\d+[A-Za-z]?\s+\S+")


def has_street_number(text: str | None) -> bool:
    """'2619 5th Avenue, Seattle' -> True; 'Belltown / Downtown' -> False."""
    return bool(text) and bool(_STREET_NUMBER_RE.match(text))


def primary_street(map_address: str | None) -> str | None:
    """Craigslist renders a poster's street + cross street as
    '9029 16th Ave SW near # 300' or '4th Ave near Clay St'. Keep the part
    before 'near'; the cross street only confuses a geocoder."""
    if not map_address:
        return None
    return re.split(r"\s+near\s+", map_address, maxsplit=1)[0].strip() or None


@dataclass
class Listing:
    source: str  # "craigslist" or "rentcast"
    source_id: str
    url: str
    title: str
    price: float | None
    category: str  # craigslist category code ("apa"/"roo"), or RentCast's propertyType
    location_text: str | None  # whatever the listing shows: an address, or just "Shoreline"

    posted_at: str | None = None
    bedrooms: int | None = None
    description: str | None = None
    map_address: str | None = None  # street (+ cross street) from the detail page, when given
    override_address: str | None = None  # from address_overrides.csv; always wins
    details_fetched: bool = False

    # Craigslist's own map pin. Verified live to be coarse (neighborhood-ish)
    # for most listings, occasionally plain wrong, so it's only used for the
    # county check -- never for buffer distances.
    pin_lat: float | None = None
    pin_lon: float | None = None
    pin_accuracy: int | None = None

    latitude: float | None = None
    longitude: float | None = None
    location_precision: str = PRECISION_NONE
    county: str | None = None

    first_seen: str | None = None  # ISO date this tool first saw the listing
    is_new: bool = True

    spam_flags: list[str] = field(default_factory=list)
    spam_score: int = 0

    # Filled in by compliance.py.
    # nearest_facility_ft[type]: distance to the nearest facility of that type,
    #   or None if none exists within the largest configured buffer.
    # facility_checked[type]: True only if the query actually succeeded. A
    #   type that isn't marked checked is reported as unknown -- never as a
    #   pass -- no matter what nearest_facility_ft says.
    nearest_facility_ft: dict[str, float | None] = field(default_factory=dict)
    facility_checked: dict[str, bool] = field(default_factory=dict)

    # Contact info for outreach. Craigslist never populates this (see
    # sources/craigslist.py -- there is no real, stable email to send to,
    # only its own JS reply-relay). RentCast listings carry a real agent or
    # office email straight from the provider.
    contact_name: str | None = None
    contact_email: str | None = None

    # Filled in by email_draft.py once a listing is a real candidate.
    draft_subject: str | None = None
    draft_body: str | None = None

    # Outcome of this run's outreach attempt for this listing, if any:
    # None (not attempted), "sent", or a short reason it was held back
    # ("no contact email", "profile incomplete", "already contacted", ...).
    # This is report-only -- send.py and main.py decide and act; this field
    # just carries the result into the CSV/JSON for you to see what happened.
    outreach_result: str | None = None

    @property
    def best_address(self) -> str | None:
        """The most geocodable string we have. An override wins outright.
        The search-result location usually carries city and state, so it's
        preferred when it has a street number; the detail page's map
        address lacks a city, so it borrows the search-result place name
        (or falls back to the state) to keep the geocoder in the right
        town."""
        if self.override_address:
            return self.override_address
        if has_street_number(self.location_text):
            return self.location_text
        street = primary_street(self.map_address)
        if has_street_number(street):
            place = self.location_text if self.location_text else "WA"
            return f"{street}, {place}"
        return self.location_text

    def clearance(self, facility_type: str, buffer_ft: int) -> bool | None:
        if self.location_precision != PRECISION_ADDRESS or not self.facility_checked.get(facility_type):
            return None
        nearest = self.nearest_facility_ft.get(facility_type)
        return True if nearest is None else nearest >= buffer_ft

    def clears_buffer(self, buffer_ft: int, facility_types: tuple[str, ...]) -> bool | None:
        """False if any facility type is confirmed too close, None if any
        facility type couldn't be verified at this tier, True only if every
        facility type was checked and came back clear."""
        results = [self.clearance(ftype, buffer_ft) for ftype in facility_types]
        if any(result is False for result in results):
            return False
        if any(result is None for result in results):
            return None
        return True

    def tiers_cleared(self, tiers: tuple[int, ...], facility_types: tuple[str, ...]) -> int:
        return sum(1 for tier in tiers if self.clears_buffer(tier, facility_types) is True)
