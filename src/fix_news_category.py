import sqlite3
from pathlib import Path

def main():
    base = Path(__file__).resolve().parent.parent
    db = base / "data" / "state.sqlite"
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("""
    UPDATE articles
    SET category = 'news'
    WHERE kind = 'news'
      AND (category IS NULL OR TRIM(category) = '')
    """)
    con.commit()
    con.close()
    print("[OK] fix_news_category")

if __name__ == "__main__":
    main()
