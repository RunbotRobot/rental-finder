from rental_finder.models import Listing
from rental_finder.room_share_filter import is_occupied_shared_room


def _listing(category="roo", title="Room for rent", description="", room_attrs=None, source="craigslist") -> Listing:
    return Listing(
        source=source, source_id="x", url="u", title=title, price=700.0,
        category=category, location_text=None, description=description or None,
        room_attrs=room_attrs or [],
    )


def test_non_craigslist_is_never_excluded():
    listing = _listing(source="rentcast", category="roo", room_attrs=["no private bath"])
    assert is_occupied_shared_room(listing) is False


def test_non_room_category_is_never_excluded():
    listing = _listing(category="apa", description="shared kitchen, roommate wanted")
    assert is_occupied_shared_room(listing) is False


def test_no_private_bath_attr_is_excluded():
    listing = _listing(room_attrs=["private room", "apartment", "no private bath"])
    assert is_occupied_shared_room(listing) is True


def test_explicit_shared_room_attr_is_excluded():
    listing = _listing(room_attrs=["shared room"])
    assert is_occupied_shared_room(listing) is True


def test_roommate_language_in_description_is_excluded():
    listing = _listing(description="Looking for a roommate to share the kitchen and living room.")
    assert is_occupied_shared_room(listing) is True


def test_plain_private_room_with_no_other_signal_is_kept():
    """Ambiguous: a private room + private bath, no explicit shared-house
    language. Keep it -- same "uncertain means keep" convention as the
    county filter."""
    listing = _listing(room_attrs=["private room", "apartment", "private bath"])
    assert is_occupied_shared_room(listing) is False


def test_not_yet_detail_fetched_is_kept():
    listing = _listing(title="Room for rent", description="", room_attrs=[])
    assert is_occupied_shared_room(listing) is False


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
    listing = _listing(title="Cozy ADU available now", description="")
    assert is_occupied_shared_room(listing) is False


def test_studio_is_kept():
    listing = _listing(title="Private studio, own entrance", description="")
    assert is_occupied_shared_room(listing) is False


def test_detached_guest_house_is_kept():
    listing = _listing(description="Detached guest house in the backyard, fully private.")
    assert is_occupied_shared_room(listing) is False


def test_in_law_housing_type_attr_is_kept():
    listing = _listing(room_attrs=["private room", "in-law", "no private bath"])
    assert is_occupied_shared_room(listing) is False
