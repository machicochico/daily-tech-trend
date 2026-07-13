"""トピックタイムライン: 一つのトピックに属する記事を時系列で追うページ。

docs/topic/<topic_id>/index.html を上位 importance のトピックについて生成する。
LLM 呼び出し不要（記事タイトル・要約・日付の表示のみ）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from db import connect
from page_common import PAGE_BASE_CSS


def _format_date(s: str | None) -> str:
    if not s:
        return ""
    try:
        return str(s)[:16].replace("T", " ")
    except Exception:
        return str(s)[:16]


def render_topic_timelines(
    out_dir: Path | str, *, top_n: int = 50, include_ids=None, conn=None
) -> int:
    """個別トピックページを書き出す。

    対象は以下の和集合:
    - importance 上位 `top_n` 件
    - 直近48時間に記事が追加されたトピック
    - `include_ids`（メインページから 📈 経緯リンクで参照されている ID 群。
      リンク切れを防ぐため呼び出し側が渡す）

    戻り値: 生成したページ数。
    """
    out_dir = Path(out_dir)
    topic_root = out_dir / "topic"
    topic_root.mkdir(parents=True, exist_ok=True)

    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()

    # 対象 ID を収集
    target_ids: set[int] = {int(i) for i in (include_ids or [])}
    cur.execute(
        """
        SELECT t.id FROM topics t
        LEFT JOIN topic_insights ti ON ti.topic_id = t.id
        ORDER BY COALESCE(ti.importance, 0) DESC, ti.updated_at DESC
        LIMIT ?
        """,
        (int(top_n),),
    )
    target_ids |= {r[0] for r in cur.fetchall()}
    cutoff_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        SELECT DISTINCT ta.topic_id FROM topic_articles ta
        JOIN articles a ON a.id = ta.article_id
        WHERE COALESCE(a.published_at, a.fetched_at) >= ?
        """,
        (cutoff_48h,),
    )
    target_ids |= {r[0] for r in cur.fetchall()}

    # 詳細をチャンク取得（SQLite の IN 句上限対策）
    topics = []
    id_list = sorted(target_ids)
    for i in range(0, len(id_list), 500):
        chunk = id_list[i:i + 500]
        placeholders = ",".join("?" * len(chunk))
        cur.execute(
            f"""
            SELECT
              t.id,
              COALESCE(t.title_ja, t.title) AS title,
              COALESCE(t.category, ''),
              COALESCE(ti.importance, 0),
              COALESCE(ti.summary, ''),
              COALESCE(ti.updated_at, t.created_at)
            FROM topics t
            LEFT JOIN topic_insights ti ON ti.topic_id = t.id
            WHERE t.id IN ({placeholders})
              AND COALESCE(t.title_ja, t.title) IS NOT NULL
              AND COALESCE(t.title_ja, t.title) != ''
            """,
            chunk,
        )
        topics.extend(cur.fetchall())
    topics.sort(key=lambda r: ((r[3] or 0), str(r[5] or "")), reverse=True)

    generated = 0
    for topic_id, title, category, importance, summary, updated_at in topics:
        cur.execute(
            """
            SELECT
              a.id,
              COALESCE(a.title_ja, a.title) AS title,
              COALESCE(a.source, ''),
              COALESCE(a.url, ''),
              COALESCE(a.published_at, a.fetched_at) AS dt,
              COALESCE(a.content, '')
            FROM topic_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.topic_id = ?
            ORDER BY COALESCE(a.published_at, a.fetched_at) ASC
            """,
            (topic_id,),
        )
        articles = cur.fetchall()
        # 記事0件でもページは生成する（メインページからリンクされるため、
        # スキップすると404になる。重複整理で元記事が削除されたケース等）

        items_html: list[str] = []
        if not articles:
            items_html.append(
                '<li class="timeline-item"><div class="timeline-body">'
                '<div class="timeline-meta">このトピックの元記事は重複整理により削除されました。</div>'
                "</div></li>"
            )
        for aid, a_title, a_source, a_url, a_dt, a_content in articles:
            snippet = (a_content or "")[:180]
            snippet_html = (
                f'<p class="timeline-snippet">{escape(snippet)}...</p>' if snippet else ""
            )
            items_html.append(
                f'<li class="timeline-item">'
                f'<div class="timeline-date">{escape(_format_date(a_dt))}</div>'
                f'<div class="timeline-body">'
                f'<a href="{escape(a_url)}" target="_blank" rel="noopener" class="timeline-title">{escape(a_title or "")}</a>'
                f'<div class="timeline-meta">{escape(a_source or "-")}</div>'
                f'{snippet_html}'
                f'</div></li>'
            )

        html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>{escape(title)} | トピックタイムライン</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{PAGE_BASE_CSS}
.summary{{background:#f9fafb;border-left:3px solid #2563eb;padding:.7rem 1rem;border-radius:0 8px 8px 0;margin:1rem 0}}
ol.timeline{{list-style:none;padding:0;position:relative;margin:1rem 0 1rem 1rem;border-left:2px solid #e5e7eb}}
.timeline-item{{padding:.5rem 0 1rem 1.2rem;position:relative}}
.timeline-item::before{{content:"";position:absolute;left:-7px;top:.8rem;width:12px;height:12px;border-radius:50%;background:#2563eb}}
.timeline-date{{color:#6b7280;font-size:.8rem;font-family:monospace}}
.timeline-title{{color:#2563eb;text-decoration:none;font-weight:600;display:inline-block;margin:.2rem 0}}
.timeline-title:hover{{text-decoration:underline}}
.timeline-meta{{color:#9ca3af;font-size:.8rem}}
.timeline-snippet{{margin:.3rem 0 0;font-size:.88rem;color:#4b5563}}
.importance-badge{{display:inline-block;padding:2px 8px;border-radius:4px;color:#fff;background:#d97706;font-size:.8rem;font-weight:700}}
</style></head><body>
<nav><a href="../../">&larr; Top</a> / <a href="../../diff/">差分</a></nav>
<h1>{escape(title)}</h1>
<p class="meta">カテゴリ: <b>{escape(category or "-")}</b> · 重要度 <span class="importance-badge">{importance}</span> · 記事{len(articles)}件 · 最終更新 {escape(_format_date(updated_at))}</p>
{f'<div class="summary">{escape(summary)}</div>' if summary else ''}
<ol class="timeline">
{''.join(items_html)}
</ol>
</body></html>
"""
        topic_dir = topic_root / str(topic_id)
        topic_dir.mkdir(exist_ok=True)
        (topic_dir / "index.html").write_text(html, encoding="utf-8")
        generated += 1

    if owns_conn:
        conn.close()

    print(f"  topic timelines: {generated}件")
    return generated
