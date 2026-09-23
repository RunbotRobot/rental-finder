from rental_finder.applicant_profile import ApplicantProfile
from rental_finder.email_draft import build_draft
from rental_finder.models import Listing


def _listing(**kwargs) -> Listing:
    defaults = dict(
        source="rentcast", source_id="1", url="https://example.com/1", title="Apartment at 1 Main St",
        price=1500.0, category="Apartment", location_text="1 Main St, Kent, WA", bedrooms=1,
    )
    defaults.update(kwargs)
    return Listing(**defaults)


COMPLETE_PROFILE = ApplicantProfile(
    name="Alex Applicant",
    phone="555-123-4567",
    email="alex@example.com",
    move_in_date="October 1",
    income_text="I'll be earning $3,800/month starting in September.",
    employment_text="I'm starting a new position in airport ground operations.",
    disclosure_text="I want to be upfront: I am a registered sex offender under community supervision.",
)


def test_incomplete_profile_produces_no_draft():
    assert build_draft(_listing(), ApplicantProfile()) is None
    assert build_draft(_listing(), ApplicantProfile(name="Alex")) is None  # no disclosure text
    assert build_draft(_listing(), ApplicantProfile(disclosure_text="...")) is None  # no name


def test_complete_profile_produces_a_draft():
    result = build_draft(_listing(), COMPLETE_PROFILE)
    assert result is not None
    subject, body = result
    assert "1 Main St" in subject
    assert "1-bedroom" in body
    assert "$1,500" in body


def test_disclosure_text_appears_verbatim_and_unedited():
    _, body = build_draft(_listing(), COMPLETE_PROFILE)
    assert COMPLETE_PROFILE.disclosure_text in body


def test_signature_includes_contact_info():
    _, body = build_draft(_listing(), COMPLETE_PROFILE)
    for field in (COMPLETE_PROFILE.name, COMPLETE_PROFILE.phone, COMPLETE_PROFILE.email):
        assert field in body


def test_optional_fields_are_omitted_when_blank():
    minimal = ApplicantProfile(name="Alex", disclosure_text="My disclosure.")
    _, body = build_draft(_listing(), minimal)
    assert "My disclosure." in body
    assert "Alex" in body


def test_studio_wording():
    _, body = build_draft(_listing(bedrooms=0), COMPLETE_PROFILE)
    assert "studio" in body
