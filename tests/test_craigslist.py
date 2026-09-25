from bs4 import BeautifulSoup

from rental_finder.models import Listing
from rental_finder.sources.craigslist import _parse_manual_listing, _parse_result_row, parse_detail_page

# Trimmed from the live markup.
SEARCH_ROW = """
<li class="cl-static-search-result" title="Walk-In Closets">
 <a href="https://www.craigslist.org/view/d/seattle-walk-in-closets/9b2PK1KjrBfu72ouovYfRD">
  <div class="title">Walk-In Closets, Non-Smoking Building</div>
  <div class="details"><div class="price">$1,195</div><div class="location">2619 5th Avenue, Seattle, WA</div></div>
 </a>
</li>
"""

DETAIL_PAGE = """
<html><body>
<h1 class="postingtitle"><span class="postingtitletext"><span class="price">$1,195</span>
<span id="titletextonly">Walk-In Closets</span><span> (2619 5th Avenue, Seattle, WA)</span></span></h1>
<div id="map" class="viewposting" data-latitude="47.615100" data-longitude="-122.344700" data-accuracy="5"></div>
<div class="mapaddress">2619 5th Avenue</div>
<p class="attrgroup"><span>0BR / 1Ba</span> <span>359ft<sup>2</sup></span> <span>available now</span></p>
<p class="attrgroup"><span>rent period: monthly</span></p>
<section id="postingbody">QR Code Link to This Post Up to 6 weeks FREE on select homes! Tour today.</section>
<p class="postinginfo">posted: <time class="date timeago" datetime="2026-09-08T16:44:39-0700">2026-09-08</time></p>
</body></html>
"""


def test_parse_search_row():
    row = BeautifulSoup(SEARCH_ROW, "html.parser").select_one("li.cl-static-search-result")
    listing = _parse_result_row(row, "apa")
    assert listing.source_id == "9b2PK1KjrBfu72ouovYfRD"
    assert listing.title == "Walk-In Closets, Non-Smoking Building"
    assert listing.price == 1195.0
    assert listing.location_text == "2619 5th Avenue, Seattle, WA"
    assert listing.category == "apa"


def test_parse_detail_page():
    listing = Listing(source="craigslist", source_id="x", url="u", title="t", price=1.0, category="apa", location_text=None)
    parse_detail_page(DETAIL_PAGE, listing)
    assert listing.details_fetched
    assert listing.description == "Up to 6 weeks FREE on select homes! Tour today."
    assert listing.posted_at == "2026-09-08T16:44:39-0700"
    assert listing.bedrooms == 0
    assert listing.map_address == "2619 5th Avenue"
    assert (listing.pin_lat, listing.pin_lon, listing.pin_accuracy) == (47.6151, -122.3447, 5)
    assert listing.room_attrs == []  # this fixture's attrgroup has no .attr/.valu/a badges


# Trimmed from a live "rooms & shares" detail page.
ROOM_SHARE_DETAIL_PAGE = """
<html><body>
<div class="attrgroup">
  <div class="attr"><span class="valu"><a href="?private_room=1">private room</a></span></div>
  <div class="attr"><span class="valu"><a href="?housing_type=1">apartment</a></span></div>
  <div class="attr"><span class="valu"><a href="?private_bath=0">no private bath</a></span></div>
</div>
<section id="postingbody">A room in a shared house near campus.</section>
</body></html>
"""


def test_parse_detail_page_captures_room_attrs():
    listing = Listing(source="craigslist", source_id="x", url="u", title="t", price=1.0, category="roo", location_text=None)
    parse_detail_page(ROOM_SHARE_DETAIL_PAGE, listing)
    assert listing.room_attrs == ["private room", "apartment", "no private bath"]


def test_parse_detail_page_without_map_or_body():
    listing = Listing(source="craigslist", source_id="x", url="u", title="t", price=1.0, category="roo", location_text="Tacoma")
    parse_detail_page("<html><body><p>nothing here</p></body></html>", listing)
    assert listing.details_fetched
    assert listing.description is None
    assert listing.pin_lat is None


# Trimmed from a real, live "apa"-category detail page for a listing the
# owner found directly (not through the normal search scrape) -- see
# main.py's load_manual_listing_urls/fetch_manual_listing.
MANUAL_LISTING_URL = "https://www.craigslist.org/view/d/seattle-mother-in-law-bedroom-bath/aCBbsLQ7BxQD3AqSGDrMBt"
MANUAL_LISTING_PAGE = """
<html><body>
<a href="/search/subarea/see?cat=apa">apartments / housing for rent</a>
<h1 class="postingtitle">
    <span class="postingtitletext">
<span class="price">$1,195</span> <span class="housing">/ 1br - 750ft<sup>2</sup> - </span><span id="titletextonly">Mother-In-Law 1 Bedroom 1 Bath w/ Jacuzzi Massaging Jet Tub</span><span> (Central District)</span>    </span>
</h1>
<div id="map" class="viewposting" data-latitude="47.612607" data-longitude="-122.295856" data-accuracy="5"></div>
<p class="mapaddress"><small><a href="https://www.google.com/maps/search/47.612607,-122.295856">google map</a></small></p>
<div class="attrgroup"><span class="attr important">in-law</span></div>
<section id="postingbody">QR Code Link to This Post Basement MIL with your own separate entrance, living room, kitchen, bath, and laundry room.</section>
</body></html>
"""


def test_parse_manual_listing():
    listing = _parse_manual_listing(MANUAL_LISTING_PAGE, MANUAL_LISTING_URL)
    assert listing.source == "craigslist"
    assert listing.source_id == "aCBbsLQ7BxQD3AqSGDrMBt"
    assert listing.url == MANUAL_LISTING_URL
    assert listing.title == "Mother-In-Law 1 Bedroom 1 Bath w/ Jacuzzi Massaging Jet Tub"
    assert listing.price == 1195.0
    assert listing.category == "apa"
    assert listing.bedrooms == 1
    assert listing.location_text == "Central District"
    # parse_detail_page() ran too, exactly like a normal detail fetch.
    assert listing.details_fetched
    assert listing.description == "Basement MIL with your own separate entrance, living room, kitchen, bath, and laundry room."
    assert (listing.pin_lat, listing.pin_lon) == (47.612607, -122.295856)
    # No real address on the page, just a Google-Maps-search link -- .mapaddress
    # picks up that link's visible text verbatim (a pre-existing parse_detail_page
    # quirk, not specific to a manual listing). Harmless: has_street_number()
    # still correctly rejects it, so this never reads as an address precision.
    assert listing.map_address == "google map"


def test_parse_manual_listing_missing_category_defaults_to_apa():
    page = MANUAL_LISTING_PAGE.replace('cat=apa">apartments / housing for rent', 'cat=xyz">something else')
    listing = _parse_manual_listing(page, MANUAL_LISTING_URL)
    assert listing.category == "apa"


def test_parse_manual_listing_returns_none_for_an_expired_posting():
    assert _parse_manual_listing("<html><body><p>This posting has been deleted by its author.</p></body></html>", MANUAL_LISTING_URL) is None
