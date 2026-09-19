from rental_finder.models import Listing


def _listing() -> Listing:
    return Listing(
        source="craigslist",
        source_id="1",
        url="https://example.com/1",
        title="Unit",
        price=1500.0,
        neighborhood="SeaTac",
        raw_address_text="SeaTac",
        posted_at=None,
    )


def test_clears_buffer_true_when_all_facilities_clear():
    listing = _listing()
    listing.facility_clearance = {
        "school": {500: True, 1000: True},
        "park": {500: True, 1000: True},
    }
    assert listing.clears_buffer(500, ("school", "park")) is True


def test_clears_buffer_false_when_any_facility_too_close():
    listing = _listing()
    listing.facility_clearance = {
        "school": {500: False, 1000: True},
        "park": {500: True, 1000: True},
    }
    assert listing.clears_buffer(500, ("school", "park")) is False
    assert listing.clears_buffer(1000, ("school", "park")) is True


def test_clears_buffer_unknown_when_unverified_and_nothing_fails():
    listing = _listing()
    listing.facility_clearance = {
        "school": {500: None},
        "park": {500: True},
    }
    assert listing.clears_buffer(500, ("school", "park")) is None


def test_failed_check_never_silently_passes():
    # A False anywhere always wins over an unverified None elsewhere --
    # a confirmed problem should never be masked by a missing check.
    listing = _listing()
    listing.facility_clearance = {
        "school": {500: False},
        "park": {500: None},
    }
    assert listing.clears_buffer(500, ("school", "park")) is False


def test_no_data_at_all_is_unknown_not_pass():
    listing = _listing()
    assert listing.clears_buffer(500, ("school", "park", "childcare")) is None
