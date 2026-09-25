"""Craigslist fetcher: search results, then (optionally) each listing's page.

Craigslist used to support `&format=rss` on search-result pages; as of this
writing that's actively blocked (confirmed live: HTTP 403 "Your request has
been blocked", even with a valid session cookie), so this parses the plain
HTML search page instead, which robots.txt does not disallow. It's written
to be low-volume, single-user, rate-limited traffic -- not a bulk crawler --
and to stop cleanly the moment Craigslist starts refusing requests.

Selectors were checked against the live site. If Craigslist changes its
markup and this starts returning zero results, `_parse_result_row` and
`parse_detail_page` are the places to look.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from ..config import Settings
from ..models import Listing

logger = logging.getLogger(__name__)

_BEDROOMS_RE = re.compile(r"(\d+)\s*BR\b", re.IGNORECASE)
_BODY_BOILERPLATE = "QR Code Link to This Post"
_CATEGORY_RE = re.compile(r"cat=(apa|roo)\b")


class Blocked(Exception):
    """Craigslist refused the request (403 or similar). Stop fetching."""


def _build_search_url(settings: Settings, category: str) -> str:
    params = {
        "postal": settings.postal_code,
        "search_distance": settings.search_radius_miles,
        "max_price": int(settings.max_rent),
        "sort": "date",
    }
    return f"https://{settings.cl_subdomain}.craigslist.org/search/{category}?{urlencode(params)}"


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _parse_result_row(row, category: str) -> Listing | None:
    # Live markup: <li class="cl-static-search-result"><a href=...>
    #   <div class="title">..</div><div class="details"><div class="price">..</div>
    #   <div class="location">..</div></div></a></li>
    link_el = row.find("a", href=True)
    if link_el is None:
        return None
    url = link_el["href"]
    source_id = url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")

    title_el = row.find(class_="title")
    title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True) or "(untitled)"

    price_el = row.find(class_="price")
    location_el = row.find(class_="location")

    return Listing(
        source="craigslist",
        source_id=source_id,
        url=url,
        title=title,
        price=_parse_price(price_el.get_text(strip=True) if price_el else None),
        category=category,
        location_text=location_el.get_text(strip=True) if location_el else None,
    )


def _get(session: requests.Session, url: str, settings: Settings) -> requests.Response:
    resp = session.get(url, timeout=settings.request_timeout_seconds)
    if resp.status_code in (403, 429):
        raise Blocked(f"HTTP {resp.status_code} from {url}")
    resp.raise_for_status()
    return resp


def fetch_listings(settings: Settings, session: requests.Session) -> list[Listing]:
    listings: list[Listing] = []
    for category in settings.cl_categories:
        url = _build_search_url(settings, category)
        logger.info("Fetching %s", url)
        try:
            resp = _get(session, url, settings)
        except Blocked as exc:
            logger.error("Craigslist blocked the search request: %s", exc)
            break
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            time.sleep(settings.request_delay_seconds)
            continue

        rows = BeautifulSoup(resp.text, "html.parser").select("li.cl-static-search-result")
        if not rows:
            logger.warning("No result rows found for %s -- Craigslist's markup may have changed.", url)
        for row in rows:
            listing = _parse_result_row(row, category)
            if listing is not None:
                listings.append(listing)
        logger.info("%s: %d listings", category, len(rows))
        time.sleep(settings.request_delay_seconds)
    return listings


def parse_detail_page(html: str, listing: Listing) -> None:
    """Fill in description, post date, bedrooms, map address, and map pin."""
    soup = BeautifulSoup(html, "html.parser")

    body = soup.find(id="postingbody")
    if body is not None:
        text = body.get_text(" ", strip=True)
        if text.startswith(_BODY_BOILERPLATE):
            text = text[len(_BODY_BOILERPLATE):].strip()
        listing.description = text

    time_el = soup.select_one("time.date.timeago") or soup.find("time")
    if time_el is not None and time_el.get("datetime"):
        listing.posted_at = time_el["datetime"]

    for group in soup.select(".attrgroup"):
        match = _BEDROOMS_RE.search(group.get_text(" ", strip=True))
        if match:
            listing.bedrooms = int(match.group(1))
            break

    # Structured attribute badges ("private room", "no private bath", "in-law", ...)
    # -- each rendered as its own <div class="attr"><span class="valu"><a>label</a>.
    listing.room_attrs = [
        a.get_text(strip=True).lower()
        for a in soup.select(".attrgroup .attr .valu a")
        if a.get_text(strip=True)
    ]

    map_address_el = soup.select_one(".mapaddress")
    if map_address_el is not None:
        listing.map_address = map_address_el.get_text(" ", strip=True) or None

    map_el = soup.find(id="map")
    if map_el is not None:
        try:
            listing.pin_lat = float(map_el["data-latitude"])
            listing.pin_lon = float(map_el["data-longitude"])
            listing.pin_accuracy = int(map_el.get("data-accuracy", 0)) or None
        except (KeyError, ValueError, TypeError):
            pass

    listing.details_fetched = True


def _parse_manual_listing(html: str, url: str) -> Listing | None:
    """Everything a search-result row would normally supply -- title, price,
    bedrooms, category, neighborhood -- parsed straight from a detail page
    instead, since it has all of that and more; parse_detail_page() then
    fills in the rest exactly like a normal detail fetch (description,
    room_attrs, map pin, ...), so the result is indistinguishable from a
    listing fetch_listings() found on its own. Returns None if the page
    doesn't look like an active posting (expired/removed) -- the title/price
    this always shows on a live posting are what's checked for that."""
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("#titletextonly")
    price_el = soup.select_one("h1.postingtitle .price")
    if title_el is None or price_el is None:
        logger.warning("Manual listing doesn't look like an active posting anymore, skipping: %s", url)
        return None

    category_match = _CATEGORY_RE.search(html)
    if category_match is None:
        logger.warning("Could not determine category for manual listing, assuming apa: %s", url)
    category = category_match.group(1) if category_match else "apa"

    bedrooms = None
    housing_el = soup.select_one("h1.postingtitle .housing")
    if housing_el is not None:
        match = _BEDROOMS_RE.search(housing_el.get_text(" ", strip=True))
        if match:
            bedrooms = int(match.group(1))

    # The title's last <span> is the neighborhood in parens, e.g.
    # "...Jet Tub</span><span> (Central District)</span>" -- same text a
    # search-result row's .location would have carried.
    neighborhood = None
    title_span = soup.select_one("h1.postingtitle .postingtitletext")
    if title_span is not None:
        spans = title_span.find_all("span", recursive=False)
        if spans:
            last = spans[-1].get_text(strip=True)
            if last.startswith("(") and last.endswith(")"):
                neighborhood = last[1:-1]

    listing = Listing(
        source="craigslist",
        source_id=url.rstrip("/").rsplit("/", 1)[-1].replace(".html", ""),
        url=url,
        title=title_el.get_text(strip=True),
        price=_parse_price(price_el.get_text(strip=True)),
        category=category,
        location_text=neighborhood,
        bedrooms=bedrooms,
    )
    parse_detail_page(html, listing)
    return listing


