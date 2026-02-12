# src/topic_backfill.py
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def connect():
    base = Path(__file__).resolve().parent.parent
    return sqlite3.connect(base / "data" / "state.sqlite")

def main(limit: int = 500):
    con = connect()
    cur = con.cursor()

    # 未トピック化の news/tech を拾う
    sql = """
    SELECT a.id, a.kind, a.category, a.title, a.title_ja
    FROM articles a
    LEFT JOIN topic_articles ta ON ta.article_id = a.id
    WHERE ta.article_id IS NULL
      AND a.kind IN ('news','tech')
    ORDER BY COALESCE(a.published_at, a.fetched_at) DESC
    LIMIT ?
    """
    cur.execute(sql, (limit,))
    rows = cur.fetchall()

    now = datetime.now(timezone.utc).isoformat()
    created_topics = 0
    linked = 0

    for article_id, kind, category, title, title_ja in rows:
        # category 空は kind を採用（news/tech を落とさない）
        cat = (category.strip() if category else "") or kind

        # topic_key を恒久キーに（重複防止）
        topic_key = f"{kind}:{article_id}"

        cur.execute("SELECT id FROM topics WHERE topic_key=?", (topic_key,))
        r = cur.fetchone()
        if r:
            topic_id = r[0]
        else:
            cur.execute(
                "INSERT INTO topics(title, title_ja, category, score_48h, created_at, topic_key, kind, region) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (title or title_ja or "", title_ja or "", cat or "other", 0, now, topic_key, kind, "")
            )
            topic_id = cur.lastrowid
            created_topics += 1

        cur.execute(
            "SELECT 1 FROM topic_articles WHERE topic_id=? AND article_id=?",
            (topic_id, article_id)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO topic_articles(topic_id, article_id) VALUES(?,?)",
                (topic_id, article_id)
            )
            linked += 1

    con.commit()
    con.close()

    print(f"[OK] topic_backfill created_topics={created_topics} linked={linked} processed={len(rows)}")

if __name__ == "__main__":
    main()
