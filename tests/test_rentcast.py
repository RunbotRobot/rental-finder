from rental_finder.config import Settings
from rental_finder.models import PRECISION_ADDRESS
from rental_finder.sources.rentcast import _to_listing, fetch_listings

SAMPLE_ITEM = {
    "id": "1234-abcd",
    "formattedAddress": "8500 20th Ave NE, Seattle, WA 98115",
    "latitude": 47.6903,
    "longitude": -122.3068,
    "county": "King",
    "price": 1795,
    "propertyType": "Apartment",
    "bedrooms": 1,
    "listedDate": "2026-09-01",
    "listingAgent": {"name": "Jane Agent", "email": "jane@example-realty.com"},
    "listingOffice": {"name": "Example Realty", "email": "office@example-realty.com"},
}


def test_to_listing_maps_core_fields():
    listing = _to_listing(SAMPLE_ITEM)
    assert listing.source == "rentcast"
    assert listing.source_id == "1234-abcd"
    assert listing.price == 1795.0
    assert listing.location_precision == PRECISION_ADDRESS
    assert (listing.latitude, listing.longitude) == (47.6903, -122.3068)
    assert listing.county == "King"
    assert listing.bedrooms == 1
    assert listing.details_fetched is True


def test_prefers_listing_agent_email_over_office():
    listing = _to_listing(SAMPLE_ITEM)
    assert listing.contact_name == "Jane Agent"
    assert listing.contact_email == "jane@example-realty.com"


def test_falls_back_to_office_email_when_agent_has_none():
    item = dict(SAMPLE_ITEM, listingAgent={"name": "Jane Agent"})
    listing = _to_listing(item)
    assert listing.contact_email == "office@example-realty.com"


def test_no_contact_at_all_is_fine():
    item = dict(SAMPLE_ITEM, listingAgent={}, listingOffice={})
    listing = _to_listing(item)
    assert listing.contact_email is None


def test_missing_required_fields_is_skipped():
    assert _to_listing(dict(SAMPLE_ITEM, latitude=None)) is None
    assert _to_listing(dict(SAMPLE_ITEM, price=None)) is None
    assert _to_listing(dict(SAMPLE_ITEM, formattedAddress=None)) is None


def test_fetch_skipped_without_api_key():
    settings = Settings(rentcast_api_key=None)
    assert fetch_listings(settings, session=None) == []
