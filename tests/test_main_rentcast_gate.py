"""Integration-ish test for main.run()'s RentCast daily-quota gate: the
piece that actually matters is that a second run the same day doesn't
re-fetch, but the listing still shows up in that run's output instead of
vanishing until the next day."""

import json
from datetime import date
from unittest.mock import patch

from rental_finder.config import Settings
from rental_finder.main import run
from rental_finder.models import PRECISION_ADDRESS, Listing


def _rentcast_listing() -> Listing:
    listing = Listing(
        source="rentcast", source_id="rc1", url="https://maps.example/1", title="Apt at 1 Main St",
        price=1500.0, category="Apartment", location_text="1 Main St, Kent, WA",
        contact_name="Jane", contact_email="jane@example.com",
    )
    listing.latitude, listing.longitude = 47.38, -122.23
    listing.location_precision = PRECISION_ADDRESS
    listing.county = "King"
    return listing


def _run(tmp_path, today, rentcast_calls, force_rentcast=False):
    out = tmp_path / "out.csv"
    j = tmp_path / "data.json"
    settings = Settings(
        rentcast_api_key="fake-key", cache_path=str(tmp_path / "cache.json"),
        overrides_path=str(tmp_path / "none.csv"), profile_path=str(tmp_path / "none_profile.json"),
        emailed_path=str(tmp_path / "none_emailed.json"), manual_listings_path=str(tmp_path / "none_manual.txt"),
        fetch_details=False,
    )
    with (
        patch("rental_finder.main.craigslist.fetch_listings", return_value=[]),
        patch("rental_finder.main.rentcast.fetch_listings", side_effect=lambda *a, **k: rentcast_calls()),
        patch("rental_finder.main.compliance.annotate_distances", lambda *a, **k: None),
        patch("rental_finder.main.date") as mock_date,
    ):
        mock_date.today.return_value = today
        run(settings, str(out), json_path=str(j), force_rentcast=force_rentcast)
    return json.loads(j.read_text())


def test_second_run_same_day_reuses_cached_rentcast_listing_without_refetching(tmp_path):
    call_count = 0

    def fake_fetch():
        nonlocal call_count
        call_count += 1
        return True, [_rentcast_listing()]

    day1 = _run(tmp_path, date(2026, 9, 23), fake_fetch)
    assert call_count == 1
    assert len(day1["listings"]) == 1

    def fail_if_called():
        raise AssertionError("RentCast should not be re-fetched the same day")

    day1_again = _run(tmp_path, date(2026, 9, 23), fail_if_called)
    assert call_count == 1  # still 1 -- the second run never called fetch_listings
    assert len(day1_again["listings"]) == 1  # but the listing is still there
    assert day1_again["listings"][0]["id"] == "rc1"


def test_next_day_refetches(tmp_path):
    call_count = 0

    def fake_fetch():
        nonlocal call_count
        call_count += 1
        return True, [_rentcast_listing()]

    _run(tmp_path, date(2026, 9, 23), fake_fetch)
    _run(tmp_path, date(2026, 9, 24), fake_fetch)
    assert call_count == 2


def test_force_rentcast_refetches_same_day(tmp_path):
    call_count = 0

    def fake_fetch():
        nonlocal call_count
        call_count += 1
        return True, [_rentcast_listing()]

    _run(tmp_path, date(2026, 9, 23), fake_fetch)
    _run(tmp_path, date(2026, 9, 23), fake_fetch, force_rentcast=True)
    assert call_count == 2


def test_failed_fetch_does_not_consume_the_quota_slot(tmp_path):
    call_count = 0

    def failing_fetch():
        nonlocal call_count
        call_count += 1
        return False, []

    _run(tmp_path, date(2026, 9, 23), failing_fetch)
    _run(tmp_path, date(2026, 9, 23), failing_fetch)
    assert call_count == 2  # both runs retried, since the first never succeeded
