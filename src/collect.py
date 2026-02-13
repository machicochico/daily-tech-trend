import feedparser
import yaml
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections import defaultdict

from db import init_db, connect

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re
import time

# ★本文フェッチ用
import urllib.request
import urllib.error
import html as _html
import socket


def _now_sec():
    return time.perf_counter()


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


FULLTEXT_SOURCES = {
    "Forest Watch",  # RSS本文が短いことがある
    # 必要なら追加
    # "毎日新聞（速報）",
}
MIN_CONTENT_CHARS = 200          # RSS本文がこれ未満なら「薄い」と判定して補完を試みる
MAX_FETCH_BYTES = 2_000_000      # 取得上限 2MB（暴走防止）
FETCH_TIMEOUT_SEC = 15

# 同意画面/JS依存など、取得しても本文抽出できない・リスク高いドメインは除外
SKIP_FETCH_DOMAINS = {
    "www3.nhk.or.jp",
    "www.nhk.or.jp",
}


def _strip_html_soft(s: str) -> str:
    """script/style除去→タグ除去→空白圧縮（簡易）"""
    if not s:
        return ""
    s = re.sub(r"(?is)<script.*?>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?>.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def should_fetch_fulltext(source: str, content: str, fetch_count: int, fetch_limit: int) -> bool:
    """本文補完を試みる条件を判定する。"""
    if source not in FULLTEXT_SOURCES:
        return False
    if fetch_count >= fetch_limit:
        return False
    return len((content or "").strip()) < MIN_CONTENT_CHARS


def fetch_fulltext(url: str, source: str = "") -> str:
    """記事ページを取得して本文っぽいテキストを抽出（簡易）。失敗時は空文字。"""
    host = urlsplit(url).netloc.lower()
    if host in SKIP_FETCH_DOMAINS:
        return ""

    try:
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SEC) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" not in ctype:
                return ""

            data = resp.read(MAX_FETCH_BYTES + 1)
            if len(data) > MAX_FETCH_BYTES:
                # 大きすぎるページは無視（事故防止）
                return ""

            # charset 推定
            charset = "utf-8"
            m = re.search(r"charset=([a-zA-Z0-9_\-]+)", ctype)
            if m:
                charset = m.group(1).strip()

            html_text = data.decode(charset, errors="ignore")
            text = _strip_html_soft(html_text)

            # 短すぎる場合は失敗扱い
            if len(text) < MIN_CONTENT_CHARS:
                return ""

            return text
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout) as e:
        print(f"[WARN] fulltext fetch failed source={source} url={url} host={host} err={e}")
        return ""
    except ValueError as e:
        print(f"[WARN] fulltext response invalid source={source} url={url} host={host} err={e}")
        return ""


DROP_QS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
HEADERS = {
    "User-Agent": "DailyTechTrend/1.0 (+https://github.com/yourname/daily-tech-trend)"
}


def normalize_url(u: str) -> str:
    sp = urlsplit(u)
    qs = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if k not in DROP_QS]
    return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(qs), ""))  # fragment


