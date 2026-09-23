import json

from rental_finder.main import load_emailed_ids


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
