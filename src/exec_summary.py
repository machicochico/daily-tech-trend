"""カテゴリ別エグゼクティブサマリー生成。

直近 7 日分の記事を対象に、各カテゴリで
「業界への影響 Top3」を LLM に抽出させ、docs/exec/<category>.html に書き出す。

- LLM 未起動などで失敗した場合は、記事タイトル一覧のみの簡易 HTML を出力する。
- 運用はローカル/手動実行を想定（forecast_generate.py と同じパターン）。

使い方:
    python src/exec_summary.py                # 全カテゴリ生成
    python src/exec_summary.py --category ai  # 単一カテゴリのみ
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from db import connect
from page_common import PAGE_BASE_CSS, PAGE_DARK_CSS

# LLM 呼び出しは失敗しても致命にしないため、import は遅延化しない（型を明示）。
try:
    from llm_insights_api import (
        LLM_LONG_TIMEOUT_SEC,
        _extract_json_object,
        _get_lm_content,
        post_ollama,
    )
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

CAT_LABELS = {
    "ai": "AI",
    "security": "セキュリティ",
    "manufacturing": "製造（鉄鋼）",
    "system": "システム",
    "policy": "政策・規制",
    "market": "市況",
    "news": "一般ニュース",
}

OUT_DIR = Path("docs/exec")


def _load_recent_articles(cur, category: str, days: int = 7, limit: int = 20) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        SELECT
          id,
          COALESCE(title_ja, title) AS title,
          COALESCE(substr(content, 1, 600), '') AS snippet,
          COALESCE(source, '') AS source,
          COALESCE(url, '') AS url,
          COALESCE(published_at, fetched_at) AS dt
        FROM articles
        WHERE category = ?
          AND COALESCE(published_at, fetched_at) >= ?
          AND COALESCE(title_ja, title) IS NOT NULL
          AND COALESCE(title_ja, title) != ''
        ORDER BY COALESCE(published_at, fetched_at) DESC
        LIMIT ?
        """,
        (category, cutoff, int(limit)),
    )
    rows = []
    for row in cur.fetchall():
        rows.append({
            "id": row[0],
            "title": row[1],
            "snippet": row[2],
            "source": row[3],
            "url": row[4],
            "dt": row[5],
        })
    return rows


def _call_llm_for_summary(category: str, articles: list[dict]) -> dict | None:
    """LLM にカテゴリ別の影響 Top3 を抽出させる。失敗時は None。"""
    if not LLM_AVAILABLE or not articles:
        return None

    label = CAT_LABELS.get(category, category)
    # 記事をプロンプト用に整形
    bullets = []
    for i, a in enumerate(articles, 1):
        bullets.append(f"{i}. {a['title']} ({a['source']}) — {a['snippet'][:200]}")
    news_block = "\n".join(bullets)

    system = (
        "あなたは日本企業の経営企画向けに、技術トレンドから"
        "事業影響を抽出するアナリストです。"
    )
    user = (
        f"以下は直近1週間の「{label}」カテゴリのニュースです。\n\n"
        f"{news_block}\n\n"
        "これらのニュースから、業界／企業への影響が大きい上位3点を抽出し、"
        "各点について (1) 何が起きているか (2) 事業への影響 (3) 経営層が取るべき行動 "
        "を簡潔に記述してください。\n"
        "出力は JSON のみ。以下のスキーマ:\n"
        '{"category":"カテゴリ名","items":['
        '{"title":"見出し","what":"何が起きているか",'
        '"impact":"事業への影響","action":"推奨行動"}]}'
    )

    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        # gpt-oss は reasoning がトークンを食い潰して content が空になりやすい
        # （finish_reason=length・content=0 を実測）。effort を下げ、余裕を持たせる
        "max_tokens": 1600,
        "reasoning_effort": "low",
    }

    # gpt-oss は reasoning 超過で content が空になることが確率的にあるため軽くリトライする
    for attempt in range(1, 3):
        try:
            r = post_ollama(payload, timeout=LLM_LONG_TIMEOUT_SEC)
            text = _get_lm_content(r)
            obj_str = _extract_json_object(text)
            if not obj_str:
                print(f"[WARN] exec_summary empty/unparsable response category={category} attempt={attempt}")
                continue
            parsed = json.loads(obj_str)
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                return parsed
            print(f"[WARN] exec_summary schema mismatch category={category} attempt={attempt}")
        except Exception as e:
            print(f"[WARN] exec_summary LLM failed category={category} attempt={attempt} err={e}")
    return None


