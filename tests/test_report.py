import csv

from rental_finder.config import Settings
from rental_finder.models import PRECISION_ADDRESS, PRECISION_AREA, Listing
from rental_finder.report import rank_listings, summarize, to_json, write_csv

SETTINGS = Settings(buffer_tiers_ft=(500, 1000), facility_types=("school", "park"))


def _listing(source_id, price=1000.0, precision=PRECISION_ADDRESS, nearest=None, spam=0) -> Listing:
    listing = Listing(
        source="craigslist", source_id=source_id, url=f"u/{source_id}", title=source_id,
        price=price, category="apa", location_text="1 Main St",
    )
    listing.location_precision = precision
    listing.spam_score = spam
    if nearest is not None:
        listing.nearest_facility_ft = dict(nearest)
        listing.facility_checked = {k: True for k in nearest}
    return listing


def test_ranking_order():
    clears_all = _listing("clears_all", price=1800.0, nearest={"school": None, "park": None})
    clears_one = _listing("clears_one", price=900.0, nearest={"school": 700.0, "park": None})
    unknown = _listing("unknown", price=800.0, precision=PRECISION_AREA)
    too_close = _listing("too_close", price=700.0, nearest={"school": 100.0, "park": None})
    spammy = _listing("spammy", price=600.0, nearest={"school": None, "park": None}, spam=2)
    ranked = [l.source_id for l in rank_listings([spammy, too_close, unknown, clears_one, clears_all], SETTINGS)]
    assert ranked == ["clears_all", "clears_one", "unknown", "too_close", "spammy"]


def test_cheaper_first_within_same_clearance():
    a = _listing("a", price=1500.0, nearest={"school": None, "park": None})
    b = _listing("b", price=1200.0, nearest={"school": None, "park": None})
    assert [l.source_id for l in rank_listings([a, b], SETTINGS)] == ["b", "a"]


def test_csv_columns_and_labels(tmp_path):
    listing = _listing("x", nearest={"school": 750.0, "park": None})
    out = tmp_path / "out.csv"
    write_csv([listing], SETTINGS, out)
    with out.open() as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["clears_500ft"] == "yes"
    assert rows[0]["clears_1000ft"] == "no"
    assert rows[0]["nearest_school_ft"] == "750"
    assert rows[0]["nearest_park_ft"] == ">1000"


def test_csv_includes_source_and_outreach_columns(tmp_path):
    listing = _listing("x", nearest={"school": 750.0, "park": None})
    listing.source = "rentcast"
    listing.contact_email = "landlord@example.com"
    listing.outreach_result = "sent"
    out = tmp_path / "out.csv"
    write_csv([listing], SETTINGS, out)
    with out.open() as f:
        row = next(csv.DictReader(f))
    assert row["source"] == "rentcast"
    assert row["contact_email"] == "landlord@example.com"
    assert row["outreach_result"] == "sent"


def test_json_includes_outreach_fields():
    listing = _listing("x", nearest={"school": 750.0, "park": None})
    listing.contact_email = "landlord@example.com"
    listing.draft_subject = "Rental inquiry: 1 Main St"
    listing.draft_body = "Hello..."
    listing.outreach_result = "ready to send"
    payload = to_json([listing], SETTINGS, "2026-09-23T00:00:00+00:00")
    row = payload["listings"][0]
    assert row["contact_email"] == "landlord@example.com"
    assert row["draft_subject"] == "Rental inquiry: 1 Main St"
    assert row["draft_body"] == "Hello..."
    assert row["outreach_result"] == "ready to send"
    assert row["source"] == "craigslist"


def test_summary_counts_survivors_per_tier():
    listings = [
        _listing("a", nearest={"school": None, "park": None}),
        _listing("b", nearest={"school": 700.0, "park": None}),
        _listing("c", precision=PRECISION_AREA),
    ]
    text = summarize(listings, SETTINGS)
    assert "500 ft: 2" in text
    assert "1000 ft: 1" in text
    assert "1 need an address" in text
