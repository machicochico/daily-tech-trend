import logging
import time
from urllib.parse import urlsplit, urlunsplit

from db import connect
from text_clean import clean_text

logger = logging.getLogger(__name__)

def _now_sec():
    return time.perf_counter()

def normalize(url):
    url = clean_text(url).strip()
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))

def main():
    t0 = _now_sec()
    logger.info("step=normalize start")
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, url FROM articles")
    rows = cur.fetchall()
    ok, skip = 0, 0
    updates = []
    for i, url in rows:
        try:
            updates.append((normalize(url), i))
            ok += 1
        except Exception as e:
            logger.warning("normalize failed id=%s url=%r err=%s", i, str(url)[:80], e)
            skip += 1
    cur.executemany("UPDATE articles SET url_norm=? WHERE id=?", updates)
    conn.commit()
    conn.close()

    logger.info("step=normalize end sec=%.1f ok=%d skip=%d total=%d", _now_sec() - t0, ok, skip, len(rows))

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    main()
