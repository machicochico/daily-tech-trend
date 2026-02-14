from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import load_feed_list
from feed_lint import lint_feed_list


def test_load_feed_list_accepts_legacy_feeds_format():
    cfg = {
        "feeds": [
            {
                "url": "https://example.com/feed.xml",
                "category": "ai",
                "source": "Example",
                "kind": "tech",
                "region": "global",
                "limit": 10,
            }
        ]
    }

    feeds = load_feed_list(cfg)

    assert feeds == [
        {
            "url": "https://example.com/feed.xml",
            "category": "ai",
            "source": "Example",
            "vendor": "Example",
            "source_tier": "secondary",
            "kind": "tech",
            "region": "global",
            "limit": 10,
            "weekly_new_limit": None,
            "tls_mode": "strict",
        }
    ]


def test_load_feed_list_accepts_sources_with_rss_string_and_object():
    cfg = {
        "sources": [
            {
                "name": "SourceA",
                "category": "cloud",
                "kind": "tech",
                "region": "jp",
                "source_tier": "primary",
                "limit": 20,
                "weekly_new_limit": 8,
                "rss": [
                    "https://example.com/a.xml",
                    {
                        "url": "https://example.com/b.xml",
                        "category": "security",
                        "limit": 5,
                        "source_tier": "secondary",
                        "vendor": "VendorB",
                        "weekly_new_limit": 3,
                    },
                ],
            }
        ]
    }

    feeds = load_feed_list(cfg)

    assert feeds == [
        {
            "url": "https://example.com/a.xml",
            "category": "cloud",
            "source": "SourceA",
            "vendor": "SourceA",
            "source_tier": "primary",
            "kind": "tech",
            "region": "jp",
            "limit": 20,
            "weekly_new_limit": 8,
            "tls_mode": "strict",
        },
        {
            "url": "https://example.com/b.xml",
            "category": "security",
            "source": "SourceA",
            "vendor": "VendorB",
            "source_tier": "secondary",
            "kind": "tech",
            "region": "jp",
            "limit": 5,
            "weekly_new_limit": 3,
            "tls_mode": "strict",
        },
    ]


def test_feed_lint_detects_duplicates_and_warnings():
    feeds = [
        {"url": "http://example.com/about", "source": "A", "category": "x"},
        {"url": "http://example.com/about?utm_source=a", "source": "B", "category": "y"},
        {"url": "https://dup.example.com/feed.xml", "source": "C", "category": "z"},
        {"url": "https://dup.example.com/feed.xml", "source": "D", "category": "z2"},
    ]

    issues = lint_feed_list(feeds)
    issue_codes = {issue.code for issue in issues}

    assert "duplicate-exact-url" in issue_codes
    assert "duplicate-normalized-url" in issue_codes
    assert "http-url" in issue_codes
    assert "non-rss-heuristic" in issue_codes
