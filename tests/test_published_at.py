from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backfill_published_at import norm
from collect import normalize_published_at


def test_backfill_norm_supports_iso8601_and_z_and_rfc2822():
    assert norm("2024-01-02T03:04:05+09:00") == "2024-01-01T18:04:05+00:00"
    assert norm("2024-01-02T03:04:05Z") == "2024-01-02T03:04:05+00:00"
    assert norm("Tue, 02 Jan 2024 03:04:05 GMT") == "2024-01-02T03:04:05+00:00"


def test_normalize_published_at_supports_rfc2822_and_z_notation_via_struct_time():
    rfc_entry = SimpleNamespace(published="Tue, 02 Jan 2024 03:04:05 GMT")
    assert normalize_published_at(rfc_entry) == "2024-01-02T03:04:05+00:00"

    z_entry = SimpleNamespace(
        published="2024-01-02T03:04:05Z",
        published_parsed=(2024, 1, 2, 3, 4, 5, 1, 2, 0),
    )
    assert normalize_published_at(z_entry) == "2024-01-02T03:04:05+00:00"


def test_normalize_published_at_returns_empty_for_unparseable_iso8601_string():
    iso_entry = SimpleNamespace(published="2024-01-02T03:04:05+09:00")
    assert normalize_published_at(iso_entry) == ""
