from datetime import datetime, timezone
from db import connect

def main():
    conn = connect()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute("SELECT id, title, category FROM articles")
    for aid, title, cat in cur.fetchall():
        key = title.lower()[:60]
        cur.execute("""
            INSERT OR IGNORE INTO topics (topic_key, title, category, created_at)
            VALUES (?,?,?,?)
        """, (key, title, cat, now))
        cur.execute("SELECT id FROM topics WHERE topic_key=?", (key,))
        tid = cur.fetchone()[0]
        cur.execute("INSERT OR IGNORE INTO topic_articles VALUES (?,?)", (tid, aid))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
