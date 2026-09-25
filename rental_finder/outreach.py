"""The outreach eligibility gate.

Every rule here is a deterministic, auditable check -- never a model's
self-reported confidence -- because the thing being gated (an email you
can't unsend, disclosing something consequential, to a stranger) is not
something to trust to "the AI seemed sure."

This module never sends email itself unless `settings.send_emails` is set
(only ever true for a local, deliberate test run -- see mailer.py and
main.py; the scheduled GitHub Action never sets it). In normal operation, a
listing that clears every rule below is marked "ready to send" and left
there: a separate Claude session, woken on a recurring check-in, reads
those through the Worker's narrow `AGENT_TOKEN`-gated endpoint, drafts each
email itself (real per-listing judgment, not a template), and sends it
directly -- see README's "Outreach and auto-send". Anything that doesn't
clear every rule gets a drafted email attached anyway (for you to review or
send yourself, e.g. via Craigslist's own reply box) and a stated reason it
isn't gate-eligible -- never a silent skip.
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
    listing: Listing,
    settings: Settings,
    profile: ApplicantProfile,
    already_emailed: set[str],
    company_notes: dict[str, tuple[str | None, str]],
) -> str | None:
    """None if every auto-send condition is met; otherwise why not."""
    if listing.source_id in already_emailed:
        return "already contacted"
    if not profile.is_complete():
        return "applicant profile incomplete"
    # Address/spam/buffer checks come before the contact-email check on
    # purpose: Craigslist listings always fail contact-email (see
    # sources/craigslist.py), so checking it first would make "no
    # automatable contact" the reason for EVERY Craigslist listing --
    # including ones with no address, spam flags, or too close a facility --
    # rather than what it's supposed to mean: this listing cleared every
    # other rule and contact is the only thing left. The Worker's
    # /api/agent/candidates endpoint keys off that exact string to decide
    # which Craigslist listings are worth a personal draft, so getting this
    # order wrong there silently offers hundreds of unqualified listings.
    if listing.location_precision != PRECISION_ADDRESS:
        return "no verified address"
    if listing.spam_score != 0:
        return "spam-flagged"
    clearance = listing.clears_buffer(settings.auto_send_buffer_ft, settings.facility_types)
    if clearance is None:
        return "facility distance unverified"
    if clearance is False:
        return f"does not clear {settings.auto_send_buffer_ft} ft on every facility type"
    # Checked before the generic contact_email check below: a Craigslist
    # listing needs a VERIFIED contact (contact_source set -- i.e. a real
    # citation from a contact override, recorded via POST /api/agent/contact
    # after a check-in either found a direct email the poster gave in their
    # own listing text, or researched the property/company the same way as
    # for a RentCast listing -- see main.py's load_contact_overrides), never
    # just any contact_email. sources/craigslist.py itself never sets
    # contact_email at all -- Craigslist's own reply widget is a JS relay,
    # not a real address -- so the only way this field is ever non-empty for
    # a Craigslist listing is a verified override in the first place. This
    # check still matters: it means a hypothetical future bug that sets
    # contact_email on a Craigslist listing through some OTHER path (a
    # caching mistake, a copy-paste error) can't silently make it
    # gate-eligible without a cited contact_source to back it up.
    if listing.source == "craigslist" and not listing.contact_source:
        return "no automatable contact (Craigslist has no real send address)"
    # Checked before the final contact_email check, same ordering rule as
    # everything else in this function: a company-level block is exactly
    # the kind of thing that should stop a send even once every other rule
    # has cleared. Keyed by contact_email (normalized lowercase/trimmed) --
    # not address, and not the site's building-group cards, which only
    # group postings that share the SAME address -- because a single
    # property manager can list units at many different addresses, and the
    # thing being blocked is the company, not any one building. Added after
    # a real incident: Foundation Group manages units at more than one
    # address, and the owner had already been told directly they wouldn't
    # pass screening there, but a second listing from the same company at a
    # different address still got auto-emailed the same day. See
    # main.py's load_company_notes() and worker/src/index.js's
    # /api/company-notes for how this gets recorded.
    if listing.contact_email:
        note = company_notes.get(listing.contact_email.strip().lower())
        if note is not None:
            company, text = note
            label = f"company flagged ({company})" if company else "company flagged"
            return f"{label}: {text}"
    if not listing.contact_email:
        return "no contact email"
    return None


def process(
    listings: list[Listing],
    settings: Settings,
    profile: ApplicantProfile,
    already_emailed: set[str],
    company_notes: dict[str, tuple[str | None, str]] | None = None,
) -> set[str]:
    """Fills in draft_subject/draft_body/outreach_result on every listing in
    place. Returns the set of source_ids actually emailed this run, for the
    caller to persist so a future run never double-sends."""
    newly_emailed: set[str] = set()
    company_notes = company_notes or {}

    for listing in listings:
        draft = build_draft(listing, profile)
        if draft is None:
            listing.outreach_result = "applicant profile incomplete"
            continue
        listing.draft_subject, listing.draft_body = draft

        reason = _gate_reason(listing, settings, profile, already_emailed, company_notes)
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
