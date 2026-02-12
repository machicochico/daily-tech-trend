import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import llm_insights_local
import render
from llm_insights_pipeline import postprocess_insight


def test_render_json_helpers_compat():
    assert render._safe_json_list('["a",1,null]') == ["a", "1"]
    assert render._safe_json_obj('{"a":1}') == {"a": 1}


def test_render_query_functions_exist_and_run():
    conn = sqlite3.connect(':memory:')
    cur = conn.cursor()
    cur.execute('create table articles (id integer primary key, title_ja text, title text, url text, source text, category text, region text, published_at text, fetched_at text, kind text)')
    cur.execute('create table topic_articles (topic_id integer, article_id integer)')
    cur.execute('create table topic_insights (topic_id integer, importance integer, tags text, summary text, type text, key_points text, perspectives text, evidence_urls text)')
    cur.execute("insert into articles values (1,'','t','u','s','policy','jp','2025-01-01 00:00:00','2025-01-01 00:00:00','news')")
    conn.commit()

    rows = render.fetch_news_articles(cur, 'jp', 10)
    assert len(rows) == 1


def test_llm_postprocess_news_fills_required_fields():
    row = {"category": "news", "kind": "news", "url": "https://example.com"}
    out = postprocess_insight({"importance": 0, "summary": "ok", "key_points": []}, row)
    assert out["importance"] >= 10
    assert len(out["key_points"]) == 3
    assert out["evidence_urls"] == ["https://example.com"]


def test_llm_wrapper_exports():
    assert callable(llm_insights_local.call_llm)
    assert callable(llm_insights_local.post_lmstudio)
