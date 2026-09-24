import json

from rental_finder.main import load_contact_overrides, load_emailed_ids


def test_missing_file_is_empty_set(tmp_path):
    assert load_emailed_ids(tmp_path / "missing.json") == set()


def test_loads_ids_from_file(tmp_path):
    path = tmp_path / "emailed.json"
    path.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert load_emailed_ids(path) == {"a", "b"}


def test_unreadable_file_is_empty_set(tmp_path):
    path = tmp_path / "emailed.json"
    path.write_text("not json", encoding="utf-8")
    assert load_emailed_ids(path) == set()


def _write_overrides_csv(path, rows):
    header = "source_id,address,contact_name,contact_email,contact_source"
    lines = [header] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_contact_overrides_missing_file_is_empty_dict(tmp_path):
    assert load_contact_overrides(tmp_path / "missing.csv") == {}


def test_contact_overrides_full_row_is_loaded(tmp_path):
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(
        path,
        [("rc1", "", "Jane Doe", "jane@example.com", "AI research (high confidence): https://example.com/listing")],
    )
    result = load_contact_overrides(path)
    assert result == {
        "rc1": ("Jane Doe", "jane@example.com", "AI research (high confidence): https://example.com/listing")
    }


def test_contact_overrides_missing_name_is_none(tmp_path):
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(path, [("rc2", "", "", "office@example.com", "AI research: https://example.com")])
    result = load_contact_overrides(path)
    assert result == {"rc2": (None, "office@example.com", "AI research: https://example.com")}


def test_contact_overrides_row_without_a_source_is_skipped(tmp_path):
    """contact_source is required -- never applied without a citation of how
    the contact was found, same as every other unverified thing this project
    refuses to trust silently."""
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(path, [("rc3", "", "Jane Doe", "jane@example.com", "")])
    assert load_contact_overrides(path) == {}


def test_contact_overrides_row_without_an_email_is_skipped(tmp_path):
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(path, [("rc4", "", "Jane Doe", "", "AI research: https://example.com")])
    assert load_contact_overrides(path) == {}


def test_contact_overrides_address_only_row_is_ignored(tmp_path):
    """A row that only carries an address override (the pre-existing case)
    has no contact_email/contact_source, so it's simply not in this dict --
    load_overrides handles the address half separately."""
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(path, [("cl1", "123 Main St, Kent, WA", "", "", "")])
    assert load_contact_overrides(path) == {}
