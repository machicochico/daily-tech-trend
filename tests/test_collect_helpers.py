"""collect.py の純関数ヘルパーに対する単体テスト。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import collect


# --- should_fetch_fulltext -------------------------------------------------
def test_should_fetch_fulltext_skips_unknown_source():
    assert not collect.should_fetch_fulltext("UnknownSource", "x", 0, 30)


def test_should_fetch_fulltext_fetches_when_content_thin():
    # FULLTEXT_SOURCES に含まれるソース名で、本文が短いならフェッチする
    src = next(iter(collect.FULLTEXT_SOURCES))
    assert collect.should_fetch_fulltext(src, "short", 0, 30) is True


def test_should_fetch_fulltext_stops_at_limit():
    src = next(iter(collect.FULLTEXT_SOURCES))
    assert collect.should_fetch_fulltext(src, "short", 30, 30) is False


def test_should_fetch_fulltext_skips_when_content_enough():
    src = next(iter(collect.FULLTEXT_SOURCES))
    big = "a" * (collect.MIN_CONTENT_CHARS + 10)
    assert collect.should_fetch_fulltext(src, big, 0, 30) is False


# --- fetch_fulltext --------------------------------------------------------
def test_fetch_fulltext_returns_empty_for_skipped_domain():
    # NHK 等は SKIP_FETCH_DOMAINS に入っており即座に空文字を返す
    assert collect.fetch_fulltext("https://www3.nhk.or.jp/news/a", source="NHK") == ""


def test_fetch_fulltext_returns_empty_on_network_error():
    """urlopen が例外を投げても fetch_fulltext は空文字を返す。"""
    with patch("collect.urllib.request.urlopen", side_effect=TimeoutError("fake")):
        assert collect.fetch_fulltext("https://example.com/article") == ""


def test_fetch_fulltext_extracts_text_from_html():
    """正常系: HTML から strip された本文を返す。"""
    # MIN_CONTENT_CHARS 超になるよう冗長な本文を仕込む
    body_text = "本文テスト。" * 50
    fake_html = f"<html><head><title>T</title></head><body><p>{body_text}</p></body></html>".encode("utf-8")

    class FakeResp:
        # HTTP ヘッダは dict.get でアクセスされるため、"Content-Type" キーで返す
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def read(self, n=None):
            return fake_html

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("collect.urllib.request.urlopen", return_value=FakeResp()):
        out = collect.fetch_fulltext("https://example.com/article")

    assert "本文テスト" in out
    assert "<p>" not in out  # タグは除去される


# --- _prefetch_feeds -------------------------------------------------------
def test_prefetch_feeds_returns_successful_urls(monkeypatch):
    """_prefetch_feeds が成功分だけマップに入れることを検証する。"""
    # _fetch_single_feed は内部で _parse_feed_with_requests を呼ぶため、
    # そちらをモックする。
    def fake_parse_with_requests(url, *, tls_mode, user_agent=None):
        if "good" in url:
            return {"entries": []}  # parsed っぽいダミー
        raise RuntimeError("network fail")

    monkeypatch.setattr(collect, "_parse_feed_with_requests", fake_parse_with_requests)

    feed_list = [
        {"url": "https://good.example.com/rss"},
        {"url": "https://bad.example.com/rss"},
    ]
    result = collect._prefetch_feeds(feed_list)
    assert "https://good.example.com/rss" in result
    assert "https://bad.example.com/rss" not in result


# --- classify_error --------------------------------------------------------
def test_classify_error_timeout():
    import socket
    assert collect.classify_error(socket.timeout()) == "timeout_error"


def test_classify_error_unknown():
    class CustomErr(Exception):
        pass
    assert collect.classify_error(CustomErr("x")) == "parse_error"


def test_classify_error_hint_overrides():
    assert collect.classify_error(ValueError("x"), hint="my_hint") == "my_hint"
