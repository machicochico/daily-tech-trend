import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_insights_pipeline import pick_topic_inputs


def _setup_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        create table topics (
          id integer primary key,
          title text,
          title_ja text,
          category text,
          score_48h integer
        )
        """
    )
    cur.execute(
        """
        create table articles (
          id integer primary key,
          kind text,
          source text,
          title text,
          title_ja text,
          url text,
          content text,
          category text,
          published_at text,
          fetched_at text
        )
        """
    )
    cur.execute("create table topic_articles (topic_id integer, article_id integer)")
    cur.execute(
        """
        create table topic_insights (
          topic_id integer primary key,
          importance integer,
          summary text,
          src_hash text
        )
        """
    )
    return conn


def test_pick_topic_inputs_rescue_reingests_news_even_if_already_processed():
    conn = _setup_db()
    cur = conn.cursor()

    cur.execute("insert into topics values (1, 't1', 'ニュース1', 'news', 3)")
    cur.execute(
        "insert into articles values (10, 'news', 'Reuters', 'title', 'タイトル', 'https://example.com/n', '本文', 'news', '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')"
    )
    cur.execute("insert into topic_articles values (1, 10)")
    cur.execute("insert into topic_insights values (1, 50, 'ok', 'hash-ok')")
    conn.commit()

    normal_rows = pick_topic_inputs(conn, rescue=False)
    rescue_rows = pick_topic_inputs(conn, rescue=True)

    assert len(normal_rows) == 0
    assert len(rescue_rows) == 1
    assert rescue_rows[0]["topic_id"] == 1


def test_pick_topic_inputs_rescue_does_not_reingest_completed_tech_by_default():
    conn = _setup_db()
    cur = conn.cursor()

    cur.execute("insert into topics values (2, 't2', '技術2', 'security', 4)")
    cur.execute(
        "insert into articles values (20, 'tech', 'TechCrunch', 'tech title', '技術タイトル', 'https://example.com/t', '本文', 'security', '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')"
    )
    cur.execute("insert into topic_articles values (2, 20)")
    cur.execute("insert into topic_insights values (2, 60, 'ok', 'hash-ok')")
    conn.commit()

    rescue_rows = pick_topic_inputs(conn, rescue=True)

    assert len(rescue_rows) == 0
