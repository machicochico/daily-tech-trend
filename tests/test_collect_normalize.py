from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import (
    MIN_CONTENT_CHARS,
    normalize_url,
    should_fetch_fulltext,
    should_route_to_low_priority,
    resolve_week_key,
    is_arxiv_feed,
    matches_manufacturing_keywords,
    build_manufacturing_keyword_pattern,
    load_manufacturing_keywords,
)


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


def test_resolve_week_key_prefers_published_at():
    assert resolve_week_key("2026-01-05T01:02:03+00:00", "2026-02-01T01:00:00+00:00") == "2026-02"


def test_should_route_to_low_priority_only_when_new_and_limit_exceeded():
    assert should_route_to_low_priority(is_new=True, current_new_count=5, weekly_limit=5)
    assert not should_route_to_low_priority(is_new=False, current_new_count=99, weekly_limit=1)
    assert not should_route_to_low_priority(is_new=True, current_new_count=1, weekly_limit=None)



def test_is_arxiv_feed_detects_source_vendor_or_url():
    assert is_arxiv_feed({"source": "arXiv AI (cs.AI)"})
    assert is_arxiv_feed({"vendor": "arXiv"})
    assert is_arxiv_feed({"url": "http://export.arxiv.org/rss/cs.LG"})
    assert not is_arxiv_feed({"source": "OpenAI News", "url": "https://openai.com/news/rss.xml"})


def test_matches_manufacturing_keywords_works_with_external_dictionary(tmp_path):
    keywords_file = tmp_path / "keywords.yaml"
    keywords_file.write_text("keywords:\n  - steel\n  - 高炉\n", encoding="utf-8")

    load_manufacturing_keywords.cache_clear()
    build_manufacturing_keyword_pattern.cache_clear()

    assert load_manufacturing_keywords(str(keywords_file)) == ("steel", "高炉")
    assert build_manufacturing_keyword_pattern(str(keywords_file)).search("new steel process")

    assert matches_manufacturing_keywords("Advanced Steel Control", "")
    assert not matches_manufacturing_keywords("Large Language Models", "benchmark only")

    load_manufacturing_keywords.cache_clear()
    build_manufacturing_keyword_pattern.cache_clear()
