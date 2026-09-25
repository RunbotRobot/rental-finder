from rental_finder.applicant_profile import ApplicantProfile
from rental_finder.config import Settings
from rental_finder.models import PRECISION_ADDRESS, PRECISION_AREA, Listing
from rental_finder.outreach import process

COMPLETE_PROFILE = ApplicantProfile(name="Alex", disclosure_text="My disclosure.")
SETTINGS = Settings(
    buffer_tiers_ft=(500, 1000), facility_types=("school",), auto_send_buffer_ft=1000, send_emails=True,
    gmail_address="me@gmail.com", gmail_app_password="app-password",
)


def _good_rentcast_listing(source_id="rc1", contact_email="landlord@example.com") -> Listing:
    listing = Listing(
        source="rentcast", source_id=source_id, url="u", title="Apartment", price=1500.0,
        category="Apartment", location_text="1 Main St, Kent, WA", contact_email=contact_email,
    )
    listing.location_precision = PRECISION_ADDRESS
    listing.nearest_facility_ft = {"school": None}
    listing.facility_checked = {"school": True}
    listing.spam_score = 0
    return listing


def test_incomplete_profile_blocks_everything_and_drafts_nothing():
    listing = _good_rentcast_listing()
    process([listing], SETTINGS, ApplicantProfile(), already_emailed=set())
    assert listing.draft_subject is None
    assert listing.outreach_result == "applicant profile incomplete"


def test_clean_rentcast_listing_sends_when_send_emails_is_true(monkeypatch):
    sent = {}

    def fake_send(to_address, subject, body, settings):
        sent["to"] = to_address
        return True, "sent"

    monkeypatch.setattr("rental_finder.outreach.send_email", fake_send)
    listing = _good_rentcast_listing()
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "sent"
    assert newly_emailed == {"rc1"}
    assert sent["to"] == "landlord@example.com"


def test_without_send_emails_flag_marks_ready_but_does_not_send(monkeypatch):
    called = False

    def fake_send(*a, **k):
        nonlocal called
        called = True
        return True, "sent"

    monkeypatch.setattr("rental_finder.outreach.send_email", fake_send)
    settings = Settings(**{**SETTINGS.__dict__, "send_emails": False})
    listing = _good_rentcast_listing()
    newly_emailed = process([listing], settings, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "ready to send"
    assert newly_emailed == set()
    assert called is False


def test_craigslist_listing_never_auto_sends_even_with_perfect_data(monkeypatch):
    calls = []
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: calls.append(a) or (True, "sent"))
    listing = _good_rentcast_listing(source_id="cl1", contact_email=None)
    listing.source = "craigslist"
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert "craigslist" in listing.outreach_result.lower()
    assert newly_emailed == set()
    assert calls == []
    # a draft should still be produced, for manual use
    assert listing.draft_subject is not None


def test_craigslist_listing_with_an_unverified_contact_email_still_never_auto_sends(monkeypatch):
    """Regression guard for a gap introduced by supporting contact overrides
    for RentCast (main.py's load_contact_overrides): before that, Craigslist
    always failed the contact_email check simply because craigslist.py never
    set it -- an assumption, not an enforced rule. This proves the source
    check in _gate_reason() makes it a hard rule instead: a Craigslist
    listing with a contact_email but NO contact_source (i.e. not recorded
    through the verified /api/agent/contact override -- some other,
    unverified path) must never become gate-eligible."""
    calls = []
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: calls.append(a) or (True, "sent"))
    listing = _good_rentcast_listing(source_id="cl-with-contact", contact_email="found@example.com")
    listing.source = "craigslist"
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "no automatable contact (Craigslist has no real send address)"
    assert newly_emailed == set()
    assert calls == []


def test_craigslist_listing_with_a_verified_contact_override_can_auto_send(monkeypatch):
    """The intended new capability: a Craigslist listing whose contact was
    found and recorded through the verified override path (contact_source
    set -- see POST /api/agent/contact) is treated exactly like a
    RentCast-provided contact once every other rule clears. The owner asked
    for Craigslist research specifically so a real, direct email -- either
    one the poster gave in their own listing text, or one found the same way
    as for RentCast -- can be emailed directly instead of only ever getting
    a manual reply-box draft."""
    sent = {}
    monkeypatch.setattr(
        "rental_finder.outreach.send_email",
        lambda to, subject, body, settings: (sent.setdefault("to", to), (True, "sent"))[1],
    )
    listing = _good_rentcast_listing(source_id="cl-verified", contact_email="landlord@example.com")
    listing.source = "craigslist"
    listing.contact_source = "AI research (high confidence): https://example.com/listing"
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "sent"
    assert newly_emailed == {"cl-verified"}
    assert sent["to"] == "landlord@example.com"


