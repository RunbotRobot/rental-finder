from rental_finder.models import Listing
from rental_finder.room_share_filter import is_occupied_shared_room


def _listing(
    category="roo", title="Room for rent", description="", room_attrs=None,
    source="craigslist", details_fetched=True,
) -> Listing:
    return Listing(
        source=source, source_id="x", url="u", title=title, price=700.0,
        category=category, location_text=None, description=description or None,
        room_attrs=room_attrs or [], details_fetched=details_fetched,
    )


def test_non_craigslist_is_never_excluded():
    listing = _listing(source="rentcast", category="roo", room_attrs=["no private bath"])
    assert is_occupied_shared_room(listing) is False


def test_non_room_category_is_never_excluded():
    listing = _listing(category="apa", description="shared kitchen, roommate wanted")
    assert is_occupied_shared_room(listing) is False


def test_not_yet_detail_fetched_is_kept():
    """Nothing to judge from yet -- keep it until a future run actually
    reads the listing, rather than guess from the title alone."""
    listing = _listing(title="Room for rent", details_fetched=False)
    assert is_occupied_shared_room(listing) is False


def test_plain_private_room_with_private_bath_and_no_other_signal_is_excluded():
    """Regression test for a real, live listing this missed: "private
    room" + "private bath" + a neutral whole-house description, with no
    self-contained language anywhere. That's still a room in someone's
    occupied home, not an ADU -- a private bathroom doesn't make it
    self-contained. Once actually read, a "rooms & shares" listing is an
    occupied shared room BY DEFAULT unless it says otherwise."""
    listing = _listing(
        title="Single Family/2 bedroom, 1 bath single level home!",
        description=(
            "2 bedroom, 1 bath single level home in North Seattle. Kitchen: natural "
            "cherry cabinets. Bathroom: heated stone mosaic floor, pedestal sink and "
            "vintage tub. Garden area, covered outdoor area for entertaining."
        ),
        room_attrs=["private room", "apartment", "private bath"],
    )
    assert is_occupied_shared_room(listing) is True


def test_no_private_bath_attr_is_excluded():
    listing = _listing(room_attrs=["private room", "apartment", "no private bath"])
    assert is_occupied_shared_room(listing) is True


def test_shared_room_attr_is_excluded():
    listing = _listing(room_attrs=["shared room"])
    assert is_occupied_shared_room(listing) is True


def test_roommate_language_with_no_structured_attrs_is_still_excluded():
    listing = _listing(description="Looking for a roommate to share the kitchen and living room.")
    assert is_occupied_shared_room(listing) is True


def test_mother_in_law_suite_is_kept_even_with_no_private_bath_attr():
    """The explicit self-contained signal wins over an ambiguous/shared
    attribute -- e.g. a poster who marked "no private bath" by mistake, or
    a suite with an ensuite the CL form doesn't have a box for."""
    listing = _listing(
        description="Private mother-in-law suite with its own entrance.",
        room_attrs=["no private bath"],
    )
    assert is_occupied_shared_room(listing) is False


def test_adu_is_kept():
    listing = _listing(title="Cozy ADU available now")
    assert is_occupied_shared_room(listing) is False


def test_studio_is_kept():
    listing = _listing(title="Private studio, own entrance")
    assert is_occupied_shared_room(listing) is False


def test_detached_guest_house_is_kept():
    listing = _listing(description="Detached guest house in the backyard, fully private.")
    assert is_occupied_shared_room(listing) is False


def test_in_law_housing_type_attr_is_kept():
    listing = _listing(room_attrs=["private room", "in-law", "no private bath"])
    assert is_occupied_shared_room(listing) is False
