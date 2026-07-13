"""フィード・検索ページ生成専用モジュール。

render_main.py から分離することで、HTMLテンプレートと静的出力ロジックを
責務ごとに分ける第一歩。render_main はこのモジュールを re-export する。

公開関数:
- render_rss_feed(out_dir, generated_at, cur, limit=30): RSS 2.0 を docs/feed.xml へ
- render_search_page(out_dir, generated_at, cur, limit=3000): docs/search.html + search-index.json へ
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template


# 独立したロガー。render_main 側のロガーと干渉しないよう別名。
_logger = logging.getLogger("render_feeds")


def _rss_escape(s: str | None) -> str:
    """RSS XML 用の最小限エスケープ。"""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _rss_rfc822(dt_iso: str | None) -> str:
    """ISO8601 文字列を RFC 822 形式へ変換。失敗時は現在時刻を返す。"""
    if not dt_iso:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    try:
        s = str(dt_iso).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s[:25] if len(s) > 25 else s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except (ValueError, TypeError):
        _logger.debug("rss.rfc822_parse failed for %r", dt_iso)
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


from site_config import SITE_URL as FEED_SITE_URL

FEED_TITLE = os.environ.get("FEED_TITLE", "Daily Tech Trend")
FEED_DESCRIPTION = os.environ.get(
    "FEED_DESCRIPTION",
    "製造業・IT技術系の日次トレンドまとめ（自動生成）",
)


def render_rss_feed(out_dir: Path | str, generated_at: str, cur, limit: int = 30) -> None:
    """最新トピック `limit` 件を RSS 2.0 として docs/feed.xml に出力する。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(t.category, '') AS category,
          COALESCE(ti.summary, '') AS summary,
          COALESCE(ti.updated_at, t.created_at) AS updated_at,
          (
            SELECT a.url FROM topic_articles ta2
            JOIN articles a ON a.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY ta2.is_representative DESC, a.published_at DESC
            LIMIT 1
          ) AS primary_url
        FROM topics t
        LEFT JOIN topic_insights ti ON ti.topic_id = t.id
        WHERE COALESCE(t.title_ja, t.title) IS NOT NULL
          AND COALESCE(t.title_ja, t.title) != ''
        ORDER BY COALESCE(ti.updated_at, t.created_at) DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()

    items_xml: list[str] = []
    for topic_id, title, category, summary, updated_at, primary_url in rows:
        link = primary_url or f"{FEED_SITE_URL.rstrip('/')}/#topic-{topic_id}"
        guid = f"{FEED_SITE_URL.rstrip('/')}/topic/{topic_id}"
        desc_text = summary or title or ""
        if len(desc_text) > 500:
            desc_text = desc_text[:497] + "..."
        items_xml.append(
            "<item>"
            f"<title>{_rss_escape(title)}</title>"
            f"<link>{_rss_escape(link)}</link>"
            f"<guid isPermaLink=\"false\">{_rss_escape(guid)}</guid>"
            f"<pubDate>{_rss_rfc822(updated_at)}</pubDate>"
            + (f"<category>{_rss_escape(category)}</category>" if category else "")
            + f"<description>{_rss_escape(desc_text)}</description>"
            "</item>"
        )

    last_build = _rss_rfc822(generated_at)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>"
        f"<title>{_rss_escape(FEED_TITLE)}</title>"
        f"<link>{_rss_escape(FEED_SITE_URL)}</link>"
        f"<description>{_rss_escape(FEED_DESCRIPTION)}</description>"
        '<language>ja</language>'
        f"<lastBuildDate>{last_build}</lastBuildDate>"
        f'<atom:link href="{_rss_escape(FEED_SITE_URL.rstrip("/") + "/feed.xml")}" rel="self" type="application/rss+xml"/>'
        + "".join(items_xml)
        + "</channel></rss>\n"
    )

    (out_dir / "feed.xml").write_text(xml, encoding="utf-8")
    print(f"  rss feed: {out_dir / 'feed.xml'} ({len(rows)}件)")


SEARCH_HTML = r"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>記事検索 | Daily Tech Trend</title>
<link rel="stylesheet" href="{{ common_css_href }}">
<style>
  .search-wrap{max-width:900px;margin:2rem auto;padding:0 1rem}
  .search-input{width:100%;font-size:1.1rem;padding:.7rem 1rem;border:1px solid var(--border);border-radius:8px;background:var(--panel);color:var(--text-main);box-sizing:border-box}
  .search-meta{margin:.8rem 0;color:var(--text-sub);font-size:.9rem}
  .search-hit{border:1px solid var(--border);border-radius:8px;padding:.8rem 1rem;margin-bottom:.6rem;background:var(--panel)}
  .search-hit h3{margin:0 0 .3rem;font-size:1rem}
  .search-hit h3 a{color:var(--accent);text-decoration:none}
  .search-hit h3 a:hover{text-decoration:underline}
  .search-hit .meta{font-size:.8rem;color:var(--text-sub)}
  .search-hit .snippet{font-size:.9rem;margin-top:.3rem;color:var(--text-main)}
  mark{background:var(--accent-soft);color:var(--text-main);padding:0 2px;border-radius:3px}
