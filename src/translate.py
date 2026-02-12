import re
import requests
from requests import RequestException
from db import connect

import time

def _now_sec():
    return time.perf_counter()

API = "https://translate.googleapis.com/translate_a/single"

def translate(text: str) -> str:
    params = {"client":"gtx","sl":"en","tl":"ja","dt":"t","q":text}
    r = requests.get(API, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return "".join([x[0] for x in data[0] if x and x[0]])

def looks_english(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))

def ensure_column(cur, table: str, col: str, coltype: str = "TEXT"):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]  # r[1] = column name
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")

def translate_news_titles(conn, limit: int = 400):
    """
    articles.kind='news' かつ title_ja が空のものを翻訳して埋める。
    """
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, title
        FROM articles
        WHERE kind IN ('news','tech')
          AND title IS NOT NULL AND title != ''
          AND (title_ja IS NULL OR title_ja = '')
        ORDER BY published_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    print(f"[translate] news titles (to translate): {len(rows)}")

    n_ok = 0
    for article_id, title in rows:
        try:
            ja = translate(title)
            ja = (ja or "").strip()
        except (RequestException, ValueError) as e:
            print(f"[WARN] translate failed id={article_id} title={title[:80]!r} err={e}")
            continue

        if not ja:
            print(f"[WARN] translate returned empty id={article_id} title={title[:80]!r}")
            continue

        cur.execute(
            "UPDATE articles SET title_ja=? WHERE id=?",
            (ja, article_id),
        )
        n_ok += 1

    conn.commit()
    print(f"[translate] news titles updated: {n_ok}")

def main():
    t0 = _now_sec()
    print("[TIME] step=translate start")
    conn = connect()
    cur = conn.cursor()

    ensure_column(cur, "articles", "title_ja", "TEXT")
    translate_news_titles(conn, limit=600)

    # topics を日本語化（トップ表示に直結）
    # cur.execute("SELECT id, title FROM topics WHERE title_ja IS NULL LIMIT 100")
    cur.execute("SELECT id, title FROM topics WHERE title_ja IS NULL OR title_ja = ''")
    rows = cur.fetchall()

    for tid, title in rows:
        if not title or not looks_english(title):
            continue
        try:
            ja = translate(title)
        except (RequestException, ValueError) as e:
            print(f"[WARN] translate topic failed topic_id={tid} title={title[:80]!r} err={e}")
            continue

        if not ja:
            print(f"[WARN] translate topic empty topic_id={tid} title={title[:80]!r}")
            continue
        cur.execute("UPDATE topics SET title_ja=? WHERE id=?", (ja, tid))
    
    conn.commit()   
    conn.close()

    print(f"[TIME] step=translate end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
