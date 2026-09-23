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


def test_rentcast_quota_gate_allows_first_fetch_of_the_day(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    assert cache.should_fetch_rentcast(date(2026, 9, 19))


def test_rentcast_quota_gate_blocks_second_fetch_same_day(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    today = date(2026, 9, 19)
    cache.mark_rentcast_fetched(today)
    assert not cache.should_fetch_rentcast(today)


def test_rentcast_quota_gate_resets_the_next_day(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.mark_rentcast_fetched(date(2026, 9, 19))
    assert cache.should_fetch_rentcast(date(2026, 9, 20))


def test_rentcast_gate_meta_survives_a_save_load_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    cache = Cache(path)
    cache.mark_rentcast_fetched(date(2026, 9, 19))
    cache.save()
    reloaded = Cache(path)
    assert not reloaded.should_fetch_rentcast(date(2026, 9, 19))


def test_prune_never_drops_the_rentcast_gate_meta(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.mark_rentcast_fetched(date(2026, 9, 19))
    cache.store(_listing("old"), None, date(2020, 1, 1))  # long since prunable
    cache.prune(date(2026, 9, 19))
    assert not cache.should_fetch_rentcast(date(2026, 9, 19))


def test_all_source_listings_reconstructs_full_listings(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    rc = Listing(
        source="rentcast", source_id="rc1", url="https://maps.example/1", title="Apt at 1 Main St",
        price=1500.0, category="Apartment", location_text="1 Main St, Kent, WA",
        contact_name="Jane", contact_email="jane@example.com",
    )
    rc.latitude, rc.longitude = 47.38, -122.23
    rc.location_precision = PRECISION_ADDRESS
    rc.county = "King"
    rc.nearest_facility_ft = {"school": 900.0}
    rc.facility_checked = {"school": True}
    cache.store(rc, None, date(2026, 9, 19))
    cache.store(_listing("cl1"), None, date(2026, 9, 19))  # a craigslist entry, should be excluded

    rebuilt = cache.all_source_listings("rentcast")
    assert len(rebuilt) == 1
    listing = rebuilt[0]
    assert listing.source_id == "rc1"
    assert listing.contact_email == "jane@example.com"
    assert (listing.latitude, listing.longitude) == (47.38, -122.23)
    assert listing.nearest_facility_ft == {"school": 900.0}
    assert listing.is_new is False


def test_all_source_listings_empty_when_none_cached(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    cache.store(_listing("cl1"), None, date(2026, 9, 19))
    assert cache.all_source_listings("rentcast") == []
