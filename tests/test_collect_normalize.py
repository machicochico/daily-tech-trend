from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import (
    FAILURE_THRESHOLD,
    SUSPEND_HOURS,
    MIN_CONTENT_CHARS,
    normalize_url,
    should_fetch_fulltext,
    should_route_to_low_priority,
    resolve_week_key,
    is_arxiv_feed,
    matches_manufacturing_keywords,
    build_manufacturing_keyword_pattern,
    load_manufacturing_keywords,
    get_feed_health,
    mark_feed_failure,
    mark_feed_success,
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


def test_feed_health_failure_then_success_flow(tmp_path):
    import sqlite3
    from datetime import datetime, timedelta, timezone

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE feed_health (
            feed_url TEXT PRIMARY KEY,
            failure_count INTEGER DEFAULT 0,
            last_success_at TEXT,
            last_failure_reason TEXT,
            suspend_until TEXT
        )
        """
    )

    feed = {"url": "https://example.com/rss.xml", "source": "example"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    for _ in range(FAILURE_THRESHOLD):
        mark_feed_failure(cur, feed=feed, error_type="parse_error", now_iso=now_iso)

    health = get_feed_health(cur, feed["url"])
    assert health["failure_count"] == FAILURE_THRESHOLD
    assert health["last_failure_reason"] == "parse_error"

    suspend_until = datetime.fromisoformat(health["suspend_until"])
    assert suspend_until >= now + timedelta(hours=SUSPEND_HOURS)

    success_time = (now + timedelta(hours=1)).isoformat(timespec="seconds")
    mark_feed_success(cur, feed=feed, now_iso=success_time)
    health_after_success = get_feed_health(cur, feed["url"])
    assert health_after_success["failure_count"] == 0
    assert health_after_success["last_success_at"] == success_time
    assert health_after_success["last_failure_reason"] == ""
    assert health_after_success["suspend_until"] == ""
