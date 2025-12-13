import feedparser
import yaml
from datetime import datetime, timezone
from db import init_db, connect

def load_feed_list(cfg: dict):
    # 旧形式: feeds: [{url, category, source}, ...]
    if isinstance(cfg.get("feeds"), list):
        return [{"url": x["url"], "category": x.get("category"), "source": x.get("source", "")} for x in cfg["feeds"]]

    # 新形式: sources: [{url, category, name}, ...]
    if isinstance(cfg.get("sources"), list):
        return [{"url": x["url"], "category": x.get("category"), "source": x.get("name", x.get("source", ""))} for x in cfg["sources"]]

    raise KeyError("sources.yaml must contain 'feeds' or 'sources' list.")

def main():
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    with open("src/sources.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    feed_list = load_feed_list(cfg)

    conn = connect()
    cur = conn.cursor()

    for feed in feed_list:
        d = feedparser.parse(feed["url"])
        for e in getattr(d, "entries", [])[:50]:
            link = getattr(e, "link", None)
            title = getattr(e, "title", None)
            if not link or not title:
                continue

            cur.execute(
                """
                INSERT OR IGNORE INTO articles
                (url, title, source, category, published_at, fetched_at)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    link,
                    title,
                    feed.get("source", ""),
                    feed.get("category", ""),
                    getattr(e, "published", "") or getattr(e, "updated", "") or "",
                    now,
                ),
            )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
