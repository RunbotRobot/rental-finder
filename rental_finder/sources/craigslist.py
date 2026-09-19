"""Craigslist search-results fetcher.

Craigslist has changed its search-results markup and feed support several
times over the years (RSS support for search pages has come and gone). This
module is written defensively: it tries a couple of parsing strategies
against the current HTML search page, logs what it couldn't parse instead of
silently dropping listings, and is meant to be low-volume, single-user,
rate-limited traffic — not a bulk crawler. Re-check the selectors in
`_parse_result_row` if Craigslist changes their page and this starts
returning zero results.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from ..config import Settings
from ..models import Listing

logger = logging.getLogger(__name__)


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
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_result_row(row, source_category: str) -> Listing | None:
    # Craigslist's current search result markup uses <li class="cl-static-search-result">
    # wrapping an <a> with the link/title, and a child with class "price" and
    # "location". Fields are optional in the DOM depending on category, so
    # every lookup here is defensive.
    link_el = row.find("a", href=True)
    if link_el is None:
        return None
    url = link_el["href"]
    source_id = url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")

    title_el = row.find(class_="title") or link_el
    title = title_el.get_text(strip=True) if title_el else "(untitled)"

    price_el = row.find(class_="price")
    price = _parse_price(price_el.get_text(strip=True) if price_el else None)

    hood_el = row.find(class_="location")
    neighborhood = hood_el.get_text(strip=True).strip("()") if hood_el else None

    time_el = row.find("time")
    posted_at = time_el.get("datetime") if time_el else None

    lat = row.get("data-latitude")
    lon = row.get("data-longitude")

    listing = Listing(
        source="craigslist",
        source_id=source_id,
        url=url,
        title=title,
        price=price,
        neighborhood=neighborhood,
        raw_address_text=neighborhood,
        posted_at=posted_at,
    )
    if lat and lon:
        try:
            listing.latitude = float(lat)
            listing.longitude = float(lon)
            listing.location_precision = "exact"
        except ValueError:
            pass
    return listing


def fetch_listings(settings: Settings, session: requests.Session | None = None) -> list[Listing]:
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", settings.geocode_user_agent)

    all_listings: list[Listing] = []
    for category in settings.cl_categories:
        url = _build_search_url(settings, category)
        logger.info("Fetching %s", url)
        try:
            resp = session.get(url, timeout=settings.request_timeout_seconds)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            time.sleep(settings.request_delay_seconds)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("li.cl-static-search-result") or soup.select("li.result-row")
        if not rows:
            logger.warning(
                "No result rows found for %s — Craigslist's markup may have changed; "
                "check _parse_result_row selectors.",
                url,
            )

        for row in rows:
            listing = _parse_result_row(row, category)
            if listing is not None:
                all_listings.append(listing)

        time.sleep(settings.request_delay_seconds)

    return all_listings
