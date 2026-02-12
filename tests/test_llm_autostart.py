import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm_insights_api


class DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "{}"}}]}
        self.text = "ok"

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, get_results=None):
        self.get_results = list(get_results or [])
        self.post_calls = 0

    def get(self, *_args, **_kwargs):
        if not self.get_results:
            raise RuntimeError("not ready")
        result = self.get_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return DummyResponse(status_code=result)

    def post(self, *_args, **_kwargs):
        self.post_calls += 1
        return DummyResponse()


def _reset_flags():
    llm_insights_api._LMSTUDIO_READY = False
    llm_insights_api._AUTOSTART_ATTEMPTED = False


def test_post_lmstudio_uses_existing_running_server(monkeypatch):
    _reset_flags()
    session = DummySession(get_results=[200])
    monkeypatch.setattr(llm_insights_api, "_SESSION", session)

    res = llm_insights_api.post_lmstudio({"model": "x"}, timeout=1)

    assert res.status_code == 200
    assert session.post_calls == 1


def test_post_lmstudio_errors_when_server_down_without_autostart(monkeypatch):
    _reset_flags()
    monkeypatch.setattr(llm_insights_api, "_SESSION", DummySession(get_results=[]))
    monkeypatch.delenv("LMSTUDIO_AUTOSTART_CMD", raising=False)

    with pytest.raises(RuntimeError) as e:
        llm_insights_api.post_lmstudio({"model": "x"}, timeout=1)

    assert "LMSTUDIO_AUTOSTART_CMD" in str(e.value)


def test_post_lmstudio_autostarts_and_waits_until_ready(monkeypatch):
    _reset_flags()
    session = DummySession(get_results=[RuntimeError("down"), RuntimeError("down"), 200])
    monkeypatch.setattr(llm_insights_api, "_SESSION", session)
    monkeypatch.setenv("LMSTUDIO_AUTOSTART_CMD", "echo start")
    monkeypatch.setenv("LMSTUDIO_AUTOSTART_WAIT_SEC", "3")

    launched = {"ok": False}

    def fake_popen(*_args, **_kwargs):
        launched["ok"] = True

    monkeypatch.setattr(llm_insights_api.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(llm_insights_api.time, "sleep", lambda *_args, **_kwargs: None)

    res = llm_insights_api.post_lmstudio({"model": "x"}, timeout=1)

    assert launched["ok"]
    assert res.status_code == 200
    assert session.post_calls == 1
