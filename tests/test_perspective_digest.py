import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm_insights_api


class DummyResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self._payload = {"choices": [{"message": {"content": content}}]}

    def json(self):
        return self._payload


def _long_text(n: int, seed: str = "本") -> str:
    """指定文字数(概ね)の日本語ダミーテキストを作る。"""
    return (seed * n)[:n]


# --- _extract_evidence_domain ------------------------------------------------

def test_extract_evidence_domain_returns_netloc():
    got = llm_insights_api._extract_evidence_domain(["https://example.com/path/to/article"])
    assert got == "example.com"


def test_extract_evidence_domain_handles_empty_list():
    assert llm_insights_api._extract_evidence_domain([]) == ""
    assert llm_insights_api._extract_evidence_domain(None) == ""


def test_extract_evidence_domain_handles_invalid_url_without_raising():
    got = llm_insights_api._extract_evidence_domain(["", None, "   ", "not a url ::::"])
    # 例外を投げず、有効なnetlocが無ければ空文字を返す
    assert isinstance(got, str)


# --- _normalize_perspective_digest ------------------------------------------

def test_normalize_perspective_digest_accepts_japanese_aliases():
    text = _long_text(180)
    raw = {
        "技術者目線": text,
        "経営者目線": text,
        "利用者目線": text,
    }

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=["https://example.com/a"])

    assert got["engineer"].startswith(text)
    assert got["management"].startswith(text)
    assert got["consumer"].startswith(text)


def test_normalize_perspective_digest_drops_too_short_values():
    short_text = _long_text(50)  # 120字未満
    raw = {"engineer": short_text, "management": "", "consumer": None}

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=["https://example.com/a"])

    assert got["engineer"] == ""
    assert got["management"] == ""
    assert got["consumer"] == ""


def test_normalize_perspective_digest_truncates_over_max_len_with_ellipsis():
    long_text = _long_text(300)  # 260字超
    raw = {"engineer": long_text}

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=["https://example.com/a"])

    # 本文は切り詰められ "…" が付き、末尾に参考ドメインsuffixが付与される
    assert "…（参考: example.com）" in got["engineer"]
    assert got["engineer"].endswith("（参考: example.com）")


def test_normalize_perspective_digest_appends_domain_when_evidence_present():
    text = _long_text(180)
    raw = {"engineer": text}

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=["https://news.example.co.jp/a"])

    assert "（参考: news.example.co.jp）" in got["engineer"]


def test_normalize_perspective_digest_flags_missing_evidence():
    text = _long_text(180)
    raw = {"engineer": text}

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=[])

    assert "（参考情報未取得）" in got["engineer"]


def test_normalize_perspective_digest_treats_sample_text_as_empty():
    raw = {
        "engineer": "技術者向けの考え方・推奨行動・注意点を含む200字前後の説明",
        "management": "経営者向けの考え方・推奨行動・注意点を含む200字前後の説明",
        "consumer": "消費者向けの考え方・推奨行動・注意点を含む200字前後の説明",
    }

    got = llm_insights_api._normalize_perspective_digest(raw, evidence_urls=["https://example.com/a"])

    assert got == {"engineer": "", "management": "", "consumer": ""}


# --- call_llm_perspective_digest --------------------------------------------

def test_call_llm_perspective_digest_builds_normalized_digest(monkeypatch):
    text = _long_text(180)
    payload = (
        '{"perspective_digest": {'
        f'"engineer": "{text}", "management": "{text}", "consumer": "{text}"'
        "}}"
    )

    monkeypatch.setattr(llm_insights_api, "_pick_usable_model", lambda *args, **kwargs: "dummy/model")
    monkeypatch.setattr(llm_insights_api, "post_ollama", lambda *_args, **_kwargs: DummyResponse(payload))

    got = llm_insights_api.call_llm_perspective_digest(
        "タイトル",
        "要約",
        {"engineer": "短評E", "management": "短評M", "consumer": "短評C"},
        url="https://example.com/news/1",
    )

    assert got["engineer"].startswith(text)
    assert "（参考: example.com）" in got["engineer"]
    assert got["management"].startswith(text)
    assert got["consumer"].startswith(text)
