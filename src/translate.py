import requests
from db import connect

# 無料・APIキー不要（精度も実用）
API = "https://translate.googleapis.com/translate_a/single"

def translate(text):
    params = {
        "client": "gtx",
        "sl": "en",
        "tl": "ja",
        "dt": "t",
        "q": text
    }
    r = requests.get(API, params=params, timeout=10)
    r.raise_for_status()
    return "".join([x[0] for x in r.json()[0]])

def main():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title FROM articles
        WHERE title_ja IS NULL
          AND title REGEXP '[A-Za-z]'
        LIMIT 50
    """)

    for aid, title in cur.fetchall():
        try:
            ja = translate(title)
            cur.execute(
                "UPDATE articles SET title_ja=? WHERE id=?",
                (ja, aid)
            )
        except Exception:
            pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
