"""Diff ビュー（昨日との差分）。

毎日の render 直前にトピックのスナップショットを topic_snapshots に保存し、
直近 2 日を比較して以下を分類した HTML を docs/diff/index.html に書き出す:
- new_today: 今日初登場のトピック
- trending: importance が昨日より +10 以上 上昇
- fading: importance が昨日より -10 以上 下降または消失
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path

from db import connect
from page_common import PAGE_BASE_CSS

# スナップショットの保持日数。差分表示は直近2日しか参照しないため、
# 余裕を持たせつつ無制限の蓄積（過去に150万行/480MBまで肥大）を防ぐ。
SNAPSHOT_RETENTION_DAYS = 14


def save_today_snapshot(conn=None) -> int:
    """現在のトピック状態を topic_snapshots に UPSERT する（report_date = UTC 今日）。

    戻り値は保存したトピック数。
    """
    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cur.execute(
        """
        SELECT t.id,
               COALESCE(ti.importance, 0),
               COALESCE(t.category, ''),
               COALESCE(t.title_ja, t.title, '')
        FROM topics t
        LEFT JOIN topic_insights ti ON ti.topic_id = t.id
        WHERE COALESCE(t.title_ja, t.title) IS NOT NULL
          AND COALESCE(t.title_ja, t.title) != ''
        """
    )
    rows = cur.fetchall()
    written = 0
    for tid, importance, category, title in rows:
        cur.execute(
            """
            INSERT INTO topic_snapshots(report_date, topic_id, importance, category, title)
            VALUES(?,?,?,?,?)
            ON CONFLICT(report_date, topic_id) DO UPDATE SET
              importance=excluded.importance,
              category=excluded.category,
              title=excluded.title
            """,
            (today, tid, int(importance or 0), category, title),
        )
        written += 1

    # 保持期間を過ぎたスナップショットをパージ（無制限蓄積の防止）
    cur.execute(
        "DELETE FROM topic_snapshots WHERE report_date < date(?, ?)",
        (today, f"-{SNAPSHOT_RETENTION_DAYS} days"),
    )

    conn.commit()
    if owns_conn:
        conn.close()
    return written


def compute_diff(conn=None, *, gap_threshold: int = 10) -> dict:
    """直近2日の topic_snapshots を比較して差分を返す。

    戻り値: {
      "today": "YYYY-MM-DD",
      "prev": "YYYY-MM-DD",
      "new_today": [{...}],
      "trending": [{...with delta}],
      "fading": [{...with delta}],
    }
    """
    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT report_date FROM topic_snapshots ORDER BY report_date DESC LIMIT 2")
    dates = [r[0] for r in cur.fetchall()]
    if len(dates) == 0:
        result = {"today": None, "prev": None, "new_today": [], "trending": [], "fading": []}
    elif len(dates) == 1:
        # 初回起動時は全件を new_today に
        cur.execute(
            "SELECT topic_id, importance, category, title FROM topic_snapshots WHERE report_date=?",
            (dates[0],),
        )
        new_today = [_row_to_dict(r) for r in cur.fetchall()]
        new_today.sort(key=lambda x: x["importance"], reverse=True)
        result = {
            "today": dates[0], "prev": None,
            "new_today": new_today[:30], "trending": [], "fading": [],
        }
    else:
        today, prev = dates[0], dates[1]
        cur.execute(
            "SELECT topic_id, importance, category, title FROM topic_snapshots WHERE report_date=?",
            (today,),
        )
        today_map = {r[0]: _row_to_dict(r) for r in cur.fetchall()}
        cur.execute(
            "SELECT topic_id, importance, category, title FROM topic_snapshots WHERE report_date=?",
            (prev,),
        )
        prev_map = {r[0]: _row_to_dict(r) for r in cur.fetchall()}

        new_today = []
        trending = []
        fading = []

        for tid, rec in today_map.items():
            prev_rec = prev_map.get(tid)
            if prev_rec is None:
                new_today.append(rec)
                continue
            delta = rec["importance"] - prev_rec["importance"]
            if delta >= gap_threshold:
                rec = dict(rec)
                rec["delta"] = delta
                rec["prev_importance"] = prev_rec["importance"]
                trending.append(rec)
            elif delta <= -gap_threshold:
                rec = dict(rec)
                rec["delta"] = delta
                rec["prev_importance"] = prev_rec["importance"]
                fading.append(rec)

        # 前日にあったが今日消えた（=失速）
        for tid, prev_rec in prev_map.items():
            if tid in today_map:
                continue
            rec = dict(prev_rec)
            rec["delta"] = -rec["importance"]
            rec["prev_importance"] = prev_rec["importance"]
            rec["vanished"] = True
            fading.append(rec)

        new_today.sort(key=lambda x: x["importance"], reverse=True)
        trending.sort(key=lambda x: x["delta"], reverse=True)
        fading.sort(key=lambda x: x["delta"])

        result = {
            "today": today, "prev": prev,
            "new_today": new_today[:30],
            "trending": trending[:20],
            "fading": fading[:20],
        }

    if owns_conn:
        conn.close()
    return result


def _row_to_dict(row) -> dict:
    return {
        "topic_id": int(row[0]),
        "importance": int(row[1] or 0),
        "category": row[2] or "",
        "title": row[3] or "",
    }


def render_diff_page(out_dir: Path | str, conn=None) -> None:
    """docs/diff/index.html を生成する。"""
    diff = compute_diff(conn)
    out_dir = Path(out_dir)
    diff_dir = out_dir / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)

    def _render_section(title: str, items: list[dict], *, show_delta: bool = False) -> str:
        if not items:
            return f'<section><h2>{escape(title)}</h2><p class="empty">対象なし</p></section>'
        rows = []
        for it in items:
            delta_html = ""
            if show_delta:
                d = it.get("delta", 0)
                sign = "▲" if d > 0 else "▼"
                color = "#16a34a" if d > 0 else "#dc2626"
                vanished = " (消失)" if it.get("vanished") else ""
                delta_html = f' <span style="color:{color};font-weight:700">{sign} {abs(d)}{vanished}</span>'
            rows.append(
                f'<tr>'
                f'<td><a href="../topic/{it["topic_id"]}/">{escape(it["title"])}</a></td>'
                f'<td class="cat">{escape(it["category"])}</td>'
                f'<td class="num">{it["importance"]}{delta_html}</td>'
                f'</tr>'
            )
        table = (
            '<table class="diff-table">'
            '<thead><tr><th>タイトル</th><th>カテゴリ</th><th>重要度</th></tr></thead>'
            '<tbody>' + "\n".join(rows) + "</tbody></table>"
        )
        return f'<section><h2>{escape(title)} <small>({len(items)}件)</small></h2>{table}</section>'

    new_section = _render_section("🆕 新規トピック（今日初登場）", diff["new_today"])
    trend_section = _render_section("📈 急上昇（重要度上昇）", diff["trending"], show_delta=True)
    fade_section = _render_section("📉 失速（重要度低下・消失）", diff["fading"], show_delta=True)

    today = diff.get("today") or "-"
    prev = diff.get("prev") or "（初回）"

    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>昨日との差分 | Daily Tech Trend</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{PAGE_BASE_CSS}
body{{max-width:960px}}
h2{{font-size:1.1rem;margin-top:1.8rem;color:#2563eb}}
h2 small{{color:#6b7280;font-weight:400;font-size:.85rem}}
.diff-table{{width:100%;border-collapse:collapse;margin:.5rem 0}}
.diff-table th,.diff-table td{{border-bottom:1px solid #e5e7eb;padding:.5rem .6rem;text-align:left;font-size:.9rem}}
.diff-table th{{background:#f9fafb;color:#6b7280}}
.diff-table td.cat{{color:#6b7280;font-size:.85rem}}
.diff-table td.num{{text-align:right;white-space:nowrap}}
.diff-table a{{color:#2563eb;text-decoration:none}}
.diff-table a:hover{{text-decoration:underline}}
.empty{{color:#9ca3af;font-style:italic}}
</style></head>
<body>
<nav><a href="../">&larr; Top</a></nav>
<h1>昨日との差分</h1>
<p class="meta">比較: <b>{escape(str(today))}</b> vs <b>{escape(str(prev))}</b></p>
{new_section}
{trend_section}
{fade_section}
</body></html>
"""
    (diff_dir / "index.html").write_text(html, encoding="utf-8")
    print(
        f"  diff page: {diff_dir / 'index.html'} "
        f"(new={len(diff['new_today'])} trend={len(diff['trending'])} fade={len(diff['fading'])})"
    )
