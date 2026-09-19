from rental_finder.models import Listing
from rental_finder.spam_filter import flag_listings


def _listing(**kwargs) -> Listing:
    defaults = dict(
        source="craigslist",
        source_id="1",
        url="https://seattle.craigslist.org/x/1.html",
        title="Cozy 1BR",
        price=1500.0,
        neighborhood="SeaTac",
        raw_address_text="SeaTac",
        posted_at=None,
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def test_flags_scam_phrasing():
    listing = _listing(title="Great deal, wire transfer deposit via Western Union")
    flag_listings([listing])
    assert "scam-phrasing" in listing.spam_flags


def test_flags_duplicate_postings():
    a = _listing(source_id="1", title="Same Title", price=1200.0)
    b = _listing(source_id="2", title="Same Title", price=1200.0)
    flag_listings([a, b])
    assert "duplicate-posting" in a.spam_flags
    assert "duplicate-posting" in b.spam_flags


def test_flags_no_location_info():
    listing = _listing(raw_address_text=None)
    listing.location_precision = "none"
    flag_listings([listing])
    assert "no-location-info" in listing.spam_flags


def test_clean_listing_has_no_flags():
    listings = [_listing(source_id=str(i), title=f"Unit {i}", price=1400.0 + i) for i in range(6)]
    flag_listings(listings)
    assert listings[0].spam_flags == []
