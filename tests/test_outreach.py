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
