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


def test_normalize_perspectives_accepts_japanese_keys():
    raw = {
        "技術者目線": "推測: API変更の影響調査が必要",
        "経営者目線": "推測: 対外説明の準備が必要",
        "利用者目線": "推測: 利用者への告知が必要",
    }

    got = llm_insights_api._normalize_perspectives(raw)

    assert got["engineer"] == "推測: API変更の影響調査が必要"
    assert got["management"] == "推測: 対外説明の準備が必要"
    assert got["consumer"] == "推測: 利用者への告知が必要"


def test_call_llm_short_news_uses_normalized_perspectives(monkeypatch):
    payload = (
        '{"importance": 60, "summary": "障害復旧の見通しが発表された。", '
        '"key_points": ["事実1"], '
        '"perspectives": {"技術者目線": "推測: 切り戻し条件の確認が必要", '
        '"経営者目線": "推測: SLA違反時の説明準備が必要", '
        '"消費者目線": "推測: 代替手段の案内確認が必要"}, '
        '"inferred": 1}'
    )

    monkeypatch.setattr(llm_insights_api, "_pick_usable_model", lambda *args, **kwargs: "dummy/model")
    monkeypatch.setattr(llm_insights_api, "post_lmstudio", lambda *_args, **_kwargs: DummyResponse(payload))

    got = llm_insights_api.call_llm_short_news("タイトル", "本文", url="https://example.com")

    assert got["perspectives"]["engineer"] == "推測: 切り戻し条件の確認が必要"
    assert got["perspectives"]["management"] == "推測: SLA違反時の説明準備が必要"
    assert got["perspectives"]["consumer"] == "推測: 代替手段の案内確認が必要"
