import json

from rental_finder.config import Settings
from rental_finder.models import PRECISION_ADDRESS, PRECISION_AREA, Listing
from rental_finder.report import to_json

SETTINGS = Settings(buffer_tiers_ft=(500, 1000), facility_types=("school", "park"))


def _listing(source_id, precision=PRECISION_ADDRESS, nearest=None) -> Listing:
    listing = Listing(source="craigslist", source_id=source_id, url=f"u/{source_id}", title=source_id,
                      price=1000.0, category="apa", location_text="1 Main St, Kent, WA")
    listing.location_precision = precision
    if nearest is not None:
        listing.nearest_facility_ft = dict(nearest)
        listing.facility_checked = {k: True for k in nearest}
    return listing


def test_json_payload_is_serializable_and_ranked():
    located = _listing("a", nearest={"school": 750.0, "park": None})
    unknown = _listing("b", precision=PRECISION_AREA)
    payload = json.loads(json.dumps(to_json([unknown, located], SETTINGS, "2026-09-19T12:00:00+00:00")))
    assert [l["id"] for l in payload["listings"]] == ["a", "b"]
    a, b = payload["listings"]
    assert a["clears"] == {"500": True, "1000": False}
    assert a["nearest_ft"] == {"school": 750.0, "park": -1}   # -1 = none within the largest buffer
    assert b["clears"] == {"500": None, "1000": None}
    assert b["nearest_ft"] == {"school": None, "park": None}  # never measured
    assert payload["tier_counts"] == {"500": 1, "1000": 0}
    assert payload["settings"]["buffer_tiers_ft"] == [500, 1000]
