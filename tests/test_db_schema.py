from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import db


def test_init_db_creates_required_tables_and_columns(tmp_path):
    db.DB_PATH = tmp_path / "state.sqlite"

    db.init_db()

    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}

    for t in {"articles", "topics", "topic_articles", "topic_insights", "edges", "low_priority_articles"}:
        assert t in tables

    cur.execute("PRAGMA table_info(topics)")
    topic_columns = {row[1] for row in cur.fetchall()}
    assert {"topic_key", "kind", "region"}.issubset(topic_columns)

    cur.execute("PRAGMA table_info(articles)")
    article_columns = {row[1] for row in cur.fetchall()}
    assert "source_tier" in article_columns

    conn.close()



def test_init_db_creates_low_priority_queue_index(tmp_path):
    db.DB_PATH = tmp_path / "state.sqlite"
    db.init_db()

    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='low_priority_articles'")
    indexes = {row[0] for row in cur.fetchall()}
    assert "idx_low_priority_articles_url" in indexes

    conn.close()
