from urllib.parse import urlsplit, urlunsplit
from db import connect

def normalize(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))

def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, url FROM articles")
    for i, url in cur.fetchall():
        cur.execute("UPDATE articles SET url_norm=? WHERE id=?", (normalize(url), i))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
