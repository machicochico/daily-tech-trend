# src/forecast_generate.py
"""直近ニュース記事をもとにLM Studioで未来予測レポートを自動生成する（ローカル専用）"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from db import connect, init_db
from llm_insights_api import (
    post_lmstudio,
    _get_lm_content,
    _extract_json_object,
    _repair_json_with_llm,
)

FORECASTS_DIR = Path("data/forecasts")

# --- カテゴリ日本語名 ---
CAT_LABELS = {
    "news": "一般ニュース", "market": "市況", "industry": "産業",
    "security": "セキュリティ", "ai": "AI", "policy": "政策・規制",
    "company": "企業動向", "dev": "開発", "manufacturing": "製造",
    "environment": "環境", "quality": "品質", "other": "その他",
}

HORIZONS = ["1週間後", "1〜6ヶ月後", "1年後"]

# ---------------------------------------------------------------------------
# 1. ニュースダイジェスト構築
# ---------------------------------------------------------------------------

def build_news_digest(cur, hours: int = 48, per_cat: int = 5) -> str:
    """直近の記事からカテゴリ別にサンプリングし、ダイジェストテキストを構築"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur.execute("""
        SELECT a.title, a.category,
               COALESCE(ti.summary, '') as summary,
               COALESCE(ti.importance, 0) as importance
        FROM articles a
        LEFT JOIN topic_articles ta ON ta.article_id = a.id AND ta.is_representative = 1
        LEFT JOIN topic_insights ti ON ti.topic_id = ta.topic_id
        WHERE datetime(a.fetched_at) >= datetime(?)
        ORDER BY ti.importance DESC NULLS LAST
    """, (cutoff,))

    by_cat: dict[str, list] = {}
    for title, cat, summary, importance in cur.fetchall():
        cat = cat or "other"
        if cat not in by_cat:
            by_cat[cat] = []
        if len(by_cat[cat]) < per_cat:
            by_cat[cat].append({
                "title": title or "",
                "summary": summary or "",
                "importance": int(importance or 0),
            })

    lines = []
    for cat, items in sorted(by_cat.items(), key=lambda x: -max((i["importance"] for i in x[1]), default=0)):
        label = CAT_LABELS.get(cat, cat)
        lines.append(f"【{label}】")
        for item in items:
            imp = f"[重要度{item['importance']}]" if item["importance"] else ""
            desc = item["summary"] if item["summary"] else item["title"]
            lines.append(f"- {imp} {item['title']} — {desc}")
        lines.append("")

    digest = "\n".join(lines)
    print(f"  ダイジェスト構築完了: {len(by_cat)}カテゴリ, {sum(len(v) for v in by_cat.values())}記事")
    return digest


# ---------------------------------------------------------------------------
# 2. LLM呼び出し
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
あなたはニュース分析に基づく未来予測の専門家です。
提示されたニュースダイジェストを分析し、指定された時間軸での予測をJSON配列で出力してください。
各予測項目には影響度（大/中/小）、確信度（高/中/低）、タイトル、予測内容、根拠を含めてください。
出力はJSONのみ。JSON以外の文字（挨拶、説明、コードブロック、注釈）を一切出さないでください。
必ず日本語で出力してください。"""

PREDICTION_USER_TMPL = """\
以下は直近48時間の主要ニュースダイジェストです。

{digest}

上記ニュースに基づき、**{horizon}**の未来予測を3〜5件、以下のJSON形式で出力してください:
[
  {{
    "impact": "大|中|小",
    "confidence": "高|中|低",
    "title": "予測タイトル（30字以内）",
    "prediction": "予測内容（具体的に、100字程度）",
    "evidence": "根拠となるニュースと論拠（100字程度）"
  }}
]"""

SUMMARY_SYSTEM = """\
あなたはニュース分析の専門家です。
未来予測の結果をもとに、今週の最重要ポイントを3つ選び、JSON配列で出力してください。
出力はJSONのみ。必ず日本語で出力してください。"""

SUMMARY_USER_TMPL = """\
以下は3つの時間軸の未来予測結果です。

{predictions_text}

上記から今週の最重要ポイントを3つ選び、以下のJSON形式で出力してください:
[
  {{
    "title": "ポイントのタイトル",
    "impact_description": "あなたへの影響（1〜2文）"
  }}
]"""


def _call_llm_json(system: str, user: str, max_tokens: int = 2000) -> list | dict:
    """LM Studioを呼び出してJSON結果を取得する"""
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    resp = post_lmstudio(payload, timeout=180, retries=2)
    raw_text = _get_lm_content(resp)

    # JSON抽出
    # 配列の場合は [ ] で囲まれている
    text = raw_text.strip().replace("```json", "").replace("```", "").strip()
    # 配列を試みる
    s = text.find("[")
    e = text.rfind("]")
    if s != -1 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except json.JSONDecodeError:
            pass
    # オブジェクトを試みる
    candidate = _extract_json_object(text)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # LLM修復
    try:
        return _repair_json_with_llm(raw_text)
    except Exception:
        print(f"  [WARN] JSON解析失敗、空配列を返します")
        return []


def generate_predictions(digest: str, horizon: str) -> list[dict]:
    """1つの時間軸の予測を生成"""
    user = PREDICTION_USER_TMPL.format(digest=digest, horizon=horizon)
    result = _call_llm_json(SYSTEM_PROMPT, user)
    if isinstance(result, dict):
        result = [result]
    print(f"  {horizon}: {len(result)}件の予測を生成")
    return result


