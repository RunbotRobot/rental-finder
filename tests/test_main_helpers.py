import csv
import json

from rental_finder.main import (
    load_company_notes,
    load_contact_overrides,
    load_contact_overrides_by_address,
    load_emailed_ids,
    load_manual_listing_urls,
)


def test_missing_file_is_empty_set(tmp_path):
    assert load_emailed_ids(tmp_path / "missing.json") == set()


def test_manual_listing_urls_missing_file_is_empty_list(tmp_path):
    assert load_manual_listing_urls(tmp_path / "missing.txt") == []


def test_manual_listing_urls_skips_blank_lines_and_comments(tmp_path):
    path = tmp_path / "manual_listings.txt"
    path.write_text(
        "# manually-added listings\nhttps://www.craigslist.org/view/d/one/abc\n\n"
        "  https://www.craigslist.org/view/d/two/def  \n# another comment\n",
        encoding="utf-8",
    )
    assert load_manual_listing_urls(path) == [
        "https://www.craigslist.org/view/d/one/abc",
        "https://www.craigslist.org/view/d/two/def",
    ]


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


def _write_overrides_csv_with_contact_address(path, rows):
    """Like _write_overrides_csv, but with the newer 6th contact_address
    column -- the listing's own address at the moment a contact was
    recorded, written by the Worker (see worker/src/index.js's
    /api/agent/contact), which load_contact_overrides_by_address() keys on.
    Uses csv.writer (unlike _write_overrides_csv's naive join) since a real
    address routinely contains a comma, which the address-matching feature
    exists specifically to handle correctly."""
    header = ["source_id", "address", "contact_name", "contact_email", "contact_source", "contact_address"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def test_contact_overrides_by_address_missing_file_is_empty_dict(tmp_path):
    assert load_contact_overrides_by_address(tmp_path / "missing.csv") == {}


def test_contact_overrides_by_address_full_row_is_loaded(tmp_path):
    path = tmp_path / "overrides.csv"
    _write_overrides_csv_with_contact_address(
        path,
        [
            (
                "cl1",
                "",
                "Jane Doe",
                "jane@example.com",
                "AI research (high confidence): https://example.com/listing",
                "1210 N 152nd St, Shoreline",
            )
        ],
    )
    result = load_contact_overrides_by_address(path)
    assert result == {
        "1210 N 152nd St, Shoreline": (
            "Jane Doe",
            "jane@example.com",
            "AI research (high confidence): https://example.com/listing",
        )
    }


def test_contact_overrides_by_address_row_without_a_contact_address_is_skipped(tmp_path):
    """A row recorded before this column existed, or for a listing that had
    already dropped out of the current scan when the contact was written (so
    the Worker had nothing to look up), has no contact_address -- this
    fallback just doesn't apply for it, same as if it were never there. The
    id-keyed override from load_contact_overrides is unaffected either way."""
    path = tmp_path / "overrides.csv"
    _write_overrides_csv_with_contact_address(
        path, [("cl2", "", "Jane Doe", "jane@example.com", "AI research: https://example.com", "")]
    )
    assert load_contact_overrides_by_address(path) == {}


def test_contact_overrides_by_address_row_without_a_source_is_skipped(tmp_path):
    path = tmp_path / "overrides.csv"
    _write_overrides_csv_with_contact_address(
        path, [("cl3", "", "Jane Doe", "jane@example.com", "", "1210 N 152nd St, Shoreline")]
    )
    assert load_contact_overrides_by_address(path) == {}


def test_contact_overrides_by_address_ignores_older_5_column_rows(tmp_path):
    """A CSV written before this column existed (5 columns, no
    contact_address) must not crash this reader -- it just finds nothing to
    key on, since csv.DictReader leaves the missing trailing field as None."""
    path = tmp_path / "overrides.csv"
    _write_overrides_csv(
        path,
        [("rc1", "", "Jane Doe", "jane@example.com", "AI research (high confidence): https://example.com/listing")],
    )
    assert load_contact_overrides_by_address(path) == {}


def test_company_notes_missing_file_is_empty_dict(tmp_path):
    assert load_company_notes(tmp_path / "missing.json") == {}


def test_company_notes_full_entry_is_loaded_and_normalized(tmp_path):
    path = tmp_path / "company_notes.json"
    path.write_text(
        json.dumps(
            {
                "Info@FoundationGroupRE.com  ": {
                    "contact_email": "Info@FoundationGroupRE.com",
                    "company": "The Foundation Group LLC",
                    "note": "Told directly applicant wouldn't pass screening (guarantor situation).",
                    "updated": "2026-09-25T00:00:00.000Z",
                }
            }
        ),
        encoding="utf-8",
    )
    result = load_company_notes(path)
    assert result == {
        "info@foundationgroupre.com": (
            "The Foundation Group LLC",
            "Told directly applicant wouldn't pass screening (guarantor situation).",
        )
    }


def test_company_notes_missing_note_is_skipped(tmp_path):
    path = tmp_path / "company_notes.json"
    path.write_text(json.dumps({"a@example.com": {"company": "A LLC", "note": "  "}}), encoding="utf-8")
    assert load_company_notes(path) == {}


def test_company_notes_missing_company_is_none(tmp_path):
    path = tmp_path / "company_notes.json"
    path.write_text(json.dumps({"a@example.com": {"note": "not worth contacting"}}), encoding="utf-8")
    assert load_company_notes(path) == {"a@example.com": (None, "not worth contacting")}


def test_company_notes_unreadable_file_is_empty_dict(tmp_path):
    path = tmp_path / "company_notes.json"
    path.write_text("not json", encoding="utf-8")
    assert load_company_notes(path) == {}


def test_company_notes_non_dict_json_is_empty_dict(tmp_path):
    path = tmp_path / "company_notes.json"
    path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert load_company_notes(path) == {}
