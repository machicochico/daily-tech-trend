from __future__ import annotations

from text_clean import clean_for_html


def _clean_rows(rows):
    cleaned = []
    for row in rows:
        cleaned.append(tuple(clean_for_html(v) if isinstance(v, str) else v for v in row))
    return cleaned


def fetch_news_articles(cur, region: str, limit: int = 60):
    if region:
        cur.execute(
            """
            SELECT
              articles.id AS article_id,
              COALESCE(NULLIF(title_ja,''), NULLIF(title,''), url) AS title,
              url,
              COALESCE(NULLIF(source,''), '') AS source,
              COALESCE(NULLIF(category,''), '') AS category,
              COALESCE(NULLIF(published_at,''), fetched_at) AS dt,
              (
                SELECT i.importance FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
              ) AS importance,
              (
                SELECT i.tags FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
              ) AS tags,
              (
                SELECT i.summary FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
              ) AS summary
            FROM articles
            WHERE kind='news' AND region=?
            ORDER BY datetime(substr(replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),1, 19)) DESC, id DESC
            LIMIT ?
            """,
            (region, limit),
        )
    else:
        cur.execute(
            """
            SELECT COALESCE(NULLIF(title_ja,''), NULLIF(title,''), url) AS title, url,
              COALESCE(NULLIF(source,''), '') AS source,
              COALESCE(NULLIF(category,''), '') AS category,
              COALESCE(NULLIF(region,''), '') AS region,
              COALESCE(NULLIF(published_at,''), fetched_at) AS dt
            FROM articles
            WHERE kind='news'
            ORDER BY datetime(substr(replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),1,19)) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    return _clean_rows(cur.fetchall())


def fetch_news_articles_by_category(cur, region: str, category: str, limit: int = 40):
    cur.execute(
        """
        SELECT
          a.id AS article_id,
          COALESCE(NULLIF(a.title_ja,''), NULLIF(a.title,''), a.url) AS title,
          a.url,
          COALESCE(NULLIF(a.source,''), '') AS source,
          COALESCE(NULLIF(a.category,''), '') AS category,
          COALESCE(NULLIF(a.published_at,''), a.fetched_at) AS dt,
          (
            SELECT i.importance
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS importance,
          (
            SELECT i.type
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS typ,
          (
            SELECT i.summary
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS summary,
          (
            SELECT i.key_points
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS key_points,
          (
            SELECT i.perspectives
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS perspectives,
          (
            SELECT i.tags
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS tags,
          (
            SELECT i.evidence_urls
            FROM topic_articles ta JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC LIMIT 1
          ) AS evidence_urls,
          (
            SELECT ta.is_representative
            FROM topic_articles ta
            JOIN topics t ON t.id = ta.topic_id
            WHERE ta.article_id = a.id AND COALESCE(t.kind,'')='news'
            ORDER BY ta.is_representative DESC, ta.topic_id DESC LIMIT 1
          ) AS is_representative
        FROM articles a
        WHERE a.kind='news' AND COALESCE(a.region,'')=? AND COALESCE(a.category,'')=?
        ORDER BY datetime(substr(replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),1,19)) DESC, a.id DESC
        LIMIT ?
        """,
        (region, category, limit),
    )
    return _clean_rows(cur.fetchall())


def count_news_recent_48h(cur, region: str, category: str, cutoff_dt: str) -> int:
    cur.execute(
        """
        SELECT COALESCE(SUM(
          CASE WHEN datetime(substr(replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),1,19)) >= datetime(?) THEN 1 ELSE 0 END
        ),0)
        FROM articles
        WHERE kind='news' AND COALESCE(region,'')=? AND COALESCE(category,'')=?
        """,
        (cutoff_dt, region, category),
    )
    row = cur.fetchone()
    return int(row[0] if row and row[0] is not None else 0)
