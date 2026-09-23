"""The auto-send gate.

Every rule here is a deterministic, auditable check -- never a model's
self-reported confidence -- because the action being gated (an email you
can't unsend, disclosing something consequential, to a stranger) is not
something to trust to "the AI seemed sure." A listing auto-sends only when
every one of these holds; anything else gets a drafted email attached
(for you to review or send yourself, e.g. via Craigslist's own reply box)
and a stated reason it wasn't sent automatically -- never a silent skip.
"""

from __future__ import annotations

import logging

from .applicant_profile import ApplicantProfile
from .config import Settings
from .email_draft import build_draft
from .mailer import send as send_email
from .models import PRECISION_ADDRESS, Listing

logger = logging.getLogger(__name__)


def _gate_reason(
    listing: Listing, settings: Settings, profile: ApplicantProfile, already_emailed: set[str]
) -> str | None:
    """None if every auto-send condition is met; otherwise why not."""
    if listing.source_id in already_emailed:
        return "already contacted"
    if not profile.is_complete():
        return "applicant profile incomplete"
    if not listing.contact_email:
        return "no automatable contact (Craigslist has no real send address)" if listing.source == "craigslist" else "no contact email"
    if listing.location_precision != PRECISION_ADDRESS:
        return "no verified address"
    if listing.spam_score != 0:
        return "spam-flagged"
    clearance = listing.clears_buffer(settings.auto_send_buffer_ft, settings.facility_types)
    if clearance is None:
        return "facility distance unverified"
    if clearance is False:
        return f"does not clear {settings.auto_send_buffer_ft} ft on every facility type"
    return None


def process(
    listings: list[Listing], settings: Settings, profile: ApplicantProfile, already_emailed: set[str]
) -> set[str]:
    """Fills in draft_subject/draft_body/outreach_result on every listing in
    place. Returns the set of source_ids actually emailed this run, for the
    caller to persist so a future run never double-sends."""
    newly_emailed: set[str] = set()

    for listing in listings:
        draft = build_draft(listing, profile)
        if draft is None:
            listing.outreach_result = "applicant profile incomplete"
            continue
        listing.draft_subject, listing.draft_body = draft

        reason = _gate_reason(listing, settings, profile, already_emailed)
        if reason is not None:
            listing.outreach_result = reason
            continue

        if not settings.send_emails:
            listing.outreach_result = "ready to send"
            continue

        ok, message = send_email(listing.contact_email, listing.draft_subject, listing.draft_body, settings)
        if ok:
            listing.outreach_result = "sent"
            newly_emailed.add(listing.source_id)
        else:
            listing.outreach_result = f"send failed: {message}"

    return newly_emailed
