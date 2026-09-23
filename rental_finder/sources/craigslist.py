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
