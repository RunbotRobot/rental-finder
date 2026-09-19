from rental_finder.models import PRECISION_ADDRESS, PRECISION_AREA, Listing, has_street_number, primary_street


def _listing() -> Listing:
    listing = Listing(
        source="craigslist", source_id="1", url="https://example.com/1", title="Unit",
        price=1500.0, category="apa", location_text="123 Main St, SeaTac, WA",
    )
    listing.location_precision = PRECISION_ADDRESS
    return listing


def test_distances_are_never_reported_below_address_precision():
    listing = _listing()
    listing.location_precision = PRECISION_AREA
    listing.nearest_facility_ft = {"school": 5000.0}
    listing.facility_checked = {"school": True}
    assert listing.clearance("school", 500) is None
    assert listing.tiers_cleared((500, 1000), ("school",)) == 0


def test_clears_when_every_type_checked_and_far():
    listing = _listing()
    listing.nearest_facility_ft = {"school": 1200.0, "park": None}
    listing.facility_checked = {"school": True, "park": True}
    assert listing.clears_buffer(1000, ("school", "park")) is True
    assert listing.clears_buffer(1320, ("school", "park")) is False


def test_none_within_max_buffer_means_clear():
    listing = _listing()
    listing.nearest_facility_ft = {"school": None}
    listing.facility_checked = {"school": True}
    assert listing.clearance("school", 2640) is True


def test_unchecked_type_is_unknown_not_pass():
    listing = _listing()
    listing.nearest_facility_ft = {"school": None}  # looks clear...
    listing.facility_checked = {}  # ...but the query never succeeded
    assert listing.clearance("school", 500) is None
    assert listing.clears_buffer(500, ("school",)) is None


def test_confirmed_too_close_beats_unknown():
    listing = _listing()
    listing.nearest_facility_ft = {"school": 200.0}
    listing.facility_checked = {"school": True}
    assert listing.clears_buffer(500, ("school", "park")) is False


def test_tiers_cleared_counts_only_confirmed_passes():
    listing = _listing()
    listing.nearest_facility_ft = {"school": 1100.0, "park": 3000.0}
    listing.facility_checked = {"school": True, "park": True}
    assert listing.tiers_cleared((500, 1000, 1320, 2640), ("school", "park")) == 2


def test_best_address_prefers_full_search_result_address():
    listing = _listing()
    listing.map_address = "123 Main St near 4th Ave"
    assert listing.best_address == "123 Main St, SeaTac, WA"


def test_best_address_uses_map_address_when_search_result_is_area_only():
    listing = _listing()
    listing.location_text = "Kent, WA"
    listing.map_address = "25102 62nd Avenue South near 25102 62nd Avenue South"
    assert listing.best_address == "25102 62nd Avenue South, Kent, WA"


def test_best_address_ignores_cross_street_only_map_address():
    listing = _listing()
    listing.location_text = "Belltown / Downtown Seattle"
    listing.map_address = "4th Ave near Clay St"
    assert listing.best_address == "Belltown / Downtown Seattle"
    assert not has_street_number(listing.best_address)


def test_override_address_wins():
    listing = _listing()
    listing.override_address = "999 Other Rd, Kent, WA"
    assert listing.best_address == "999 Other Rd, Kent, WA"


def test_primary_street_parsing():
    assert primary_street("9029 16th Ave SW near # 300") == "9029 16th Ave SW"
    assert primary_street("2619 5th Avenue") == "2619 5th Avenue"
    assert primary_street(None) is None
