from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import normalize_url


def test_normalize_url_removes_tracking_query_and_fragment():
    url = "https://example.com/path?a=1&utm_source=x&fbclid=y#section"
    assert normalize_url(url) == "https://example.com/path?a=1"


def test_normalize_url_keeps_non_tracking_query():
    url = "https://example.com/path?ref=drop&lang=ja&utm_medium=social"
    assert normalize_url(url) == "https://example.com/path?lang=ja"


def test_normalize_url_preserves_blank_query_values():
    url = "https://example.com/path?lang=&utm_campaign=test"
    assert normalize_url(url) == "https://example.com/path?lang="


def test_normalize_url_without_query_is_unchanged_except_fragment_removed():
    url = "https://example.com/path#frag"
    assert normalize_url(url) == "https://example.com/path"