</style>
</head>
<body>
<nav class="topnav" role="navigation" aria-label="グローバル">
  <a href="{{ nav_prefix }}">Tech</a>
  <a href="{{ nav_prefix }}news/">News</a>
  <a href="{{ nav_prefix }}forecast/">Forecast</a>
  <a href="{{ nav_prefix }}ops/">Ops</a>
  <a href="{{ nav_prefix }}search.html" class="active">Search</a>
</nav>
<main class="search-wrap">
<h1>記事検索</h1>
<p class="search-meta">タイトル・日本語タイトル・本文を対象にキーワード検索します（インデックス件数: <span id="total">0</span>）。</p>
<input id="q" class="search-input" type="search" placeholder="キーワード（スペース区切りでAND検索）" autofocus>
<div id="meta" class="search-meta"></div>
<div id="results"></div>
</main>
<script>
(function(){
  const q = document.getElementById('q');
  const results = document.getElementById('results');
  const total = document.getElementById('total');
  const meta = document.getElementById('meta');
  let data = [];

  function escapeHtml(s){
    return (s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
  }
  function highlight(text, terms){
    let out = escapeHtml(text);
    for (const t of terms){
      if (!t) continue;
      const re = new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&') + ')','gi');
      out = out.replace(re, '<mark>$1</mark>');
    }
    return out;
  }
  function render(query){
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0){ results.innerHTML = ''; meta.textContent=''; return; }
    const hits = [];
    for (const row of data){
      const hay = ((row.t||'') + ' ' + (row.tj||'') + ' ' + (row.s||'')).toLowerCase();
      if (terms.every(t => hay.includes(t))) hits.push(row);
      if (hits.length >= 200) break;
    }
    meta.textContent = hits.length + ' 件ヒット（最大200件表示）';
    const html = hits.map(h => `
      <div class="search-hit">
        <h3><a href="${escapeHtml(h.u)}" target="_blank" rel="noopener">${highlight(h.tj||h.t, terms)}</a></h3>
        <div class="meta">${escapeHtml(h.c||'')} · ${escapeHtml(h.d||'')} · ${escapeHtml(h.src||'')}</div>
        <div class="snippet">${highlight((h.s||'').slice(0,200), terms)}</div>
      </div>`).join('');
    results.innerHTML = html;
  }
  // インデックス(約2MB)はページ表示時ではなく最初の入力時に遅延ロードする
  let loading = null;
  function ensureIndex(){
    if (!loading){
      meta.textContent = '検索インデックスを読み込み中…';
      loading = fetch('search-index.json').then(r => r.json()).then(rows => {
        data = rows;
        total.textContent = rows.length;
      }).catch(err => { meta.textContent = '検索インデックスを読み込めませんでした: ' + err; });
    }
    return loading;
  }
  q.addEventListener('focus', () => { ensureIndex(); }, { once: true });
  q.addEventListener('input', () => { ensureIndex().then(() => render(q.value)); });
})();
</script>
</body>
</html>
"""


def render_sitemap(out_dir: Path | str, cur, *, site_url: str | None = None) -> None:
    """docs/ 配下の主要ページを列挙した sitemap.xml を生成する。

    対象:
    - ルート / tech / news / forecast / ops / search / exec / diff / feed.xml
    - docs/forecast/<date>/index.html（過去レポート）
    - docs/exec/<category>.html
    - docs/topic/<id>/index.html（トピックタイムライン、存在するもののみ）
    - docs/entity/<slug>/index.html（エンティティページ、存在するもののみ）
    """
    out_dir = Path(out_dir)
    base = (site_url or FEED_SITE_URL).rstrip("/")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls: list[tuple[str, str]] = []  # (loc, lastmod)

    static_paths = [
        "",
        "news/",
        "forecast/",
        "ops/",
        "search.html",
        "feed.xml",
        "exec/",
        "diff/",
    ]
    for p in static_paths:
        target = out_dir / p if not p.endswith("/") else out_dir / p / "index.html"
        # 存在しないファイルは sitemap にも入れない
        check = out_dir / p if p else out_dir / "index.html"
        # 簡略化: 有無にかかわらず主要導線は含める（無い場合は公開前＝404になるが許容）
        urls.append((f"{base}/{p}", now_iso))

    # 過去フォーキャストレポート
    if (out_dir / "forecast").exists():
        for d in sorted((out_dir / "forecast").glob("2*-*-*")):
            if d.is_dir():
                urls.append((f"{base}/forecast/{d.name}/", d.name))

    # exec summary ページ
    exec_dir = out_dir / "exec"
    if exec_dir.exists():
        for f in sorted(exec_dir.glob("*.html")):
            if f.name == "index.html":
                continue
            urls.append((f"{base}/exec/{f.name}", now_iso))

    # トピックタイムライン
    topic_dir = out_dir / "topic"
    if topic_dir.exists():
        for d in sorted(topic_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                urls.append((f"{base}/topic/{d.name}/", now_iso))

    # エンティティページ
    entity_dir = out_dir / "entity"
    if entity_dir.exists():
        for d in sorted(entity_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                urls.append((f"{base}/entity/{d.name}/", now_iso))

    url_tags = "".join(
        f"<url><loc>{_rss_escape(loc)}</loc><lastmod>{_rss_escape(lastmod)}</lastmod></url>"
        for loc, lastmod in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + url_tags
        + "</urlset>\n"
    )
    (out_dir / "sitemap.xml").write_text(xml, encoding="utf-8")
    print(f"  sitemap: {out_dir / 'sitemap.xml'} ({len(urls)}件)")


def render_json_api(out_dir: Path | str, cur) -> None:
    """docs/api/ 配下に topics.json / forecast.json / feed_health.json を書き出す。

    他プロジェクトから static hosting 経由で fetch 可能な公開 API。
    更新頻度は日次。個人情報・機微なしのみ含める。
    """
    out_dir = Path(out_dir)
    api_dir = out_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- topics.json: 最新 insight 付きトピック 100件 ---
    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(t.category, ''),
          COALESCE(ti.importance, 0),
          COALESCE(ti.summary, ''),
          COALESCE(ti.updated_at, t.created_at)
        FROM topics t
        LEFT JOIN topic_insights ti ON ti.topic_id = t.id
        WHERE COALESCE(t.title_ja, t.title) IS NOT NULL
          AND COALESCE(t.title_ja, t.title) != ''
        ORDER BY COALESCE(ti.updated_at, t.created_at) DESC
        LIMIT 100
        """
    )
    topics = [
        {
            "id": tid,
            "title": title,
            "category": category,
            "importance": int(importance or 0),
            "summary": summary,
            "updated_at": updated_at,
        }
        for (tid, title, category, importance, summary, updated_at) in cur.fetchall()
    ]
    (api_dir / "topics.json").write_text(
        json.dumps(
            {"generated_at": generated_at, "count": len(topics), "items": topics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --- forecast.json: 最新予測レポート＋時間軸別精度 ---
    forecast_data: dict = {"generated_at": generated_at}
    try:
        cur.execute(
            "SELECT report_date, executive_summary, accuracy_score FROM forecast_reports "
            "ORDER BY report_date DESC LIMIT 1"
        )
        latest = cur.fetchone()
        if latest:
            forecast_data["latest"] = {
                "report_date": latest[0],
                "executive_summary": latest[1],
                "accuracy_score": latest[2],
            }
        cur.execute(
            "SELECT report_date, horizon, accuracy_score FROM forecast_verifications "
            "WHERE accuracy_score IS NOT NULL "
            "ORDER BY report_date DESC LIMIT 50"
        )
        forecast_data["verifications"] = [
            {"report_date": r[0], "horizon": r[1], "accuracy": r[2]}
            for r in cur.fetchall()
        ]
    except Exception as e:
        _logger.debug("forecast api skipped: %s", e)
        forecast_data["error"] = "unavailable"

    (api_dir / "forecast.json").write_text(
        json.dumps(forecast_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- feed_health.json: フィード健全性 ---
    try:
        cur.execute(
            "SELECT feed_url, failure_count, last_success_at, last_failure_reason "
            "FROM feed_health ORDER BY failure_count DESC, feed_url"
        )
        feeds = [
            {
                "url": r[0],
                "failure_count": int(r[1] or 0),
                "last_success_at": r[2],
                "last_failure_reason": r[3],
            }
            for r in cur.fetchall()
        ]
    except Exception:
        feeds = []
    (api_dir / "feed_health.json").write_text(
        json.dumps(
            {"generated_at": generated_at, "count": len(feeds), "items": feeds},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"  json api: {api_dir}/ (topics={len(topics)}, feeds={len(feeds)})")


def render_search_page(
    out_dir: Path | str,
    generated_at: str,
    cur,
    limit: int = 3000,
    *,
    common_css_href: str = "/daily-tech-trend/assets/css/common.css",
    nav_prefix: str = "/daily-tech-trend/",
) -> None:
    """検索用JSON + search.html を出力する。

    JSON は軽量化のため短いキー (u,t,tj,s,c,d,src) で保存。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cur.execute(
        """
        SELECT
          COALESCE(title,'') AS title,
          COALESCE(title_ja,'') AS title_ja,
          COALESCE(substr(content,1,400),'') AS snippet,
          COALESCE(category,'') AS category,
          COALESCE(substr(published_at,1,16),'') AS dt,
          COALESCE(source,'') AS source,
          COALESCE(url,'') AS url
        FROM articles
        WHERE url IS NOT NULL AND url != ''
        ORDER BY published_at DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows: list[dict] = []
    for title, title_ja, snippet, category, dt, source, url in cur.fetchall():
        rows.append({
            "u": url,
            "t": title,
            "tj": title_ja,
            "s": snippet,
            "c": category,
            "d": dt,
            "src": source,
        })

    (out_dir / "search-index.json").write_text(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    html = Template(SEARCH_HTML).render(
        common_css_href=common_css_href,
        nav_prefix=nav_prefix,
    )
    (out_dir / "search.html").write_text(html, encoding="utf-8")
    print(f"  search page: {out_dir / 'search.html'} (index={len(rows)}件)")
