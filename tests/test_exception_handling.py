import sqlite3
import ssl
import sys
from pathlib import Path
from urllib.error import URLError

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import collect
import llm_insights_local
import translate


def test_fetch_fulltext_logs_context_and_skips_on_network_error(monkeypatch, capsys):
    def fake_urlopen(*args, **kwargs):
        raise URLError("network down")

    monkeypatch.setattr(collect.urllib.request, "urlopen", fake_urlopen)

    out = collect.fetch_fulltext("https://example.com/a", source="example-source")
    assert out == ""
    captured = capsys.readouterr().out
    assert "source=example-source" in captured
    assert "url=https://example.com/a" in captured


def test_translate_news_titles_skips_request_failures_and_keeps_running(monkeypatch):
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("create table articles (id integer primary key, title text, title_ja text, kind text, published_at text)")
    cur.execute("insert into articles values (1, 'hello', '', 'news', '2025-01-01T00:00:00+00:00')")
    cur.execute("insert into articles values (2, 'world', '', 'news', '2025-01-01T00:00:00+00:00')")
    conn.commit()

    calls = {"n": 0}

    def fake_translate(text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.RequestException("temporary error")
        return "翻訳"

    monkeypatch.setattr(translate, "translate", fake_translate)
    translate.translate_news_titles(conn, limit=10)

    rows = conn.execute("select id, title_ja from articles order by id").fetchall()
    assert rows == [(1, "翻訳"), (2, "")]


class DummyConn:
    def __init__(self):
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1


def test_llm_main_skips_expected_generation_errors(monkeypatch, capsys):
    rows = [
        {
            "topic_id": 1,
            "topic_title": "t1",
            "url": "https://a",
            "body": "b1",
            "prev_src_hash": "",
            "category": "news",
            "kind": "news",
            "src_article_id": 10,
            "source": "src1",
        },
        {
            "topic_id": 2,
            "topic_title": "t2",
            "url": "https://b",
            "body": "b2",
            "prev_src_hash": "",
            "category": "news",
            "kind": "news",
            "src_article_id": 11,
            "source": "src2",
        },
    ]
    conn = DummyConn()
    saved = []

    monkeypatch.setattr(llm_insights_local, "connect", lambda: conn)
    monkeypatch.setattr(llm_insights_local, "pick_topic_inputs", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(llm_insights_local, "compute_src_hash", lambda *_args: "h")

    def fake_call_llm(title, *_args, **_kwargs):
        if title == "t1":
            raise RuntimeError("llm timeout")
        return {"importance": 1, "summary": "ok", "key_points": ["a", "b", "c"], "perspectives": {"engineer": "e", "management": "m", "consumer": "c"}}

    monkeypatch.setattr(llm_insights_local, "call_llm", fake_call_llm)
    monkeypatch.setattr(llm_insights_local, "postprocess_insight", lambda raw, _row: raw)
    monkeypatch.setattr(llm_insights_local, "upsert_insight", lambda _conn, topic_id, *_args: saved.append(topic_id))
    monkeypatch.setattr(llm_insights_local.sys, "argv", ["llm_insights_local.py", "2"])

    llm_insights_local.main()

    assert saved == [2]
    assert "topic_id=1" in capsys.readouterr().out


def test_llm_main_re_raises_db_errors(monkeypatch):
    rows = [
        {
            "topic_id": 1,
            "topic_title": "t1",
            "url": "https://a",
            "body": "b1",
            "prev_src_hash": "",
            "category": "news",
            "kind": "news",
            "src_article_id": 10,
            "source": "src1",
        }
    ]

    monkeypatch.setattr(llm_insights_local, "connect", lambda: DummyConn())
    monkeypatch.setattr(llm_insights_local, "pick_topic_inputs", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(llm_insights_local, "compute_src_hash", lambda *_args: "h")
    monkeypatch.setattr(llm_insights_local, "call_llm", lambda *_args, **_kwargs: {"importance": 1, "summary": "ok", "key_points": ["a", "b", "c"], "perspectives": {"engineer": "e", "management": "m", "consumer": "c"}})
    monkeypatch.setattr(llm_insights_local, "postprocess_insight", lambda raw, _row: raw)
    monkeypatch.setattr(llm_insights_local, "upsert_insight", lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("db down")))
    monkeypatch.setattr(llm_insights_local.sys, "argv", ["llm_insights_local.py", "1"])

    with pytest.raises(sqlite3.OperationalError):
        llm_insights_local.main()


def test_collect_main_marks_ssl_failure_after_single_retry(monkeypatch, tmp_path):
    db_path = tmp_path / "state.sqlite"

    def fake_init_db():
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                region TEXT,
                source TEXT,
                title TEXT,
                title_ja TEXT,
                url TEXT UNIQUE,
                url_norm TEXT,
                content TEXT,
                category TEXT,
                source_tier TEXT,
                published_at TEXT,
                fetched_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS low_priority_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                title TEXT,
                content TEXT,
                source TEXT,
                vendor TEXT,
                category TEXT,
                source_tier TEXT,
                published_at TEXT,
                fetched_at TEXT,
                kind TEXT,
                region TEXT,
                reason TEXT,
                queued_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feed_health (
                feed_url TEXT PRIMARY KEY,
                failure_count INTEGER DEFAULT 0,
                last_success_at TEXT,
                last_failure_reason TEXT,
                suspend_until TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    monkeypatch.setattr(collect, "init_db", fake_init_db)
    monkeypatch.setattr(collect, "connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(
        collect,
        "load_feed_list",
        lambda _cfg: [
            {
                "url": "https://ssl.example.com/feed.xml",
                "source": "SSL Feed",
                "category": "ai",
                "vendor": "SSL Feed",
                "source_tier": "secondary",
                "kind": "tech",
                "region": "global",
                "limit": 10,
                "weekly_new_limit": None,
                "tls_mode": "strict",
            }
        ],
    )

    monkeypatch.setattr(
        collect.feedparser,
        "parse",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ssl.SSLError("certificate verify failed")),
    )
    monkeypatch.setattr(
        collect.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.exceptions.SSLError("certificate verify failed")),
    )

    collect.main()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT failure_count, last_failure_reason FROM feed_health WHERE feed_url=?",
        ("https://ssl.example.com/feed.xml",),
    ).fetchone()
    conn.close()

    assert row == (1, "ssl_cert_verify_failed")