def _render_html(category: str, label: str, summary: dict | None, articles: list[dict]) -> str:
    """エグゼクティブサマリー HTML を組み立てる。LLM 結果が無ければ簡易版を出力。"""
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    items_html = ""
    if summary and summary.get("items"):
        parts = []
        for idx, it in enumerate(summary["items"][:3], 1):
            parts.append(
                f'<section class="exec-item">'
                f'<h2>{idx}. {escape(str(it.get("title") or ""))}</h2>'
                f'<dl>'
                f'<dt>何が起きているか</dt><dd>{escape(str(it.get("what") or ""))}</dd>'
                f'<dt>事業への影響</dt><dd>{escape(str(it.get("impact") or ""))}</dd>'
                f'<dt>推奨行動</dt><dd>{escape(str(it.get("action") or ""))}</dd>'
                f'</dl></section>'
            )
        items_html = "\n".join(parts)
    else:
        items_html = (
            '<p class="exec-fallback">LLMによる分析が未実行のため、'
            '参考として直近記事一覧のみ表示しています。</p>'
        )

    article_list = "\n".join(
        f'<li><a href="{escape(a["url"])}" target="_blank" rel="noopener">'
        f'{escape(a["title"])}</a> <small>({escape(a["source"])}, {escape(a["dt"][:10])})</small></li>'
        for a in articles
    )

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>{escape(label)} エグゼクティブサマリー | Daily Tech Trend</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{PAGE_BASE_CSS}
body{{line-height:1.7}}
.exec-item{{border:1px solid #e5e7eb;border-radius:8px;padding:1rem 1.2rem;margin:1rem 0;background:#f9fafb}}
.exec-item h2{{font-size:1.05rem;color:#2563eb;margin:0 0 .5rem}}
dl dt{{font-weight:600;color:#6b7280;margin-top:.5rem;font-size:.9rem}}
dl dd{{margin:.2rem 0 .5rem 1rem}}
.exec-fallback{{color:#b45309;background:#fef3c7;padding:.7rem 1rem;border-radius:6px}}
.refs{{margin-top:2rem}}
.refs h3{{font-size:1rem;color:#6b7280}}
.refs li{{font-size:.9rem;margin:.2rem 0}}
.meta{{color:#6b7280;font-size:.85rem}}
{PAGE_DARK_CSS}
</style></head>
<body>
<nav><a href="../">&larr; Top</a></nav>
<h1>{escape(label)} エグゼクティブサマリー</h1>
<p class="meta">直近7日の記事 {len(articles)} 件を対象 · 生成: {generated_at}</p>
{items_html}
<section class="refs">
  <h3>参考にしたニュース</h3>
  <ul>{article_list}</ul>
</section>
</body></html>
"""


def _render_index(categories_with_output: list[tuple[str, str]]) -> str:
    """エグゼクティブサマリーのインデックスページ。"""
    items = "\n".join(
        f'<li><a href="{escape(cat_id)}.html">{escape(label)}</a></li>'
        for cat_id, label in categories_with_output
    )
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>エグゼクティブサマリー | Daily Tech Trend</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{PAGE_BASE_CSS}li{{margin:.4rem 0}}{PAGE_DARK_CSS}</style>
</head><body>
<nav><a href="../">&larr; Top</a></nav>
<h1>エグゼクティブサマリー</h1>
<p>カテゴリ別に直近1週間の業界影響 Top3 を抽出したレポートです。</p>
<ul>{items}</ul>
</body></html>
"""


def generate(categories: list[str], *, no_llm: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    cur = conn.cursor()

    generated: list[tuple[str, str]] = []
    for cat in categories:
        label = CAT_LABELS.get(cat, cat)
        articles = _load_recent_articles(cur, cat)
        if not articles:
            print(f"[skip] category={cat} has no recent articles")
            continue
        summary = None if no_llm else _call_llm_for_summary(cat, articles)
        html = _render_html(cat, label, summary, articles)
        out_path = OUT_DIR / f"{cat}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"[ok] {out_path} (llm={'yes' if summary else 'no'}, articles={len(articles)})")
        generated.append((cat, label))

    if generated:
        # index は「今回生成した分」ではなくディスク上の全カテゴリページから構築する
        # （--category 単体実行で index が1件だけに上書きされるのを防ぐ）
        existing = [
            (cat, CAT_LABELS.get(cat, cat))
            for cat in CAT_LABELS
            if (OUT_DIR / f"{cat}.html").exists()
        ]
        (OUT_DIR / "index.html").write_text(_render_index(existing), encoding="utf-8")

    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", help="対象カテゴリ ID（未指定なら全主要カテゴリ）")
    parser.add_argument("--no-llm", action="store_true", help="LLM呼び出しをスキップして簡易版のみ出力")
    args = parser.parse_args()

    if args.category:
        cats = [args.category]
    else:
        cats = list(CAT_LABELS.keys())

    generate(cats, no_llm=args.no_llm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
