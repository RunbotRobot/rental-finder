from datetime import date, timedelta

from rental_finder.cache import Cache
from rental_finder.models import PRECISION_ADDRESS, Listing


def _listing(source_id="1") -> Listing:
    return Listing(
        source="craigslist", source_id=source_id, url="u", title="t", price=1000.0,
        category="apa", location_text="123 Main St, Kent, WA",
    )


def test_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    listing = _listing()
    listing.latitude, listing.longitude = 47.4, -122.2
    listing.location_precision = PRECISION_ADDRESS
    listing.county = "King County"
    listing.nearest_facility_ft = {"school": 812.5, "park": None}
    listing.facility_checked = {"school": True, "park": True}
    listing.description = "hello"
    listing.details_fetched = True
    cache.store(listing, "123 Main St, Kent, WA", date(2026, 9, 19))
    cache.save()

    fresh = _listing()
    restored = Cache(path)
    assert restored.restore(fresh)
    assert fresh.is_new is False
    assert fresh.first_seen == "2026-09-19"
    assert (fresh.latitude, fresh.longitude) == (47.4, -122.2)
    assert fresh.nearest_facility_ft == {"school": 812.5, "park": None}
    assert fresh.facility_checked == {"school": True, "park": True}
    assert fresh.details_fetched and fresh.description == "hello"
    assert restored.geocoded_from(fresh) == "123 Main St, Kent, WA"


def test_unseen_listing_is_new(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    listing = _listing()
    assert not cache.restore(listing)
    assert listing.is_new


def test_first_seen_is_preserved_across_runs(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    listing = _listing()
    cache.store(listing, None, date(2026, 9, 1))
    cache.store(listing, None, date(2026, 9, 19))
    assert cache.entries["1"]["first_seen"] == "2026-09-01"
    assert cache.entries["1"]["last_seen"] == "2026-09-19"


def test_prune_drops_stale_entries(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    today = date(2026, 9, 19)
    cache.store(_listing("old"), None, today - timedelta(days=90))
    cache.store(_listing("recent"), None, today - timedelta(days=5))
    cache.prune(today)
    assert set(cache.entries) == {"recent"}
