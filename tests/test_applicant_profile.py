import json

from rental_finder.applicant_profile import ApplicantProfile, load_profile


def test_missing_file_is_empty_and_incomplete(tmp_path):
    profile = load_profile(tmp_path / "does_not_exist.json")
    assert profile == ApplicantProfile()
    assert not profile.is_complete()


def test_loads_fields_from_file(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"name": "Alex", "disclosure_text": "My disclosure."}), encoding="utf-8")
    profile = load_profile(path)
    assert profile.name == "Alex"
    assert profile.disclosure_text == "My disclosure."
    assert profile.is_complete()


def test_unreadable_json_falls_back_to_empty(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text("not json", encoding="utf-8")
    assert load_profile(path) == ApplicantProfile()


def test_missing_disclosure_is_incomplete():
    assert not ApplicantProfile(name="Alex").is_complete()


def test_missing_name_is_incomplete():
    assert not ApplicantProfile(disclosure_text="text").is_complete()