def load_feed_list(cfg: dict):
    """
    対応形式:
      A) 旧: feeds:   [{url, category, source, kind, region, limit}, ...]
      B) 新: sources: [{name, category, kind, region, limit, rss:[...]} , ...]
         rss は文字列URLの配列、または {url, category, limit} の配列も許可

    拡張:
      - vendor: source上限の判定単位。未指定時は source/name を利用。
      - weekly_new_limit: 1週間あたりの新規採用上限。超過分は low_priority_articles へ退避。
    """
    out = []

    # A) 旧形式
    if isinstance(cfg.get("feeds"), list):
        for x in cfg["feeds"]:
            if not isinstance(x, dict):
                continue
            url = x.get("url")
            if not url:
                continue
            source_name = x.get("source", "")
            out.append(
                {
                    "url": url,
                    "category": x.get("category"),
                    "source": source_name,
                    "vendor": x.get("vendor", source_name),
                    "source_tier": x.get("source_tier", "secondary"),
                    "kind": x.get("kind", "tech"),
                    "region": x.get("region", "") or "",
                    "limit": x.get("limit", 30),
                    "weekly_new_limit": x.get("weekly_new_limit"),
                }
            )
        return out

    # B) 新形式（sources + rss配列）
    if isinstance(cfg.get("sources"), list):
        for s in cfg["sources"]:
            if not isinstance(s, dict):
                continue

            source_name = s.get("name", s.get("source", ""))
            base = {
                "category": s.get("category"),
                "source": source_name,
                "vendor": s.get("vendor", source_name),
                "source_tier": s.get("source_tier", "secondary"),
                "kind": s.get("kind", "tech"),
                "region": s.get("region", "") or "",
                "limit": s.get("limit", 30),
                "weekly_new_limit": s.get("weekly_new_limit"),
            }

            rss_list = s.get("rss") or []
            if not rss_list and s.get("url"):
                rss_list = [s["url"]]

            # rss: [ "https://...", ... ]
            for r in rss_list:
                if isinstance(r, str):
                    out.append({**base, "url": r})
                # rss: [ {url: "...", category: "...", limit: 30}, ... ] も許可
                elif isinstance(r, dict):
                    url = r.get("url")
                    if not url:
                        continue
                    out.append(
                        {
                            **base,
                            "url": url,
                            "category": r.get("category", base["category"]),
                            "limit": r.get("limit", base["limit"]),
                            "weekly_new_limit": r.get("weekly_new_limit", base["weekly_new_limit"]),
                            "vendor": r.get("vendor", base["vendor"]),
                            "source_tier": r.get("source_tier", base["source_tier"]),
                        }
                    )

        if out:
            return out

    raise KeyError("sources.yaml must contain 'feeds' or 'sources' list (with rss).")


def normalize_published_at(entry) -> str:
    """
    RSSの published/updated (RFC2822等) を ISO8601(UTC) に正規化して返す。
    変換できない場合は空文字。
    """
    s = getattr(entry, "published", None) or getattr(entry, "updated", None) or ""
    if not s:
        return ""

    # feedparserは parsedate が入る場合もある（struct_time 等）ので、それも吸収
    try:
        dt = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            # struct_time -> datetime(UTC扱い)
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            dt = parsedate_to_datetime(s)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return ""


