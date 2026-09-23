"""RentCast fetcher: structured rental listings with a real contact email.

Unlike Craigslist, this is a paid, authenticated API pulling from real
property-management/MLS-adjacent data, so:
- addresses and coordinates come straight from the provider -- no geocoding
  step, no ambiguity about precision.
- a real contact (listingAgent or listingOffice, with a genuine email) is
  usually present. This is the ONLY source this whole tool ever auto-emails
  on your behalf, precisely because Craigslist has no equivalent (see
  sources/craigslist.py's module docstring).
- it covers apartments/houses/condos, not room-shares -- Craigslist's "roo"
  category has no RentCast equivalent.

Endpoint and auth verified against RentCast's published docs and a working
example request (https://developers.rentcast.io/reference/rental-listings-long-term):
GET https://api.rentcast.io/v1/listings/rental/long-term
header: X-Api-Key: <key>

No API key configured -> this source is silently skipped (not an error);
Craigslist alone is still a complete, working setup.
"""

from __future__ import annotations

import logging

import requests

from ..config import Settings
from ..models import PRECISION_ADDRESS, Listing

logger = logging.getLogger(__name__)

RENTCAST_URL = "https://api.rentcast.io/v1/listings/rental/long-term"


def _contact(item: dict) -> tuple[str | None, str | None]:
    """(name, email) from listingAgent if it has an email, else listingOffice."""
    for key in ("listingAgent", "listingOffice"):
        contact = item.get(key) or {}
        if contact.get("email"):
            return contact.get("name"), contact["email"]
    return None, None


def _to_listing(item: dict) -> Listing | None:
    lat, lon = item.get("latitude"), item.get("longitude")
    price = item.get("price")
    address = item.get("formattedAddress")
    if lat is None or lon is None or price is None or not address:
        return None

    contact_name, contact_email = _contact(item)
    bedrooms = item.get("bedrooms")

    listing = Listing(
        source="rentcast",
        source_id=str(item.get("id") or address),
        # RentCast doesn't return a public listing page URL; a map search is
        # the only link we can give that's guaranteed to resolve.
        url=f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(address)}",
        title=f"{item.get('propertyType', 'Rental')} at {address}",
        price=float(price),
        category=item.get("propertyType", "Apartment"),
        location_text=address,
        bedrooms=int(bedrooms) if bedrooms is not None else None,
        contact_name=contact_name,
        contact_email=contact_email,
        posted_at=item.get("listedDate"),
    )
    # Real, provider-supplied coordinates -- no geocoding needed or wanted.
    listing.latitude, listing.longitude = float(lat), float(lon)
    listing.location_precision = PRECISION_ADDRESS
    listing.county = item.get("county")
    listing.details_fetched = True  # nothing more to fetch; description isn't in this schema
    return listing


def fetch_listings(settings: Settings, session: requests.Session) -> list[Listing]:
    if not settings.rentcast_api_key:
        return []

    params = {
        "latitude": settings.rentcast_latitude,
        "longitude": settings.rentcast_longitude,
        "radius": min(settings.search_radius_miles, 100),
        "status": "Active",
        "limit": 500,
    }
    headers = {"X-Api-Key": settings.rentcast_api_key, "Accept": "application/json"}
    try:
        resp = requests.get(RENTCAST_URL, params=params, headers=headers, timeout=settings.request_timeout_seconds)
        resp.raise_for_status()
        items = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("RentCast fetch failed: %s", exc)
        return []

    listings = []
    for item in items:
        listing = _to_listing(item)
        if listing is not None:
            listings.append(listing)
    logger.info("RentCast: %d listings", len(listings))
    return listings
