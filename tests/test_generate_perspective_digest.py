import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate_perspective_digest as gpd


class _KeepOpenConn:
    """main() が conn.close() を呼んでも実データを保持したまま検証を続けるためのラッパー。"""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        pass


def _setup_db(n: int):
    conn = sqlite3.connect(":memory:")
    conn.execute("create table topics (id integer primary key, title text, title_ja text)")
    conn.execute(
        """
        create table topic_insights (
          topic_id integer primary key,
          summary text,
          perspectives text,
          perspective_digest text,
          evidence_urls text,
          updated_at text
        )
        """
    )
    for i in range(1, n + 1):
        conn.execute("insert into topics values (?, ?, ?)", (i, f"title{i}", f"タイトル{i}"))
        conn.execute(
            "insert into topic_insights (topic_id, summary, perspectives, perspective_digest, evidence_urls, updated_at) "
            "values (?, 'summary', '{}', NULL, '[]', ?)",
            (i, f"2026-07-13T00:00:{i:02d}"),
        )
    conn.commit()
    return conn


def _patch_connect(monkeypatch, conn):
    monkeypatch.setattr(gpd, "connect", lambda: _KeepOpenConn(conn))


def test_processes_all_targets_when_max_sec_is_zero(monkeypatch):
    conn = _setup_db(4)
    _patch_connect(monkeypatch, conn)

    calls = []

    def fake_llm(title, summary, perspectives, url=""):
        calls.append(title)
        return {"engineer": "e", "management": "m", "consumer": "c"}

    monkeypatch.setattr(gpd, "call_llm_perspective_digest", fake_llm)
    monkeypatch.setattr(sys, "argv", ["generate_perspective_digest.py", "--limit", "10", "--max-sec", "0"])

    gpd.main()

    assert len(calls) == 4
    rows = conn.execute("select perspective_digest from topic_insights").fetchall()
    assert all(r[0] not in (None, "{}") for r in rows)


def test_stops_early_when_max_sec_budget_exceeded(monkeypatch, capsys):
    conn = _setup_db(5)
    _patch_connect(monkeypatch, conn)

    calls = []

    def fake_llm(title, summary, perspectives, url=""):
        calls.append(title)
        return {"engineer": "e"}

    monkeypatch.setattr(gpd, "call_llm_perspective_digest", fake_llm)

    # 1回目の time.perf_counter() 呼び出しで t0=0.0、以降は常に100.0を返す疑似クロック
    # -> 最初のループ突入時点で経過時間100秒 >= max_sec(10) となり1件も処理されない
    fake_clock = iter([0.0])
    monkeypatch.setattr(gpd.time, "perf_counter", lambda: next(fake_clock, 100.0))

    monkeypatch.setattr(sys, "argv", ["generate_perspective_digest.py", "--limit", "10", "--max-sec", "10"])

    gpd.main()

    assert len(calls) == 0
    updated = conn.execute(
        "select count(*) from topic_insights where perspective_digest is not null"
    ).fetchone()[0]
    assert updated == 0
    assert "budget reached" in capsys.readouterr().out


def test_max_sec_default_falls_back_to_env_var(monkeypatch):
    conn = _setup_db(3)
    _patch_connect(monkeypatch, conn)

    monkeypatch.setattr(gpd, "call_llm_perspective_digest", lambda *a, **k: {"engineer": "e"})
    monkeypatch.setenv("PERSPECTIVE_DIGEST_MAX_SEC", "5")

    fake_clock = iter([0.0])
    monkeypatch.setattr(gpd.time, "perf_counter", lambda: next(fake_clock, 50.0))

    # --max-sec を明示指定しない -> env PERSPECTIVE_DIGEST_MAX_SEC=5 がデフォルトとして使われる
    monkeypatch.setattr(sys, "argv", ["generate_perspective_digest.py", "--limit", "10"])

    gpd.main()

    updated = conn.execute(
        "select count(*) from topic_insights where perspective_digest is not null"
    ).fetchone()[0]
    assert updated == 0


def test_dry_run_does_not_call_llm(monkeypatch):
    conn = _setup_db(2)
    _patch_connect(monkeypatch, conn)

    calls = []
    monkeypatch.setattr(gpd, "call_llm_perspective_digest", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(sys, "argv", ["generate_perspective_digest.py", "--limit", "10", "--dry-run"])

    gpd.main()

    assert calls == []