def resolve_week_key(published_at: str, fetched_at: str) -> str:
    """published_at優先で ISO週キー(YYYY-WW) を返す。"""
    target = published_at or fetched_at
    try:
        dt = datetime.fromisoformat(target.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        dt = datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-{iso.week:02d}"


def should_route_to_low_priority(*, is_new: bool, current_new_count: int, weekly_limit: int | None) -> bool:
    """source単位の新規上限判定フック。True の場合は低優先キューへ送る。"""
    if not is_new:
        return False
    if weekly_limit is None:
        return False
    return current_new_count >= weekly_limit


def main():
    t0 = _now_sec()
    print("[TIME] step=collect start")
    init_db()

    with open("src/sources.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    feed_list = load_feed_list(cfg)

    conn = connect()
    cur = conn.cursor()
    source_week_new_count = defaultdict(int)

    for feed in feed_list:
        fetch_count = 0
        fetch_limit = 30  # Forest Watchは30件全部補完してもよい
        # d = feedparser.parse(feed["url"])
        try:
            d = feedparser.parse(feed["url"], request_headers=HEADERS)
        except (urllib.error.URLError, ValueError, OSError) as e:
            print(f"[WARN] feed fetch failed source={feed.get('source', '')} url={feed['url']} err={e}")
            continue

        if getattr(d, "bozo", 0):
            # 壊れたXMLでも entries が取れることがあるので続行はする
            print(f"[WARN] malformed feed source={feed.get('source', '')} url={feed['url']} err={getattr(d, 'bozo_exception', '')}")

        limit = feed.get("limit", 30)
        for e in getattr(d, "entries", [])[:limit]:
            raw_link = getattr(e, "link", None)
            if not raw_link:
                print(f"[WARN] skip entry without link source={feed.get('source', '')} feed_url={feed['url']}")
                continue
            link = normalize_url(raw_link)
            title = getattr(e, "title", None)
            if not link or not title:
                print(f"[WARN] skip invalid entry source={feed.get('source', '')} feed_url={feed['url']} url={raw_link}")
                continue
            content = ""

            if getattr(e, "content", None):
                if isinstance(e.content, list) and e.content:
                    content = e.content[0].get("value", "")
            elif getattr(e, "summary", None):
                content = e.summary

            content = strip_html(content)

            # ★本文が薄い/空なら、記事本文の補完を試みる（成功時のみ置き換え）
            src = feed.get("source", "")
            if should_fetch_fulltext(src, content, fetch_count, fetch_limit):
                full = fetch_fulltext(link, source=src)
                if full:
                    content = full
                    fetch_count += 1
                    # print(f"[INFO] fetched fulltext source={src} url={link}")

            published_at = normalize_published_at(e)
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            cur.execute("SELECT 1 FROM articles WHERE url=?", (link,))
            is_new_article = cur.fetchone() is None

            week_key = resolve_week_key(published_at, fetched_at)
            source_unit = (feed.get("vendor") or feed.get("source") or "").strip() or "unknown"
            source_count_key = (source_unit, week_key)
            weekly_limit = feed.get("weekly_new_limit")

            if should_route_to_low_priority(
                is_new=is_new_article,
                current_new_count=source_week_new_count[source_count_key],
                weekly_limit=weekly_limit,
            ):
                cur.execute(
                    """
                    INSERT INTO low_priority_articles
                    (url, title, content, source, vendor, category, source_tier,
                     published_at, fetched_at, kind, region, reason, queued_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(url) DO UPDATE SET
                        title=excluded.title,
                        content=excluded.content,
                        source=excluded.source,
                        vendor=excluded.vendor,
                        category=excluded.category,
                        source_tier=excluded.source_tier,
                        published_at=excluded.published_at,
                        fetched_at=excluded.fetched_at,
                        kind=excluded.kind,
                        region=excluded.region,
                        reason=excluded.reason,
                        queued_at=excluded.queued_at
                    """,
                    (
                        link,
                        title,
                        content,
                        feed.get("source", ""),
                        feed.get("vendor", ""),
                        feed.get("category", "") or "",
                        feed.get("source_tier", "secondary"),
                        published_at,
                        fetched_at,
                        feed.get("kind", "tech"),
                        feed.get("region", "") or "",
                        f"weekly_new_limit_exceeded:{source_unit}:{week_key}:{weekly_limit}",
                        fetched_at,
                    ),
                )
                continue

            cur.execute(
                """
                INSERT INTO articles
                (url, title, content, source, category, source_tier, published_at, fetched_at, kind, region)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    source=excluded.source,
                    category=excluded.category,
                    source_tier=excluded.source_tier,
                    published_at=excluded.published_at,
                    fetched_at=excluded.fetched_at,
                    kind=excluded.kind,
                    region=excluded.region
                """,
                (
                    link,
                    title,
                    content,
                    feed.get("source", ""),
                    feed.get("category", "") or "",
                    feed.get("source_tier", "secondary"),
                    published_at,
                    fetched_at,
                    feed.get("kind", "tech"),
                    feed.get("region", "") or "",
                ),
            )

            if is_new_article:
                source_week_new_count[source_count_key] += 1

    cur.execute(
        "UPDATE articles SET category='news' "
        "WHERE kind='news' AND (category IS NULL OR TRIM(category)='')"
    )
    conn.commit()
    conn.close()

    sec = _now_sec() - t0
    print(f"[TIME] step=collect end sec={sec:.1f}")


if __name__ == "__main__":
    main()
