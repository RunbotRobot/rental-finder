from rental_finder.models import Listing
from rental_finder.spam_filter import flag_listings


def _listing(**kwargs) -> Listing:
    defaults = dict(
        source="craigslist", source_id="1", url="https://example.com/1", title="Cozy 1BR",
        price=1500.0, category="apa", location_text="SeaTac",
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def _market(category: str, base: float, n: int = 6) -> list[Listing]:
    return [_listing(source_id=f"{category}{i}", title=f"Unit {category} {i}", price=base + 10 * i, category=category) for i in range(n)]


def test_flags_scam_phrasing_in_description():
    listing = _listing(description="Kindly reply if interested, I am out of the country for work.")
    flag_listings([listing])
    assert "scam-phrasing" in listing.spam_flags
    assert listing.spam_score >= 2


def test_flags_out_of_state_city_in_title():
    listing = _listing(title="WOW 2 BR/2 BA - Garfield, NJ - home For Rent")
    flag_listings([listing])
    assert "out-of-state-location" in listing.spam_flags


def test_washington_city_in_title_is_fine():
    listing = _listing(title="Nice room in Renton, WA near transit")
    flag_listings([listing])
    assert "out-of-state-location" not in listing.spam_flags


def test_duplicate_description_across_listings():
    text = "Spacious home with hardwood floors, large yard, and a two car garage in a quiet neighborhood."
    a = _listing(source_id="a", title="Home A", description=text)
    b = _listing(source_id="b", title="Home B", description=text)
    flag_listings([a, b])
    assert "duplicate-description" in a.spam_flags and "duplicate-description" in b.spam_flags


def test_price_outlier_is_judged_within_category():
    listings = _market("apa", 1500) + _market("roo", 700)
    cheap_room = _listing(source_id="r", title="Cheap room", price=650.0, category="roo")
    listings.append(cheap_room)
    flag_listings(listings)
    # $650 is far below the apartment median but perfectly normal for a room
    assert "price-far-below-market" not in cheap_room.spam_flags


def test_price_far_below_own_category_is_flagged():
    listings = _market("apa", 1500)
    bait = _listing(source_id="x", title="Too good", price=500.0, category="apa")
    listings.append(bait)
    flag_listings(listings)
    assert "price-far-below-market" in bait.spam_flags


def test_short_description_only_counts_when_details_were_fetched():
    unfetched = _listing(source_id="u", description=None, details_fetched=False)
    fetched = _listing(source_id="f", description="Room.", details_fetched=True)
    flag_listings([unfetched, fetched])
    assert "very-short-description" not in unfetched.spam_flags
    assert "very-short-description" in fetched.spam_flags


def test_clean_listing_has_no_flags():
    listings = _market("apa", 1400)
    flag_listings(listings)
    assert all(l.spam_flags == [] for l in listings)
