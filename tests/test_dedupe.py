from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import dedupe
from dedupe import category_threshold, normalize_title, normalize_url, _composite_score


def test_normalize_title_standardizes_case_symbols_and_spacing():
    title = "  OpenAI、GPT-5  発表!!!  "
    assert normalize_title(title) == "openai gpt 5 発表"


def test_normalize_url_strips_tracking_and_www():
    url = "https://www.example.com/path/?utm_source=x&a=1#frag"
    assert normalize_url(url) == "https://example.com/path?a=1"


def test_category_threshold_uses_default_for_unknown():
    assert category_threshold("security") == 90
    assert category_threshold("unknown") == 91


def test_composite_score_prefers_higher_inputs():
    score_similar = _composite_score(95.0, 100.0)
    score_different = _composite_score(60.0, 20.0)
    assert score_similar > score_different


def _run_dedupe_for_db(db_path: Path):
    def _connect_override():
        return sqlite3.connect(db_path)

    original_connect = dedupe.connect
    dedupe.connect = _connect_override
    try:
        dedupe.main()
    finally:
        dedupe.connect = original_connect

    conn = sqlite3.connect(db_path)
    try:
        remaining_ids = [r[0] for r in conn.execute("SELECT id FROM articles ORDER BY id").fetchall()]
        judgments = conn.execute(
            "SELECT article_id, kept_article_id, reason FROM dedupe_judgments ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return remaining_ids, judgments


def _prepare_articles_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE articles (
          id INTEGER PRIMARY KEY,
          source TEXT,
          category TEXT,
          title TEXT,
          url TEXT,
          url_norm TEXT
        )
        """
    )

    rows = [
        (10, "srcA", "business", "Apple posts record Q4 earnings in 2025", "https://news.example.com/apple-q4", None),
        (9, "srcB", "business", "Apple posts record Q4 earnings for 2025", "https://mirror.example.net/apple-q4-earnings", None),
        (8, "srcC", "business", "Completely unrelated long analytical macroeconomics bulletin", "https://news.example.com/macro", None),
        (7, "srcD", "business", "Completely different retail outlook briefing", "https://news.example.com/retail", None),
    ]
    cur.executemany("INSERT INTO articles(id, source, category, title, url, url_norm) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_candidate_prefilter_keeps_duplicate_decision_unchanged(tmp_path):
    base_db = tmp_path / "with_filter.sqlite"
    nofilter_db = tmp_path / "without_filter.sqlite"
    _prepare_articles_db(base_db)
    _prepare_articles_db(nofilter_db)

    remaining_filtered, judgments_filtered = _run_dedupe_for_db(base_db)

    old_token_diff = dedupe.MAX_TOKEN_COUNT_DIFF
    old_char_diff = dedupe.MAX_TITLE_LENGTH_DIFF
    dedupe.MAX_TOKEN_COUNT_DIFF = 10_000
    dedupe.MAX_TITLE_LENGTH_DIFF = 10_000
    try:
        remaining_unfiltered, judgments_unfiltered = _run_dedupe_for_db(nofilter_db)
    finally:
        dedupe.MAX_TOKEN_COUNT_DIFF = old_token_diff
        dedupe.MAX_TITLE_LENGTH_DIFF = old_char_diff

    assert remaining_filtered == remaining_unfiltered
    assert judgments_filtered == judgments_unfiltered
