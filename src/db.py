# src/db.py
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/state.sqlite")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = connect()
    cur = conn.cursor()

    # ---- articles ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS articles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT,                -- 'tech' / 'news'
      region TEXT,              -- 'jp' / 'global' など
      source TEXT,
      title TEXT,
      title_ja TEXT,
      url TEXT,
      url_norm TEXT,
      content TEXT,
      category TEXT,
      published_at TEXT,
      fetched_at TEXT
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url
    ON articles(url)
    """)

    # ---- articles: 後方互換（既存DBに列が無い場合の追加）----
    ensure_column(cur, "articles", "kind", "TEXT")
    ensure_column(cur, "articles", "region", "TEXT")
    ensure_column(cur, "articles", "title_ja", "TEXT")

    # 既存データの最低限のデフォルト補完（NULL/空のみ対象）
    cur.execute("UPDATE articles SET kind='tech' WHERE kind IS NULL OR kind=''")
    cur.execute("UPDATE articles SET region='global' WHERE region IS NULL OR region=''")


    # ---- topics ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic_key TEXT,
      title TEXT,
      title_ja TEXT,
      category TEXT,
      kind TEXT,
      region TEXT,
      score_48h INTEGER DEFAULT 0,
      created_at TEXT
    )
    """)

    # ---- topics: 後方互換（既存DBに列が無い場合の追加）----
    ensure_column(cur, "topics", "topic_key", "TEXT")
    ensure_column(cur, "topics", "kind", "TEXT")
    ensure_column(cur, "topics", "region", "TEXT")

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_topics_topic_key
    ON topics(topic_key)
    WHERE topic_key IS NOT NULL AND topic_key != ''
    """)

    # 既存データ移行: NULL/空のみデフォルト補完
    cur.execute("UPDATE topics SET kind='tech' WHERE kind IS NULL OR kind=''")
    cur.execute("UPDATE topics SET region='global' WHERE region IS NULL OR region=''")

    # ---- topic_articles ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_articles (
      topic_id INTEGER,
      article_id INTEGER,
      PRIMARY KEY (topic_id, article_id)
    )
    """)

    # ---- edges (topic内の親子リンク) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS edges (
      topic_id INTEGER,
      parent_article_id INTEGER,
      child_article_id INTEGER
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_topic_parent_child
    ON edges(topic_id, parent_article_id, child_article_id)
    """)

    # ---- topic_insights (LLM結果) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_insights (
      topic_id INTEGER PRIMARY KEY,
      importance INTEGER,
      type TEXT,
      summary TEXT,
      key_points TEXT,
      impact_guess TEXT,
      next_actions TEXT,
      evidence_urls TEXT,
      tags TEXT,
      perspectives TEXT,          
      updated_at TEXT
    )
    """)

    ensure_column(cur, "topic_insights", "tags", "TEXT")
    ensure_column(cur, "topic_insights", "perspectives", "TEXT")
    ensure_column(cur, "topic_insights", "evidence_urls", "TEXT")
    ensure_column(cur, "topic_insights", "src_article_id", "INTEGER")
    ensure_column(cur, "topic_insights", "src_hash", "TEXT")


    conn.commit()
    conn.close()

def ensure_column(cur, table: str, col: str, coltype: str):
    cur.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def recompute_score_48h():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    UPDATE topics
    SET score_48h = (
      SELECT COUNT(*)
      FROM topic_articles ta
      JOIN articles a ON a.id = ta.article_id
      WHERE ta.topic_id = topics.id
        AND datetime(a.published_at) >= datetime('now', '-48 hours')
    )
    """)

    conn.commit()
    conn.close()


def now():
    return datetime.utcnow().isoformat(timespec="seconds")
