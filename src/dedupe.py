import re
import unicodedata
from datetime import datetime
from typing import Dict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from difflib import SequenceMatcher

from db import connect

# カテゴリ別に重複判定しきい値を調整
# 値が低いほど「重複」と判定されやすい。
CATEGORY_THRESHOLDS: Dict[str, int] = {
    "ai": 88,
    "security": 90,
    "cloud": 89,
    "devtools": 90,
    "business": 93,
    "policy": 94,
    "default": 91,
}

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def normalize_title(title: str) -> str:
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title).lower()
    s = re.sub(r"\s+", " ", s)
    # 記号を空白化して語順比較のノイズを減らす
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")

    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k not in TRACKING_QUERY_KEYS]
    q.sort()
    query = urlencode(q, doseq=True)

    scheme = p.scheme.lower() or "https"
    return urlunsplit((scheme, host, path, query, ""))


def category_threshold(category: str) -> int:
    key = (category or "").strip().lower()
    return CATEGORY_THRESHOLDS.get(key, CATEGORY_THRESHOLDS["default"])


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio() * 100


def _token_set_ratio(a: str, b: str) -> float:
    ta = set((a or "").split())
    tb = set((b or "").split())
    sa = " ".join(sorted(ta))
    sb = " ".join(sorted(tb))
    return _ratio(sa, sb)


def _composite_score(title_a: str, title_b: str, url_a: str, url_b: str) -> float:
    title_score = _token_set_ratio(title_a, title_b)
    url_score = _ratio(url_a, url_b)
    # タイトル寄りだがURL一致も加点する複合スコア
    return title_score * 0.75 + url_score * 0.25


def ensure_dedupe_log_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dedupe_judgments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          article_id INTEGER NOT NULL,
          kept_article_id INTEGER NOT NULL,
          article_source TEXT,
          kept_source TEXT,
          article_category TEXT,
          title_score REAL,
          url_score REAL,
          composite_score REAL,
          threshold REAL,
          title_match INTEGER,
          url_exact_match INTEGER,
          decision TEXT,
          reason TEXT,
          created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dedupe_judgments_article
        ON dedupe_judgments(article_id)
        """
    )


def log_decision(
    cur,
    *,
    article_id: int,
    kept_article_id: int,
    article_source: str,
    kept_source: str,
    article_category: str,
    title_score: float,
    url_score: float,
    composite_score: float,
    threshold: float,
    title_match: bool,
    url_exact_match: bool,
    decision: str,
    reason: str,
):
    cur.execute(
        """
        INSERT INTO dedupe_judgments(
          article_id, kept_article_id, article_source, kept_source, article_category,
          title_score, url_score, composite_score, threshold,
          title_match, url_exact_match, decision, reason, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            kept_article_id,
            article_source,
            kept_source,
            article_category,
            title_score,
            url_score,
            composite_score,
            threshold,
            1 if title_match else 0,
            1 if url_exact_match else 0,
            decision,
            reason,
            datetime.utcnow().isoformat(timespec="seconds"),
        ),
    )


def main():
    conn = connect()
    cur = conn.cursor()
    ensure_dedupe_log_table(cur)

    cur.execute("SELECT id, source, category, title, url, url_norm FROM articles ORDER BY id DESC")
    rows = cur.fetchall()

    seen = {}
    for i, source, category, title, url, url_norm in rows:
        norm_title = normalize_title(title)
        norm_url = normalize_url(url_norm or url)
        threshold = category_threshold(category)

        for si, kept in seen.items():
            kept_title = kept["norm_title"]
            kept_url = kept["norm_url"]

            title_score = _token_set_ratio(norm_title, kept_title)
            url_score = _ratio(norm_url, kept_url)
            composite = _composite_score(norm_title, kept_title, norm_url, kept_url)

            title_match = title_score >= (threshold - 5)
            url_exact_match = bool(norm_url and norm_url == kept_url)

            is_duplicate = url_exact_match or (title_match and composite >= threshold)
            if is_duplicate:
                reason = "url_exact" if url_exact_match else "composite_threshold"
                cur.execute("DELETE FROM articles WHERE id=?", (i,))
                log_decision(
                    cur,
                    article_id=i,
                    kept_article_id=si,
                    article_source=source,
                    kept_source=kept["source"],
                    article_category=category,
                    title_score=title_score,
                    url_score=url_score,
                    composite_score=composite,
                    threshold=threshold,
                    title_match=title_match,
                    url_exact_match=url_exact_match,
                    decision="delete",
                    reason=reason,
                )
                break
        else:
            seen[i] = {
                "norm_title": norm_title,
                "norm_url": norm_url,
                "source": source,
            }

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
