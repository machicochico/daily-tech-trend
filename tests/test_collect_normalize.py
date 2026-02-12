from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import MIN_CONTENT_CHARS, normalize_url, should_fetch_fulltext


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


def test_should_fetch_fulltext_when_content_is_thin():
    thin_content = "a" * (MIN_CONTENT_CHARS - 1)
    assert should_fetch_fulltext("Forest Watch", thin_content, fetch_count=0, fetch_limit=30)


def test_should_not_fetch_fulltext_when_source_is_not_targeted():
    assert not should_fetch_fulltext("Other Source", "", fetch_count=0, fetch_limit=30)


def test_should_not_fetch_fulltext_when_limit_reached():
    assert not should_fetch_fulltext("Forest Watch", "", fetch_count=30, fetch_limit=30)


def test_should_not_fetch_fulltext_when_content_is_sufficient():
    rich_content = "a" * MIN_CONTENT_CHARS
    assert not should_fetch_fulltext("Forest Watch", rich_content, fetch_count=0, fetch_limit=30)
