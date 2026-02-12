import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def connect():
    base = Path(__file__).resolve().parent.parent
    return sqlite3.connect(base / "data" / "state.sqlite")


def _now():
    return datetime.now(timezone.utc).isoformat()


def pick_topic_inputs(conn, limit=300, rescue=False):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
    WITH latest AS (
      SELECT
        ta.topic_id,
        a.id AS article_id,
        a.kind AS kind,
        a.source,
        a.title,
        a.title_ja,
        a.url,
        a.content,
        a.category AS article_category,
        a.published_at,
        a.fetched_at,
        ROW_NUMBER() OVER (
          PARTITION BY ta.topic_id
          ORDER BY COALESCE(a.published_at, a.fetched_at) DESC, a.id DESC
        ) AS rn
      FROM topic_articles ta
      JOIN articles a ON a.id = ta.article_id
      WHERE a.kind IN ('tech','news')
    )
    SELECT
      t.id AS topic_id,
      CASE
        WHEN COALESCE(NULLIF(t.category,''),'') = 'news'
          THEN COALESCE(NULLIF(l.title_ja,''), NULLIF(l.title,''), NULLIF(t.title_ja,''), NULLIF(t.title,''))
        ELSE COALESCE(NULLIF(t.title_ja,''), NULLIF(t.title,''), NULLIF(l.title_ja,''), NULLIF(l.title,''))
      END AS topic_title,
      CASE
        WHEN COALESCE(NULLIF(t.category,''),'') = 'news' THEN 'news'
        ELSE COALESCE(NULLIF(l.article_category,''), NULLIF(t.category,''), 'other')
      END AS category,
      l.kind AS kind,
      l.source AS source,
      l.url AS url,
      l.published_at AS published_at,
      t.score_48h AS importance_hint,
      COALESCE(NULLIF(l.content,''), NULLIF(l.title_ja,''), NULLIF(l.title,''), '') AS body,
      l.article_id AS src_article_id,
      ti.src_hash AS prev_src_hash
    FROM topics t
    JOIN latest l ON l.topic_id = t.id AND l.rn = 1
    LEFT JOIN topic_insights ti ON ti.topic_id = t.id
    WHERE (
      ti.topic_id IS NULL
      OR (? = 1 AND (
            COALESCE(ti.importance, 0) = 0
         OR COALESCE(ti.summary, '') = ''
         OR COALESCE(ti.src_hash, '') = ''
      ))
    )
    ORDER BY COALESCE(l.published_at, l.fetched_at) DESC
    LIMIT ?
    """,
        (1 if rescue else 0, limit),
    )
    return cur.fetchall()


def compute_src_hash(title: str, url: str, body: str) -> str:
    seed = (title or "") + "\n" + (url or "") + "\n" + (body or "")[:2000]
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()


def postprocess_insight(ins: dict, row: dict) -> dict:
    ins = dict(ins or {})
    is_news = ((row.get("category") or "").lower() == "news") or ((row.get("kind") or "").lower() == "news")

    try:
        ins["importance"] = int(ins.get("importance") or 0)
    except Exception:
        ins["importance"] = 0
    if ins["importance"] <= 0:
        ins["importance"] = 10 if is_news else 20

    if not ins.get("type"):
        ins["type"] = "other"

    if not (ins.get("summary") or "").strip():
        if is_news:
            raise RuntimeError("news summary is empty")
        ins["summary"] = "（要約を生成できませんでした）"

    if "evidence_urls" not in ins or not ins["evidence_urls"]:
        ins["evidence_urls"] = [row.get("url")]

    kps = [x for x in (ins.get("key_points") or []) if isinstance(x, str) and x.strip()]
    if is_news:
        fallback = [
            "推測: 詳細はリンク先の本文確認が必要",
            "推測: 背景や影響は本文で確認が必要",
            "推測: 続報で条件が変わる可能性がある",
        ]
        while len(kps) < 3:
            kps.append(fallback[len(kps)])
    else:
        while len(kps) < 3:
            kps.append("（本文中の明確な事実は限定的）")
    ins["key_points"] = kps[:3]

    p = ins.get("perspectives") if isinstance(ins.get("perspectives"), dict) else {}
    news_fb = {
        "engineer": "推測: 技術的な影響や背景はリンク先本文の確認が必要",
        "management": "推測: 社会的影響や対応要否は続報・一次情報で判断が必要",
        "consumer": "推測: 生活への影響は現時点では不明で、詳細確認が望ましい",
    }
    tech_fb = {
        "engineer": "（技術観点のコメントを生成できませんでした）",
        "management": "（経営観点のコメントを生成できませんでした）",
        "consumer": "（利用者観点のコメントを生成できませんでした）",
    }
    fb = news_fb if is_news else tech_fb
    for k in ("engineer", "management", "consumer"):
        if not isinstance(p.get(k), str) or not p.get(k).strip():
            p[k] = fb[k]
    ins["perspectives"] = p
    return ins


def upsert_insight(conn, topic_id, insight, src_article_id: int | None, src_hash: str):
    cur = conn.cursor()
    cur.execute(
        """
    INSERT INTO topic_insights(
        topic_id, importance, type, summary, key_points, evidence_urls, tags,
        perspectives, updated_at, src_article_id, src_hash, inferred
      )
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(topic_id) DO UPDATE SET
        importance=excluded.importance,
        type=excluded.type,
        summary=excluded.summary,
        key_points=excluded.key_points,
        evidence_urls=excluded.evidence_urls,
        tags=excluded.tags,
        perspectives=excluded.perspectives,
        updated_at=excluded.updated_at,
        src_article_id=excluded.src_article_id,
        src_hash=excluded.src_hash,
        inferred=excluded.inferred
    """,
        (
            topic_id,
            int(insight.get("importance") or 0),
            (insight.get("type") or "other"),
            (insight.get("summary") or ""),
            json.dumps(insight.get("key_points") or [], ensure_ascii=False),
            json.dumps(insight.get("evidence_urls") or [], ensure_ascii=False),
            json.dumps(insight.get("tags") or [], ensure_ascii=False),
            json.dumps(insight.get("perspectives") or {}, ensure_ascii=False),
            _now(),
            src_article_id,
            src_hash,
            int(insight.get("inferred") or 0),
        ),
    )
