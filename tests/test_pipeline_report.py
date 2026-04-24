"""pipeline_report.py の region×kind バケット別メトリクスの検証。"""

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pipeline_report as pr


def _setup_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.executescript(
        """
        create table articles (
          id integer primary key,
          source text,
          title text,
          url text,
          url_norm text,
          content text,
          category text,
          published_at text,
          fetched_at text,
          kind text default 'tech',
          region text default '',
          title_ja text,
          source_tier text
        );
        create table topics (
          id integer primary key,
          title text,
          title_ja text,
          category text,
          score_48h integer default 0,
          created_at text,
          topic_key text,
          kind text default 'tech',
          region text default ''
        );
        create table topic_articles (topic_id integer, article_id integer);
        create table topic_insights (
          topic_id integer primary key,
          importance integer,
          type text,
          summary text
        );
        create table category_trends (
          report_date text,
          category text,
          articles_count integer,
          topics_count integer,
          primary key (report_date, category)
        );
        """
    )

    # 各バケットに記事＋トピックを作る。insight を付けるのは1バケットのみ
    bucket_samples = [
        (1, "news", "global", 1),  # global_news: topic 1, article 10, insight あり
        (2, "news", "global", 0),  # global_news: insight 無し
        (3, "news", "jp", 0),       # jp_news
        (4, "tech", "jp", 0),       # jp_tech
        (5, "tech", "global", 0),   # global_tech
    ]
    for tid, kind, region, has_insight in bucket_samples:
        aid = 10 + tid
        cur.execute(
            "insert into articles (id, source, title, url, url_norm, kind, region, category, published_at, fetched_at) "
            "values (?, 'src', 't', 'https://x/' || ?, '', ?, ?, ?, '2026-04-24T00:00:00+00:00', '2026-04-24T01:00:00+00:00')",
            (aid, aid, kind, region, "news" if kind == "news" else "security"),
        )
        cur.execute("insert into topics (id, title, category, kind, region) values (?, 't', ?, ?, ?)", (tid, "news" if kind == "news" else "security", kind, region))
        cur.execute("insert into topic_articles values (?, ?)", (tid, aid))
        if has_insight:
            cur.execute("insert into topic_insights (topic_id, importance, summary) values (?, 50, 'ok')", (tid,))

    conn.commit()
    conn.close()


def test_count_db_stats_includes_bucket_breakdown(tmp_path: Path):
    db = tmp_path / "state.sqlite"
    _setup_db(db)

    stats = pr._count_db_stats(db)

    # topics 5、insight 付き 1 → 未生成 4
    assert stats["topics"] == 5
    assert stats["topics_without_insight"] == 4

    buckets = stats["topics_without_insight_by_bucket"]
    # global_news は 2 件中 1 件 insight 済み → 1 件未生成
    assert buckets.get("global_news") == 1
    assert buckets.get("jp_news") == 1
    assert buckets.get("jp_tech") == 1
    assert buckets.get("global_tech") == 1
    # 閾値 WARN のインスタンス（大量未生成を強めた確認用）
    assert isinstance(pr.INSIGHT_BACKLOG_WARN_THRESHOLD, int)
    assert pr.INSIGHT_BACKLOG_WARN_THRESHOLD >= 1


def test_count_db_stats_without_region_column_returns_empty_buckets(tmp_path: Path):
    """articles に region カラムが無い古い DB でも壊れないことを確認。"""
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.executescript(
        """
        create table articles (id integer primary key, kind text, category text, published_at text, fetched_at text);
        create table topics (id integer primary key, category text);
        create table topic_articles (topic_id integer, article_id integer);
        create table topic_insights (topic_id integer primary key, importance integer, summary text);
        create table category_trends (report_date text, category text, articles_count integer, topics_count integer, primary key(report_date, category));
        """
    )
    cur.execute("insert into articles values (1, 'news', 'news', '2026-04-24', '2026-04-24')")
    cur.execute("insert into topics values (1, 'news')")
    cur.execute("insert into topic_articles values (1, 1)")
    conn.commit()
    conn.close()

    stats = pr._count_db_stats(db)
    assert stats["topics_without_insight_by_bucket"] == {}
