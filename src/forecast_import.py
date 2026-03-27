# src/forecast_import.py
"""未来予測レポート(Markdown)をdata/forecasts/にインポートしDB登録する"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

from db import connect, init_db
from forecast_parser import parse_forecast_markdown


FORECASTS_DIR = Path("data/forecasts")


def import_report(src_path: str) -> str:
    """レポートMDをdata/forecasts/にコピーしDBにメタデータ登録する

    Returns:
        登録されたreport_date
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"レポートファイルが見つかりません: {src}")

    md_text = src.read_text(encoding="utf-8")
    report = parse_forecast_markdown(md_text)

    # 日付が取れなければファイル更新日から推定
    if report.report_date:
        report_date = report.report_date
    else:
        mtime = datetime.fromtimestamp(src.stat().st_mtime)
        report_date = mtime.strftime("%Y-%m-%d")

    # data/forecasts/ にコピー
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = FORECASTS_DIR / f"report_{report_date}.md"
    shutil.copy2(src, dest)

    # DB登録 (UPSERT)
    init_db()
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO forecast_reports (report_date, file_path, executive_summary, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
            file_path = excluded.file_path,
            executive_summary = excluded.executive_summary,
            created_at = excluded.created_at
    """, (
        report_date,
        str(dest),
        report.executive_summary[:2000] if report.executive_summary else "",
        datetime.utcnow().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()

    print(f"インポート完了: {report_date} → {dest}")
    return report_date


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python src/forecast_import.py <レポート.md>")
        sys.exit(1)
    import_report(sys.argv[1])
