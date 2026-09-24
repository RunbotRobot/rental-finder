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


def test_no_description_is_kept():
    """Nothing to judge from yet -- keep it until a future run actually
    reads the listing, rather than guess from the title alone."""
    listing = _listing(title="Room for rent", details_fetched=False)
    assert is_occupied_shared_room(listing) is False


def test_stale_details_fetched_flag_does_not_block_a_real_description():
    """Regression test for a real, live listing this missed: main.py's
    room_attrs backfill resets details_fetched to False on listings that
    already have a perfectly good description from before room_attrs
    existed. Gating on details_fetched instead of description would have
    treated this listing's explicit "Shared spaces: kitchen, 2
    bathrooms..." as "nothing to judge from yet" and kept it, exactly what
    happened live. The description doesn't stop being true just because
    details_fetched was reset for an unrelated reason."""
    listing = _listing(
        title="Furnished bedrooms for rent in SHORELINE for $800 or $850",
        description=(
            "Rooms for rent in Shoreline includes utilities and internet. The avail. "
            "bedrooms (furnished or unfurnished) rent $800 to $850/month/room/person, "
            "72 sq ft or 99 sq ft room. Shared spaces: kitchen, 2 bathrooms, living "
            "rooms upstairs and downstairs, deck and fenced yard."
        ),
        room_attrs=[],
        details_fetched=False,
    )
    assert is_occupied_shared_room(listing) is True


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


def test_roommate_in_title_overrides_studio_even_with_no_description_yet():
    """Regression test for a real, live listing this missed: "Roommate
    Wanted to Share Studio Apartment" -- the bare word "studio" would
    otherwise have kept it as self-contained. Roommate language in the
    title alone is decisive; no need to wait for a description."""
    listing = _listing(
        title="Roommate Wanted to Share Studio Apartment - $800",
        details_fetched=False,
    )
    assert is_occupied_shared_room(listing) is True


def test_own_entrance_and_kitchen_do_not_override_explicit_roommate_language():
    """Regression test for a real, live listing this missed: a room
    described as having "its own entrance, kitchen, laundry and bathroom"
    that in the same breath says that bathroom is shared with 3 people and
    calls them "roommates." A self-contained-sounding room description
    doesn't mean much once the poster says outright you'd have roommates."""
    listing = _listing(
        title="Room in Peaceful Big Home with Jacuzzi and Gym",
        description=(
            "This room is on the bottom level of the home which has its own entrance, "
            "kitchen, laundry and bathroom shared with a total of 3 people. The space "
            "is shared with two other mid 20s-30s wonderful roommates."
        ),
    )
    assert is_occupied_shared_room(listing) is True


def test_kitchenette_alone_no_longer_implies_self_contained():
    """Regression test for a real, live listing this missed: "Shared
    bathroom/kitchenette w/ 1 other" -- "kitchenette" said nothing about
    whether it was private, and the listing explicitly says it's shared."""
    listing = _listing(
        title="Large Room for Rent",
        description=(
            "Large Bedroom ONLY for rent in lower level of house. Private entry. "
            "Shared bathroom/kitchenette w/ 1 other responsible working person."
        ),
        room_attrs=["private room", "house", "no private bath"],
    )
    assert is_occupied_shared_room(listing) is True
