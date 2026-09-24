from rental_finder.models import Listing
from rental_finder.senior_housing_filter import is_age_restricted


def _listing(title="Nice apartment", description="", source="craigslist") -> Listing:
    return Listing(
        source=source, source_id="x", url="u", title=title, price=1000.0,
        category="apa", location_text=None, description=description or None,
    )


def test_ordinary_listing_is_not_age_restricted():
    listing = _listing(title="Spacious 1 bed, walk to light rail")
    assert is_age_restricted(listing) is False


def test_55_plus_in_title_is_excluded():
    listing = _listing(title="Ardea Senior Apartments -- 55+ community, first look open house")
    assert is_age_restricted(listing) is True


def test_62_and_better_in_description_is_excluded():
    listing = _listing(description="Community is for those 62 and better.")
    assert is_age_restricted(listing) is True


def test_senior_living_phrase_is_excluded():
    listing = _listing(description="Welcome to our senior living community in Federal Way.")
    assert is_age_restricted(listing) is True


def test_independent_living_is_excluded():
    listing = _listing(title="Independent Living apartments now leasing")
    assert is_age_restricted(listing) is True


def test_applies_to_rentcast_too():
    listing = _listing(source="rentcast", title="Retirement community, 1BR available")
    assert is_age_restricted(listing) is True


def test_not_yet_detail_fetched_still_checked_from_title_alone():
    listing = _listing(title="Senior Community -- 55+ only", description="")
    assert is_age_restricted(listing) is True