def generate_executive_summary(all_predictions: dict[str, list]) -> list[dict]:
    """3時間軸の予測からエグゼクティブサマリーを生成"""
    parts = []
    for horizon, items in all_predictions.items():
        parts.append(f"## {horizon}")
        for item in items:
            parts.append(f"- {item.get('title', '')}: {item.get('prediction', '')}")
        parts.append("")
    predictions_text = "\n".join(parts)
    user = SUMMARY_USER_TMPL.format(predictions_text=predictions_text)
    result = _call_llm_json(SUMMARY_SYSTEM, user, max_tokens=1000)
    if isinstance(result, dict):
        result = [result]
    return result[:3]


# ---------------------------------------------------------------------------
# 3. Markdownレポート組み立て
# ---------------------------------------------------------------------------

def build_markdown_report(
    executive_summary: list[dict],
    predictions: dict[str, list[dict]],
    generated_at: str,
) -> str:
    """forecast_parser.pyが期待する形式でMarkdownレポートを組み立てる"""
    lines = []
    lines.append("# 多視点ニュース分析・未来予測レポート")
    lines.append("")
    lines.append(f"**生成日時:** {generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # エグゼクティブサマリー
    lines.append("# 今週の最重要ポイント")
    lines.append("")
    for i, item in enumerate(executive_summary, 1):
        title = item.get("title", f"ポイント{i}")
        desc = item.get("impact_description", "")
        lines.append(f"{i}. **{title}**  ")
        lines.append(f"   *あなたへの影響:* {desc}  ")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 未来予測
    lines.append("# 未来予測")
    lines.append("")
    lines.append("> 影響度・確信度が高い予測を優先して掲載しています。")
    lines.append("")

    for horizon in HORIZONS:
        items = predictions.get(horizon, [])
        lines.append(f"## {horizon}")
        lines.append("")
        # 影響度でソート（大>中>小）
        order = {"大": 0, "中": 1, "小": 2}
        items.sort(key=lambda x: (order.get(x.get("impact", "小"), 2),
                                   order.get(x.get("confidence", "低"), 2)))
        for idx, item in enumerate(items, 1):
            impact = item.get("impact", "中")
            confidence = item.get("confidence", "中")
            title = item.get("title", f"予測{idx}")
            prediction = item.get("prediction", "")
            evidence = item.get("evidence", "")

            lines.append(f"### {idx}. {title}")
            lines.append("")
            lines.append(f"**影響度: {impact} / 確信度: {confidence}**")
            lines.append("")
            lines.append(f"- **予測内容**：{prediction}")
            lines.append("")
            lines.append(f"- **根拠**：{evidence}")
            lines.append("")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 保存
# ---------------------------------------------------------------------------

def save_report(md_text: str, report_date: str, executive_summary_text: str) -> str:
    """Markdownをファイル保存しDBに登録する"""
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = FORECASTS_DIR / f"report_{report_date}.md"
    dest.write_text(md_text, encoding="utf-8")

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
        executive_summary_text[:2000],
        datetime.utcnow().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()
    print(f"  保存完了: {dest}")
    return str(dest)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ニュース記事から未来予測レポートを自動生成")
    parser.add_argument("--max-sec", type=int, default=600, help="最大実行時間(秒)")
    parser.add_argument("--hours", type=int, default=48, help="対象記事の期間(時間)")
    parser.add_argument("--per-cat", type=int, default=5, help="カテゴリ当たりの記事数")
    args = parser.parse_args()

    t0 = time.time()
    print("[forecast_generate] 開始")

    init_db()
    conn = connect()
    cur = conn.cursor()

    # 1. ニュースダイジェスト構築
    print("[1/4] ニュースダイジェスト構築...")
    digest = build_news_digest(cur, hours=args.hours, per_cat=args.per_cat)
    if not digest.strip():
        print("[ERROR] 対象記事が見つかりません")
        conn.close()
        sys.exit(1)

    # 2. 各時間軸の予測生成
    all_predictions: dict[str, list] = {}
    for i, horizon in enumerate(HORIZONS):
        if time.time() - t0 > args.max_sec:
            print(f"[WARN] タイムアウト({args.max_sec}秒)に達しました")
            break
        print(f"[2/4] {horizon}の予測を生成中... ({i+1}/{len(HORIZONS)})")
        all_predictions[horizon] = generate_predictions(digest, horizon)

    # 3. エグゼクティブサマリー生成
    print("[3/4] エグゼクティブサマリー生成中...")
    exec_summary = generate_executive_summary(all_predictions)
    print(f"  サマリー: {len(exec_summary)}件")

    # 4. レポート組み立て・保存
    print("[4/4] レポート組み立て・保存...")
    now = datetime.now(timezone(timedelta(hours=9)))
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    report_date = now.strftime("%Y-%m-%d")

    md_text = build_markdown_report(exec_summary, all_predictions, generated_at)

    # サマリーテキスト（DB用）
    summary_lines = []
    for item in exec_summary:
        summary_lines.append(f"- {item.get('title', '')}: {item.get('impact_description', '')}")
    summary_text = "\n".join(summary_lines)

    save_report(md_text, report_date, summary_text)

    conn.close()
    elapsed = time.time() - t0
    print(f"[forecast_generate] 完了 ({elapsed:.1f}秒)")


if __name__ == "__main__":
    main()
