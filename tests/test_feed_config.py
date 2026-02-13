from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from collect import load_feed_list


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
            "source_tier": "secondary",
            "kind": "tech",
            "region": "global",
            "limit": 10,
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
                "rss": [
                    "https://example.com/a.xml",
                    {"url": "https://example.com/b.xml", "category": "security", "limit": 5, "source_tier": "secondary"},
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
            "source_tier": "primary",
            "kind": "tech",
            "region": "jp",
            "limit": 20,
        },
        {
            "url": "https://example.com/b.xml",
            "category": "security",
            "source": "SourceA",
            "source_tier": "secondary",
            "kind": "tech",
            "region": "jp",
            "limit": 5,
        },
    ]
