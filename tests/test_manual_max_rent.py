"""Manual listings (manual_listings.txt) get the separate, higher
manual_max_rent cap instead of the normal max_rent -- see config.py. A
manual addition has already been personally reviewed by the owner before
being added, unlike max_rent, which exists to keep the automated,
unreviewed Craigslist/RentCast search from pulling in things nobody
looked at."""

import json
from datetime import date
from unittest.mock import patch

from rental_finder.config import Settings
from rental_finder.main import run
from rental_finder.models import PRECISION_AREA, Listing


def _manual_listing(source_id: str, price: float) -> Listing:
    listing = Listing(
        source="craigslist", source_id=source_id, url=f"https://www.craigslist.org/view/d/x/{source_id}",
        title="A manually-added listing", price=price, category="apa", location_text="Somewhere",
    )
    listing.details_fetched = True
    listing.pin_lat, listing.pin_lon = 47.7, -122.2
    # Set directly (rather than leaving it to locate()) so this test doesn't
    # make a real geocoding network call -- main.py's run() only calls
    # locate() when latitude is still None, same trick test_main_rentcast_gate.py
    # uses for its RentCast fixture.
    listing.latitude, listing.longitude = listing.pin_lat, listing.pin_lon
    listing.location_precision = PRECISION_AREA
    listing.county = "King County"
    return listing


def _run(tmp_path, manual_urls, fetch_manual_side_effect):
    manual_path = tmp_path / "manual_listings.txt"
    manual_path.write_text("\n".join(manual_urls) + "\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    j = tmp_path / "data.json"
    settings = Settings(
        cache_path=str(tmp_path / "cache.json"), overrides_path=str(tmp_path / "none.csv"),
        profile_path=str(tmp_path / "none_profile.json"), emailed_path=str(tmp_path / "none_emailed.json"),
        manual_listings_path=str(manual_path), fetch_details=False,
        request_delay_seconds=0,  # skip the real per-fetch politeness delay in tests
    )
    with (
        patch("rental_finder.main.craigslist.fetch_listings", return_value=[]),
        patch("rental_finder.main.craigslist.fetch_manual_listing", side_effect=fetch_manual_side_effect),
        patch("rental_finder.main.compliance.annotate_distances", lambda *a, **k: None),
        patch("rental_finder.main.date") as mock_date,
    ):
        mock_date.today.return_value = date(2026, 9, 25)
        run(settings, str(out), json_path=str(j))
    return json.loads(j.read_text())


def test_manual_listing_over_max_rent_but_under_manual_max_rent_is_kept(tmp_path):
    # Settings() defaults: max_rent=1900, manual_max_rent=2200.
    data = _run(
        tmp_path,
        ["https://www.craigslist.org/view/d/x/m1"],
        fetch_manual_side_effect=lambda u, s, sess: _manual_listing("m1", 2000.0),
    )
    assert [l["id"] for l in data["listings"]] == ["m1"]


def test_manual_listing_over_manual_max_rent_is_still_dropped(tmp_path):
    data = _run(
        tmp_path,
        ["https://www.craigslist.org/view/d/x/m2"],
        fetch_manual_side_effect=lambda u, s, sess: _manual_listing("m2", 5000.0),
    )
    assert data["listings"] == []


def test_manual_listing_at_or_under_normal_max_rent_is_kept_too(tmp_path):
    data = _run(
        tmp_path,
        ["https://www.craigslist.org/view/d/x/m3"],
        fetch_manual_side_effect=lambda u, s, sess: _manual_listing("m3", 1500.0),
    )
    assert [l["id"] for l in data["listings"]] == ["m3"]
