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
      source_tier TEXT,         -- 'primary' / 'secondary'
      published_at TEXT,
      fetched_at TEXT
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url
    ON articles(url)
    """)

    # クエリ性能向上用インデックス
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_articles_category_published
    ON articles(category, published_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_articles_kind_published
    ON articles(kind, published_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_articles_url_norm
    ON articles(url_norm)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_articles_published
    ON articles(published_at DESC)
    """)

    # ---- articles: 後方互換（既存DBに列が無い場合の追加）----
    ensure_column(cur, "articles", "kind", "TEXT")
    ensure_column(cur, "articles", "region", "TEXT")
    ensure_column(cur, "articles", "title_ja", "TEXT")
    ensure_column(cur, "articles", "source_tier", "TEXT")

    # 既存データの最低限のデフォルト補完（NULL/空のみ対象）
    cur.execute("UPDATE articles SET kind='tech' WHERE kind IS NULL OR kind=''")
    cur.execute("UPDATE articles SET region='global' WHERE region IS NULL OR region=''")
    cur.execute(
        "UPDATE articles SET source_tier='secondary' WHERE source_tier IS NULL OR source_tier=''"
    )


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

    # UNIQUE INDEX 作成前に、旧データの topic_key 重複を整理する
    dedupe_topics_by_key(cur)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_topics_topic_key
    ON topics(topic_key)
    WHERE topic_key IS NOT NULL AND topic_key != ''
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_topics_category_created
    ON topics(category, created_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_topics_kind_created
    ON topics(kind, created_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_topics_score_48h
    ON topics(score_48h DESC)
    """)

    # 既存データ移行: NULL/空のみデフォルト補完
    cur.execute("UPDATE topics SET kind='tech' WHERE kind IS NULL OR kind=''")
    cur.execute("UPDATE topics SET region='global' WHERE region IS NULL OR region=''")

    # ---- topic_articles ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_articles (
      topic_id INTEGER,
      article_id INTEGER,
      is_representative INTEGER DEFAULT 0,
      PRIMARY KEY (topic_id, article_id)
    )
    """)
    ensure_column(cur, "topic_articles", "is_representative", "INTEGER DEFAULT 0")

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_topic_articles_article
    ON topic_articles(article_id)
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
    ensure_column(cur, "topic_insights", "perspective_digest", "TEXT")

    # ---- low_priority_articles (source上限超過分の退避キュー) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS low_priority_articles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      url TEXT,
      title TEXT,
      content TEXT,
      source TEXT,
      vendor TEXT,
      category TEXT,
      source_tier TEXT,
      published_at TEXT,
      fetched_at TEXT,
      kind TEXT,
      region TEXT,
      reason TEXT,
      queued_at TEXT
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_low_priority_articles_url
    ON low_priority_articles(url)
    """)

    # ---- feed_health (フィード取得健全性の監視) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feed_health (
      feed_url TEXT PRIMARY KEY,
      failure_count INTEGER DEFAULT 0,
      last_success_at TEXT,
      last_failure_reason TEXT,
      suspend_until TEXT
    )
    """)

    ensure_column(cur, "feed_health", "failure_count", "INTEGER DEFAULT 0")
    ensure_column(cur, "feed_health", "last_success_at", "TEXT")
    ensure_column(cur, "feed_health", "last_failure_reason", "TEXT")
    ensure_column(cur, "feed_health", "suspend_until", "TEXT")


    # ---- forecast_reports (未来予測レポート) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS forecast_reports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      report_date TEXT,
      file_path TEXT,
      executive_summary TEXT,
      created_at TEXT
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_forecast_date
    ON forecast_reports(report_date)
    """)

    # forecast_reports の拡張カラム（検証結果用）
    ensure_column(cur, "forecast_reports", "accuracy_score", "REAL")
    ensure_column(cur, "forecast_reports", "verified_at", "TEXT")
    # forecast_reports の拡張カラム（生成メタ情報）
    ensure_column(cur, "forecast_reports", "model_id", "TEXT")
    ensure_column(cur, "forecast_reports", "temperature_config", "TEXT")

    # ---- forecast_verifications (時間軸別・ラウンド別の検証結果) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS forecast_verifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      report_date TEXT NOT NULL,
      horizon TEXT NOT NULL,
      verification_round INTEGER NOT NULL DEFAULT 1,
      verdict_json TEXT,
      accuracy_score REAL,
      undetermined_count INTEGER DEFAULT 0,
      verified_at TEXT NOT NULL,
      digest_hours INTEGER
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_fv_date_horizon_round
    ON forecast_verifications(report_date, horizon, verification_round)
    """)

    # ---- entities / article_entities (企業・製品・技術エンティティ) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS entities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      slug TEXT NOT NULL,
      kind TEXT,
      aliases TEXT,
      created_at TEXT
    )
    """)
    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_slug
    ON entities(slug)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS article_entities (
      article_id INTEGER NOT NULL,
      entity_id INTEGER NOT NULL,
      confidence REAL DEFAULT 1.0,
      PRIMARY KEY (article_id, entity_id)
    )
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_article_entities_entity
    ON article_entities(entity_id)
    """)

    # ---- topic_snapshots (トピックの日次スナップショット、Diffビュー用) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS topic_snapshots (
      report_date TEXT NOT NULL,
      topic_id INTEGER NOT NULL,
      importance INTEGER,
      category TEXT,
      title TEXT,
      PRIMARY KEY (report_date, topic_id)
    )
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_topic_snapshots_date
    ON topic_snapshots(report_date DESC)
    """)

    # ---- category_trends (カテゴリ別日別統計の履歴) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS category_trends (
      report_date TEXT NOT NULL,
      category TEXT NOT NULL,
      articles_count INTEGER DEFAULT 0,
      topics_count INTEGER DEFAULT 0,
      PRIMARY KEY (report_date, category)
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_category_trends_category
    ON category_trends(category, report_date DESC)
    """)

    # ---- FTS5 全文検索（articles の title / title_ja / content） ----
    # SQLite の FTS5 拡張が有効ならトリガ同期付きで作成する。
    # 拡張不在の古い SQLite でも起動できるよう例外は握りつぶす（検索機能はオプション扱い）。
    try:
        cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title, title_ja, content,
            content='articles',
            content_rowid='id',
            tokenize='unicode61'
        )
        """)
        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_fts_ai AFTER INSERT ON articles BEGIN
          INSERT INTO articles_fts(rowid, title, title_ja, content)
          VALUES (new.id, COALESCE(new.title,''), COALESCE(new.title_ja,''), COALESCE(new.content,''));
        END
        """)
        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_fts_ad AFTER DELETE ON articles BEGIN
          INSERT INTO articles_fts(articles_fts, rowid, title, title_ja, content)
          VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.title_ja,''), COALESCE(old.content,''));
        END
        """)
        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS articles_fts_au AFTER UPDATE ON articles BEGIN
          INSERT INTO articles_fts(articles_fts, rowid, title, title_ja, content)
          VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.title_ja,''), COALESCE(old.content,''));
          INSERT INTO articles_fts(rowid, title, title_ja, content)
          VALUES (new.id, COALESCE(new.title,''), COALESCE(new.title_ja,''), COALESCE(new.content,''));
        END
        """)
        # 空テーブルのときのみ既存データを rebuild で一括投入
        # (content='articles' モードでは 'rebuild' コマンドが正式な初期化手段)
        cur.execute("SELECT COUNT(*) FROM articles_fts")
        fts_count = cur.fetchone()[0]
        if fts_count == 0:
            cur.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
    except sqlite3.OperationalError:
        # FTS5 拡張が無い環境では検索機能を諦める（他機能は継続）。
        pass

    conn.commit()
    conn.close()