def test_craigslist_listing_without_a_verified_address_is_not_offered_as_a_draft_candidate():
    """Regression test: the contact-email check must never short-circuit
    ahead of address/spam/buffer for Craigslist, or 'no automatable contact'
    (which the Worker's /api/agent/candidates treats as "ready to draft")
    would become the reason for EVERY Craigslist listing regardless of
    whether it actually cleared anything else."""
    listing = _good_rentcast_listing(source_id="cl-no-address", contact_email=None)
    listing.source = "craigslist"
    listing.location_precision = PRECISION_AREA
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "no verified address"
    assert newly_emailed == set()


def test_craigslist_listing_that_is_spam_flagged_is_not_offered_as_a_draft_candidate():
    listing = _good_rentcast_listing(source_id="cl-spam", contact_email=None)
    listing.source = "craigslist"
    listing.spam_score = 2
    process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "spam-flagged"


def test_already_emailed_listing_is_skipped():
    listing = _good_rentcast_listing(source_id="rc2")
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed={"rc2"})
    assert listing.outreach_result == "already contacted"
    assert newly_emailed == set()


def test_area_precision_listing_never_auto_sends():
    listing = _good_rentcast_listing()
    listing.location_precision = PRECISION_AREA
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "no verified address"
    assert newly_emailed == set()


def test_spam_flagged_listing_never_auto_sends():
    listing = _good_rentcast_listing()
    listing.spam_score = 2
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "spam-flagged"


def test_listing_too_close_never_auto_sends():
    listing = _good_rentcast_listing()
    listing.nearest_facility_ft = {"school": 200.0}
    listing.facility_checked = {"school": True}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert "1000 ft" in listing.outreach_result
    assert newly_emailed == set()


def test_unverified_distance_never_auto_sends():
    listing = _good_rentcast_listing()
    listing.facility_checked = {"school": False}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "facility distance unverified"


def test_send_failure_is_reported_and_not_marked_emailed(monkeypatch):
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: (False, "SMTP error: boom"))
    listing = _good_rentcast_listing()
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set())
    assert listing.outreach_result == "send failed: SMTP error: boom"
    assert newly_emailed == set()


def test_company_flagged_listing_never_auto_sends(monkeypatch):
    """The Foundation Group incident this was built for: a listing that
    clears every other rule (address, spam, buffer, has a contact_email)
    must still be blocked once its contact_email matches a recorded company
    note -- regardless of which address or posting it's attached to."""
    calls = []
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: calls.append(a) or (True, "sent"))
    listing = _good_rentcast_listing(source_id="rc-flagged", contact_email="info@foundationgroupre.com")
    company_notes = {"info@foundationgroupre.com": ("The Foundation Group LLC", "wouldn't pass screening")}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set(), company_notes=company_notes)
    assert listing.outreach_result == "company flagged (The Foundation Group LLC): wouldn't pass screening"
    assert newly_emailed == set()
    assert calls == []


def test_company_note_lookup_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: (True, "sent"))
    listing = _good_rentcast_listing(source_id="rc-flagged-2", contact_email="  Info@FoundationGroupRE.com  ")
    company_notes = {"info@foundationgroupre.com": (None, "wouldn't pass screening")}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set(), company_notes=company_notes)
    assert listing.outreach_result == "company flagged: wouldn't pass screening"
    assert newly_emailed == set()


def test_company_notes_do_not_affect_unrelated_contacts(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        "rental_finder.outreach.send_email",
        lambda to, subject, body, settings: (sent.setdefault("to", to), (True, "sent"))[1],
    )
    listing = _good_rentcast_listing()
    company_notes = {"someoneelse@example.com": (None, "wouldn't pass screening")}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set(), company_notes=company_notes)
    assert listing.outreach_result == "sent"
    assert newly_emailed == {"rc1"}


def test_craigslist_listing_with_verified_contact_still_blocked_by_company_note(monkeypatch):
    """A company note must apply to a Craigslist listing with a VERIFIED
    contact override too, not just RentCast -- the block is on the company,
    not the source."""
    calls = []
    monkeypatch.setattr("rental_finder.outreach.send_email", lambda *a, **k: calls.append(a) or (True, "sent"))
    listing = _good_rentcast_listing(source_id="cl-flagged", contact_email="info@foundationgroupre.com")
    listing.source = "craigslist"
    listing.contact_source = "AI research (high confidence): https://example.com/listing"
    company_notes = {"info@foundationgroupre.com": ("The Foundation Group LLC", "wouldn't pass screening")}
    newly_emailed = process([listing], SETTINGS, COMPLETE_PROFILE, already_emailed=set(), company_notes=company_notes)
    assert listing.outreach_result == "company flagged (The Foundation Group LLC): wouldn't pass screening"
    assert newly_emailed == set()
    assert calls == []
