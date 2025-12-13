import re
import requests
from db import connect

API = "https://translate.googleapis.com/translate_a/single"

def translate(text: str) -> str:
    params = {
        "client": "gtx",
        "sl": "en",
        "tl": "ja",
        "dt": "t",
        "q": text
    }
    r = requests.get(API, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return "".join([x[0] for x in data[0] if x and x[0]])

def looks_english(text: str) -> bool:
    # 英字が少しでも含まれていれば対象にする（MVP）
    return bool(re.search(r"[A-Za-z]", text or ""))

def main():
    conn = connect()
    cur = conn.cursor()

    # REGEXPは使わず、未翻訳だけ取る
    cur.execute("SELECT id, title FROM articles WHERE title_ja IS NULL LIMIT 200")
    rows = cur.fetchall()

    for aid, title in rows:
        if not title or not looks_english(title):
            continue
        try:
            ja = translate(title)
            if ja:
                cur.execute("UPDATE articles SET title_ja=? WHERE id=?", (ja, aid))
        except Exception:
            # 失敗しても全体を止めない
            continue

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