def fetch_manual_listing(url: str, settings: Settings, session: requests.Session) -> Listing | None:
    """Build a full Listing from a single Craigslist posting URL the owner
    found directly (shared by a poster, surfaced outside the two searched
    categories/radius, or just noticed browsing) rather than through
    fetch_listings()'s search-page scrape. See main.py's
    load_manual_listing_urls() for where the URL list comes from, and
    _parse_manual_listing() for the actual parsing. Returns None on a
    request failure too (blocked/network/timeout) -- logged, not raised, so
    one bad manual URL doesn't stop the whole run."""
    try:
        resp = _get(session, url, settings)
    except (Blocked, requests.RequestException) as exc:
        logger.warning("Failed to fetch manual listing %s: %s", url, exc)
        return None
    return _parse_manual_listing(resp.text, url)


def fetch_details(listings: list[Listing], settings: Settings, session: requests.Session) -> int:
    """Fetch detail pages for up to settings.max_detail_fetches listings.
    Returns how many were fetched. Stops early if Craigslist blocks us."""
    fetched = 0
    for listing in listings:
        if listing.details_fetched:
            continue
        if fetched >= settings.max_detail_fetches:
            logger.info("Hit max_detail_fetches=%d; remaining listings will be fetched next run.", settings.max_detail_fetches)
            break
        try:
            resp = _get(session, listing.url, settings)
        except Blocked as exc:
            logger.error("Craigslist blocked detail fetches (%s). Stopping; try again later.", exc)
            break
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", listing.url, exc)
            time.sleep(settings.request_delay_seconds)
            continue
        parse_detail_page(resp.text, listing)
        fetched += 1
        time.sleep(settings.request_delay_seconds)
    return fetched
