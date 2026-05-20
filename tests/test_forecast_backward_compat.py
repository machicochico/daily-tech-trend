"""過去の本番レポート（data/forecasts/*.md）が新しい parser/loader で例外なく開けるか。

T11 検証手順の一部。HORIZONS 文字列リネームや見出し階層変更が過去データ互換を
壊していないことを保証する。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FORECASTS_DIR = ROOT / "data" / "forecasts"


def _recent_forecast_files(limit: int = 30):
    """直近 limit 件の本番レポート Markdown を更新日時降順で返す。"""
    if not FORECASTS_DIR.exists():
        return []
    files = sorted(FORECASTS_DIR.glob("report_*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _has_recent_files():
    return bool(_recent_forecast_files(1))


@pytest.mark.skipif(not _has_recent_files(),
                    reason="data/forecasts/*.md が存在しない環境ではスキップ")
def test_parse_forecast_markdown_handles_recent_reports():
    """直近30件の本番レポートが parse_forecast_markdown で例外なく開けること。"""
    from forecast_parser import parse_forecast_markdown
    failures = []
    for f in _recent_forecast_files(30):
        try:
            md = f.read_text(encoding="utf-8")
            parsed = parse_forecast_markdown(md)
            assert parsed is not None
        except Exception as e:
            failures.append((f.name, str(e)))
    assert not failures, f"パース失敗: {failures}"


@pytest.mark.skipif(not _has_recent_files(),
                    reason="data/forecasts/*.md が存在しない環境ではスキップ")
def test_load_existing_today_report_handles_recent_reports(tmp_path, monkeypatch):
    """直近の本番レポートを `_load_existing_today_report` 経由で読み込めること。

    HORIZONS 文字列を一切変えていないため、過去レポートとの horizon キー不整合は発生しないはず。
    """
    import forecast_generate as fg
    monkeypatch.setattr(fg, "FORECASTS_DIR", FORECASTS_DIR)
    failures = []
    for f in _recent_forecast_files(10):
        report_date = f.stem.replace("report_", "")
        try:
            result = fg._load_existing_today_report(report_date)
            assert isinstance(result, dict)
            assert "predictions" in result
        except Exception as e:
            failures.append((f.name, str(e)))
    assert not failures, f"_load_existing_today_report 失敗: {failures}"