import re as _re
_VALID_IDENTIFIER = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def ensure_column(cur, table: str, col: str, coltype: str):
    if not _VALID_IDENTIFIER.match(table):
        raise ValueError(f"Invalid table name: {table!r}")
    if not _VALID_IDENTIFIER.match(col):
        raise ValueError(f"Invalid column name: {col!r}")
    cur.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def dedupe_topics_by_key(cur):
    """
    旧DBで topic_key の重複があると UNIQUE INDEX 作成で失敗するため、
    同一キーの topic を1件に寄せる。
    """
    cur.execute("""
        SELECT topic_key, MIN(id) AS keep_id
        FROM topics
        WHERE topic_key IS NOT NULL AND topic_key != ''
        GROUP BY topic_key
        HAVING COUNT(*) > 1
    """)
    duplicates = cur.fetchall()
    has_topic_articles = table_exists(cur, "topic_articles")
    has_edges = table_exists(cur, "edges")
    has_topic_insights = table_exists(cur, "topic_insights")

    for topic_key, keep_id in duplicates:
        cur.execute(
            "SELECT id FROM topics WHERE topic_key=? AND id<>? ORDER BY id",
            (topic_key, keep_id),
        )
        dup_ids = [row[0] for row in cur.fetchall()]

        for dup_id in dup_ids:
            if has_topic_articles:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO topic_articles(topic_id, article_id)
                    SELECT ?, article_id FROM topic_articles WHERE topic_id=?
                    """,
                    (keep_id, dup_id),
                )
                cur.execute("DELETE FROM topic_articles WHERE topic_id=?", (dup_id,))

            if has_edges:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO edges(topic_id, parent_article_id, child_article_id)
                    SELECT ?, parent_article_id, child_article_id
                    FROM edges
                    WHERE topic_id=?
                    """,
                    (keep_id, dup_id),
                )
                cur.execute("DELETE FROM edges WHERE topic_id=?", (dup_id,))

            if has_topic_insights:
                cur.execute("SELECT 1 FROM topic_insights WHERE topic_id=?", (keep_id,))
                keep_insight = cur.fetchone()
                if not keep_insight:
                    cur.execute(
                        "UPDATE topic_insights SET topic_id=? WHERE topic_id=?",
                        (keep_id, dup_id),
                    )
                else:
                    cur.execute("DELETE FROM topic_insights WHERE topic_id=?", (dup_id,))

            cur.execute("DELETE FROM topics WHERE id=?", (dup_id,))


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


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
