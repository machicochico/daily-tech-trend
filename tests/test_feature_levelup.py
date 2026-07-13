"""機能レベルアップ群の単体テスト。

対象:
- feed_quality.compute_feed_quality / _freshness_score / _failure_score
- notify._format_slack_blocks / _format_discord_embeds / collect_notifiable_topics
- diff_view.compute_diff
- entities._slugify / extract_entities_by_dict
- topic_timeline.render_topic_timelines
- render_feeds.render_sitemap / render_json_api
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# --- feed_quality -----------------------------------------------------------
def test_failure_score_boundaries():
    from feed_quality import _failure_score
    assert _failure_score(0) == 1.0
    assert _failure_score(10) == 0.0
    assert _failure_score(20) == 0.0
    # 線形の中間点
    assert 0.4 < _failure_score(5) < 0.6


def test_freshness_score_boundaries():
    from feed_quality import _freshness_score
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    assert _freshness_score(None) == 0.0
    assert _freshness_score("not-a-date") == 0.0
    # 今 → 1.0
    fresh = (now - timedelta(hours=1)).isoformat(timespec="seconds")
    assert _freshness_score(fresh) == 1.0
    # 10日前 → 0.0
    stale = (now - timedelta(days=10)).isoformat(timespec="seconds")
    assert _freshness_score(stale) == 0.0


def test_compute_feed_quality_returns_list():
    from feed_quality import compute_feed_quality
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE feed_health(feed_url TEXT, failure_count INTEGER, last_success_at TEXT, last_failure_reason TEXT)")
    cur.execute("CREATE TABLE articles(id INTEGER, source TEXT, source_tier TEXT)")
    cur.execute("INSERT INTO feed_health VALUES('https://example.com/rss', 0, '2026-04-20T00:00:00', '')")
    cur.execute("INSERT INTO feed_health VALUES('https://bad.com/rss', 20, '', 'timeout')")
    conn.commit()
    results = compute_feed_quality(cur)
    assert len(results) == 2
    # 問題フィードが先頭（昇順）
    assert results[0]["failure_count"] >= results[-1]["failure_count"]
    assert 0 <= results[0]["score"] <= 100


# --- notify -----------------------------------------------------------------
def test_slack_payload_has_blocks():
    from notify import _format_slack_blocks
    payload = _format_slack_blocks([
        {"id": 1, "title": "T1", "category": "ai", "importance": 90, "summary": "要約",
         "updated_at": "2026-04-20"},
    ])
    assert "blocks" in payload
    assert any(b["type"] == "header" for b in payload["blocks"])
    assert any("T1" in json.dumps(b, ensure_ascii=False) for b in payload["blocks"])


def test_discord_payload_has_embeds():
    from notify import _format_discord_embeds
    payload = _format_discord_embeds([
        {"id": 1, "title": "危険度高", "category": "security", "importance": 95,
         "summary": "s", "updated_at": "2026-04-20"},
    ])
    assert payload["embeds"][0]["color"] == 0xDC2626
    # Discord の embeds は 10 件まで
    many = [
        {"id": i, "title": f"t{i}", "category": "x", "importance": 50, "summary": "",
         "updated_at": ""}
        for i in range(20)
    ]
    from notify import _format_discord_embeds as fmt
    assert len(fmt(many)["embeds"]) == 10


def test_collect_notifiable_topics_filters_by_importance():
    from notify import collect_notifiable_topics
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE topics(id INTEGER PRIMARY KEY, title TEXT, title_ja TEXT, category TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE topic_insights(topic_id INTEGER PRIMARY KEY, importance INTEGER, summary TEXT, updated_at TEXT)")
    cur.execute("INSERT INTO topics VALUES(1,'','T1','ai', datetime('now'))")
    cur.execute("INSERT INTO topic_insights VALUES(1, 90, 'sum', datetime('now'))")
    cur.execute("INSERT INTO topics VALUES(2,'','T2','ai', datetime('now'))")
    cur.execute("INSERT INTO topic_insights VALUES(2, 50, 'sum', datetime('now'))")
    conn.commit()
    items = collect_notifiable_topics(cur, min_importance=80, limit=10)
    assert len(items) == 1
    assert items[0]["title"] == "T1"


# --- diff_view --------------------------------------------------------------
def test_diff_view_detects_trending_and_fading():
    from diff_view import compute_diff
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE topic_snapshots(report_date TEXT, topic_id INTEGER, importance INTEGER, category TEXT, title TEXT, PRIMARY KEY(report_date, topic_id))")
    # 前日
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-19', 1, 50, 'ai', '昨日既存')")
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-19', 2, 80, 'ai', '昨日急上昇予備')")
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-19', 3, 70, 'ai', '失速予備')")
    # 今日
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-20', 1, 55, 'ai', '昨日既存')")  # ±差異小
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-20', 2, 95, 'ai', '昨日急上昇予備')")  # +15
    cur.execute("INSERT INTO topic_snapshots VALUES('2026-04-20', 4, 60, 'security', '新規')")  # new
    # topic 3 は今日消失
    conn.commit()

    diff = compute_diff(conn, gap_threshold=10)
    assert diff["today"] == "2026-04-20"
    assert diff["prev"] == "2026-04-19"
    # new
    new_titles = [x["title"] for x in diff["new_today"]]
    assert "新規" in new_titles
    # trending
    trending_titles = [x["title"] for x in diff["trending"]]
    assert "昨日急上昇予備" in trending_titles
    # fading: topic 3 消失
    fading_titles = [x["title"] for x in diff["fading"]]
    assert "失速予備" in fading_titles
    # delta=55-50=5 なので、topic 1 は trending にも fading にも入らない
    assert "昨日既存" not in trending_titles
    assert "昨日既存" not in fading_titles


# --- entities ---------------------------------------------------------------
def test_slugify_strips_non_ascii():
    from entities import _slugify
    assert _slugify("Microsoft") == "microsoft"
    assert _slugify("Nippon Steel") == "nippon-steel"
    assert _slugify("日本製鉄") == "unknown"  # 非ASCIIは使わず unknown へ
    assert _slugify("   ") == "unknown"


def test_extract_entities_by_dict_matches_aliases():
    from entities import extract_entities_by_dict
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE entities(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, slug TEXT UNIQUE, kind TEXT, aliases TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE article_entities(article_id INTEGER, entity_id INTEGER, confidence REAL, PRIMARY KEY(article_id, entity_id))")
    cur.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT, title_ja TEXT, content TEXT)")
    cur.execute("INSERT INTO articles VALUES(1, 'Microsoft announces Windows', '', 'Something about マイクロソフト and Windows Server')")
    cur.execute("INSERT INTO articles VALUES(2, '無関係の記事', '', '特に何も')")
    conn.commit()

    stats = extract_entities_by_dict(conn, limit_articles=100)
    assert stats["entities"] > 0
    # article 1 に Microsoft と Windows が紐づくはず
    cur.execute("SELECT e.slug FROM article_entities ae JOIN entities e ON e.id=ae.entity_id WHERE ae.article_id=1")
    slugs = {r[0] for r in cur.fetchall()}
    assert "microsoft" in slugs
    assert "windows" in slugs
    # article 2 には何も紐づかない
    cur.execute("SELECT COUNT(*) FROM article_entities WHERE article_id=2")
    assert cur.fetchone()[0] == 0


# --- topic_timeline ---------------------------------------------------------
def test_render_topic_timelines_writes_html(tmp_path: Path):
    from topic_timeline import render_topic_timelines
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE topics(id INTEGER PRIMARY KEY, title TEXT, title_ja TEXT, category TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE topic_insights(topic_id INTEGER PRIMARY KEY, importance INTEGER, summary TEXT, updated_at TEXT)")
    cur.execute("CREATE TABLE topic_articles(topic_id INTEGER, article_id INTEGER)")
    cur.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT, title_ja TEXT, source TEXT, url TEXT, published_at TEXT, fetched_at TEXT, content TEXT)")
    cur.execute("INSERT INTO topics VALUES(1,'','テストトピック','ai','2026-04-20')")
    cur.execute("INSERT INTO topic_insights VALUES(1, 90, 'サマリ', '2026-04-20')")
    cur.execute("INSERT INTO articles VALUES(1,'','記事1','src1','https://a','2026-04-19','2026-04-19','本文1')")
    cur.execute("INSERT INTO articles VALUES(2,'','記事2','src2','https://b','2026-04-20','2026-04-20','本文2')")
    cur.execute("INSERT INTO topic_articles VALUES(1,1)")
    cur.execute("INSERT INTO topic_articles VALUES(1,2)")
    conn.commit()
    n = render_topic_timelines(tmp_path, top_n=10, conn=conn)
    assert n == 1
    html = (tmp_path / "topic" / "1" / "index.html").read_text(encoding="utf-8")
    assert "テストトピック" in html
    assert "記事1" in html
    assert "記事2" in html


# --- render_feeds sitemap / api --------------------------------------------
def test_render_sitemap_includes_static_paths(tmp_path: Path):
    from render_feeds import render_sitemap
    conn = sqlite3.connect(":memory:")
    render_sitemap(tmp_path, conn.cursor())
    xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert "<?xml" in xml
    assert "urlset" in xml
    # 静的パスの主要 URL が含まれる
    assert "news/" in xml
    assert "forecast/" in xml
    assert "search.html" in xml


def test_render_json_api_produces_files(tmp_path: Path):
    from render_feeds import render_json_api
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE topics(id INTEGER PRIMARY KEY, title TEXT, title_ja TEXT, category TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE topic_insights(topic_id INTEGER PRIMARY KEY, importance INTEGER, summary TEXT, updated_at TEXT)")
    cur.execute("CREATE TABLE forecast_reports(report_date TEXT PRIMARY KEY, executive_summary TEXT, accuracy_score REAL)")
    cur.execute("CREATE TABLE forecast_verifications(report_date TEXT, horizon TEXT, accuracy_score REAL)")
    cur.execute("CREATE TABLE feed_health(feed_url TEXT, failure_count INTEGER, last_success_at TEXT, last_failure_reason TEXT)")
    cur.execute("INSERT INTO topics VALUES(1,'','t','ai','2026-04-20')")
    cur.execute("INSERT INTO topic_insights VALUES(1, 80, 's', '2026-04-20')")
    conn.commit()
    render_json_api(tmp_path, cur)
    assert (tmp_path / "api" / "topics.json").exists()
    assert (tmp_path / "api" / "forecast.json").exists()
    assert (tmp_path / "api" / "feed_health.json").exists()

    data = json.loads((tmp_path / "api" / "topics.json").read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert data["items"][0]["importance"] == 80


# --- forecast_generate retry ------------------------------------------------
def test_generate_predictions_retries_on_empty(monkeypatch):
    """初回 0 件なら temperature を上げて再試行する。"""
    import forecast_generate as fg

    call_count = {"n": 0}

    def fake_call(system, user, max_tokens=16000, temperature=0.4, max_retries=2):
        call_count["n"] += 1
        # 初回は空、2回目は中身ありを返す
        if call_count["n"] == 1:
            return [{"title": ""}]  # 空殻のみ → フィルタで除外
        return [{"title": "ok", "prediction": "x", "evidence": "y", "impact": "大", "confidence": "高"}]

    monkeypatch.setattr(fg, "_call_llm_json", fake_call)
    result = fg.generate_predictions("digest", "1週間後")
    assert call_count["n"] == 2  # 再試行した
    assert result and result[0]["title"] == "ok"
