"""Builds the outreach email for one listing -- verbatim disclosure, no LLM.

This is a plain string template, deliberately not an LLM-generated email.
An irreversible message that discloses something this consequential to a
stranger is the wrong place for a model to improvise phrasing or guess at
facts about the listing; a template only ever inserts data this tool has
already verified (address, price, bedrooms) and your own pre-written
paragraphs, unchanged.

Returns None -- refuses to draft anything -- if the applicant profile is
incomplete (see applicant_profile.py). This is the same rule for every
source: your own project decision was to disclose upfront in every email,
so there is no path here that produces a draft without your disclosure
text, whether or not that draft ever gets auto-sent.
"""

from __future__ import annotations

from .applicant_profile import ApplicantProfile
from .models import Listing


def _listing_description(listing: Listing) -> str:
    parts = []
    if listing.bedrooms is not None:
        parts.append("studio" if listing.bedrooms == 0 else f"{listing.bedrooms}-bedroom")
    parts.append("place")
    if listing.price is not None:
        parts.append(f"listed at ${listing.price:,.0f}/month")
    return " ".join(parts)


def build_draft(listing: Listing, profile: ApplicantProfile) -> tuple[str, str] | None:
    """(subject, body), or None if the profile isn't complete enough to send."""
    if not profile.is_complete():
        return None

    address = listing.best_address or listing.title
    subject = f"Rental inquiry: {address}"

    lines = [
        "Hello,",
        "",
        f"I'm writing about the {_listing_description(listing)} at {address}. I'd like to "
        "find out if it's still available and, if so, learn more about touring it.",
        "",
    ]
    if profile.employment_text.strip():
        lines += [profile.employment_text.strip(), ""]
    if profile.income_text.strip():
        lines += [profile.income_text.strip(), ""]
    if profile.move_in_date.strip():
        lines += [f"Move-in timeline: {profile.move_in_date.strip()}.", ""]

    lines += [profile.disclosure_text.strip(), ""]

    lines += ["I'm happy to answer any questions and provide references. Thank you for your time,", ""]
    lines.append(profile.name.strip())
    if profile.phone.strip():
        lines.append(profile.phone.strip())
    if profile.email.strip():
        lines.append(profile.email.strip())

    return subject, "\n".join(lines)
