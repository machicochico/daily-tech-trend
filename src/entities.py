"""エンティティ抽出＋企業/製品別ページ生成。

- ルールベースの辞書マッチ（既知のベンダー・製品）で article_entities を生成
- オプションで LLM による抽出（ENTITIES_USE_LLM=1）
- 各エンティティごとに docs/entity/<slug>/index.html を書き出し

設計方針:
- 辞書マッチだけでも運用できること（LLM 未起動でも動く）
- 辞書は YAML で外部化（src/entities.yaml）
- LLM 拡張はオプションで段階導入
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import yaml

from db import connect
from page_common import PAGE_BASE_CSS, PAGE_DARK_CSS


ENTITIES_YAML_PATH = Path(__file__).with_name("entities.yaml")


def _slugify(name: str) -> str:
    """エンティティ名から URL 用 slug を生成。"""
    s = name.lower().strip()
    # 非ASCIIは hex エンコードせず、英数字以外を - に置換
    s = re.sub(r"[^a-z0-9\-_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def load_entity_dictionary() -> list[dict]:
    """エンティティ辞書を YAML から読み込む。未存在時はデフォルトを返す。"""
    if ENTITIES_YAML_PATH.exists():
        with open(ENTITIES_YAML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        entries = data.get("entities", []) or []
        return [e for e in entries if isinstance(e, dict) and e.get("name")]
    # デフォルト辞書（小規模サンプル、要拡充）
    return [
        {"name": "Microsoft", "kind": "company", "aliases": ["Microsoft", "マイクロソフト"]},
        {"name": "Google", "kind": "company", "aliases": ["Google", "グーグル", "Alphabet"]},
        {"name": "Amazon", "kind": "company", "aliases": ["Amazon", "AWS", "アマゾン"]},
        {"name": "Apple", "kind": "company", "aliases": ["Apple", "アップル"]},
        {"name": "Meta", "kind": "company", "aliases": ["Meta", "Facebook", "メタ"]},
        {"name": "OpenAI", "kind": "company", "aliases": ["OpenAI", "ChatGPT"]},
        {"name": "NVIDIA", "kind": "company", "aliases": ["NVIDIA", "エヌビディア"]},
        {"name": "POSCO", "kind": "company", "aliases": ["POSCO", "ポスコ"]},
        {"name": "Nippon Steel", "kind": "company", "aliases": ["Nippon Steel", "日本製鉄", "新日鉄"]},
        {"name": "JFE", "kind": "company", "aliases": ["JFEスチール", "JFE Steel"]},
        {"name": "Claude", "kind": "product", "aliases": ["Claude", "クロード"]},
        {"name": "GPT", "kind": "product", "aliases": ["GPT-4", "GPT-5", "GPT-6"]},
        {"name": "Windows", "kind": "product", "aliases": ["Windows 10", "Windows 11", "Windows Server"]},
    ]


def _upsert_entity(cur, name: str, slug: str, kind: str, aliases: list[str]) -> int:
    """entities テーブルに UPSERT し、id を返す。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    aliases_json = "|".join(aliases)
    cur.execute(
        """
        INSERT INTO entities(name, slug, kind, aliases, created_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(slug) DO UPDATE SET
          name=excluded.name,
          kind=excluded.kind,
          aliases=excluded.aliases
        """,
        (name, slug, kind, aliases_json, now),
    )
    cur.execute("SELECT id FROM entities WHERE slug=?", (slug,))
    return int(cur.fetchone()[0])


def extract_entities_by_dict(conn=None, *, limit_articles: int = 5000) -> dict:
    """辞書マッチで article_entities を埋める。

    戻り値: {"entities": N, "links": M}
    """
    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()

    dictionary = load_entity_dictionary()
    # slug -> entity_id
    entity_ids: dict[str, int] = {}
    for e in dictionary:
        name = str(e["name"])
        slug = _slugify(name)
        kind = str(e.get("kind", "other"))
        aliases = list(e.get("aliases", []) or []) or [name]
        eid = _upsert_entity(cur, name, slug, kind, aliases)
        entity_ids[slug] = eid

    # エイリアス→entity_id のマップを構築。大文字小文字区別なし、長い順に評価
    # ASCII の alias は単語境界つきで照合する（"Meta" が "metal" に誤マッチするのを防ぐ）。
    # 日本語など非ASCIIを含む alias は単語境界が使えないため部分一致のまま。
    alias_map: list[tuple[str, re.Pattern, str, int]] = []  # (alias_lower, pattern, slug, entity_id)
    for e in dictionary:
        slug = _slugify(str(e["name"]))
        eid = entity_ids[slug]
        for a in (e.get("aliases") or [e["name"]]):
            alias = str(a)
            if alias.isascii():
                pattern = re.compile(rf"\b{re.escape(alias.lower())}\b")
            else:
                pattern = re.compile(re.escape(alias.lower()))
            alias_map.append((alias.lower(), pattern, slug, eid))
    # 長い別名から優先（例: "Windows Server" を "Windows" より先に）
    alias_map.sort(key=lambda x: -len(x[0]))

    # 直近の記事を対象
    cur.execute(
        """
        SELECT id, COALESCE(title_ja,'') || ' ' || COALESCE(title,'') || ' ' || COALESCE(content,'')
        FROM articles
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit_articles),),
    )
    links = 0
    for aid, blob in cur.fetchall():
        blob_lower = (blob or "").lower()
        if not blob_lower:
            continue
        matched_ids = set()
        for alias, pattern, slug, eid in alias_map:
            if alias and eid not in matched_ids and pattern.search(blob_lower):
                matched_ids.add(eid)
        for eid in matched_ids:
            cur.execute(
                """
                INSERT OR IGNORE INTO article_entities(article_id, entity_id, confidence)
                VALUES(?,?,?)
                """,
                (int(aid), int(eid), 1.0),
            )
            links += 1

    conn.commit()
    if owns_conn:
        conn.close()
    return {"entities": len(entity_ids), "links": links}


def render_entity_pages(out_dir: Path | str, *, conn=None, top_n: int = 30) -> int:
    """記事数上位 `top_n` のエンティティについて個別ページを書き出す。"""
    out_dir = Path(out_dir)
    entity_root = out_dir / "entity"
    entity_root.mkdir(parents=True, exist_ok=True)

    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()

    cur.execute(
        """
        SELECT e.id, e.name, e.slug, COALESCE(e.kind,''), COUNT(ae.article_id) AS cnt
        FROM entities e
        LEFT JOIN article_entities ae ON ae.entity_id = e.id
        GROUP BY e.id
        HAVING cnt > 0
        ORDER BY cnt DESC
        LIMIT ?
        """,
        (int(top_n),),
    )
    entities = cur.fetchall()

    # index 用データ
    index_entries = []

    generated = 0
    for eid, name, slug, kind, cnt in entities:
        cur.execute(
            """
            SELECT a.id,
                   COALESCE(a.title_ja, a.title) AS title,
                   COALESCE(a.source,'') AS source,
                   COALESCE(a.url,'') AS url,
                   COALESCE(a.published_at, a.fetched_at) AS dt,
                   COALESCE(a.category,'') AS category
            FROM article_entities ae
            JOIN articles a ON a.id = ae.article_id
            WHERE ae.entity_id = ?
            ORDER BY COALESCE(a.published_at, a.fetched_at) DESC
            LIMIT 50
            """,
            (int(eid),),
        )
        articles = cur.fetchall()
        if not articles:
            continue

        items_html = "\n".join(
            f'<li><a href="{escape(a[3])}" target="_blank" rel="noopener">{escape(a[1] or "")}</a>'
            f' <span class="meta">· {escape(a[2] or "-")} · {escape(a[5] or "-")} · {escape(str(a[4] or "")[:10])}</span></li>'
            for a in articles
        )

        html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>{escape(name)} 関連ニュース | Daily Tech Trend</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{PAGE_BASE_CSS}
.meta-info{{color:#6b7280;font-size:.9rem;margin-bottom:1rem}}
ul.entity-list{{list-style:none;padding:0}}
ul.entity-list li{{padding:.5rem 0;border-bottom:1px solid #e5e7eb;font-size:.92rem}}
ul.entity-list a{{color:#2563eb;text-decoration:none}}
ul.entity-list a:hover{{text-decoration:underline}}
.meta{{color:#6b7280;font-size:.8rem}}
{PAGE_DARK_CSS}
</style></head><body>
<nav><a href="../../">&larr; Top</a> / <a href="../">エンティティ一覧</a></nav>
<h1>{escape(name)} 関連ニュース</h1>
<p class="meta-info">種別: {escape(kind or "-")} · 関連記事数: <b>{cnt}</b></p>
<ul class="entity-list">{items_html}</ul>
</body></html>
"""
        page_dir = entity_root / slug
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        generated += 1
        index_entries.append({"name": name, "slug": slug, "kind": kind, "count": cnt})

    # index.html
    if index_entries:
        items = "\n".join(
            f'<li><a href="{escape(e["slug"])}/">{escape(e["name"])}</a>'
            f' <span class="kind">{escape(e["kind"] or "")}</span>'
            f' <span class="count">{e["count"]}件</span></li>'
            for e in index_entries
        )
        index_html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<title>エンティティ一覧 | Daily Tech Trend</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
{PAGE_BASE_CSS}
ul{{list-style:none;padding:0}}
li{{padding:.4rem 0;border-bottom:1px solid #e5e7eb}}
.kind{{color:#6b7280;font-size:.85rem;margin-left:.5rem}}
.count{{float:right;color:#2563eb;font-weight:600}}
{PAGE_DARK_CSS}
</style></head><body>
<nav><a href="../">&larr; Top</a></nav>
<h1>エンティティ一覧（記事数順 · {len(index_entries)}件）</h1>
<ul>{items}</ul>
</body></html>
"""
        (entity_root / "index.html").write_text(index_html, encoding="utf-8")

    if owns_conn:
        conn.close()

    print(f"  entity pages: {generated}件")
    return generated


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--extract", action="store_true", help="辞書マッチでエンティティ抽出のみ実行")
    p.add_argument("--render", action="store_true", help="エンティティ別ページ生成のみ実行")
    p.add_argument("--top-n", type=int, default=30)
    args = p.parse_args()

    if args.extract or (not args.extract and not args.render):
        stats = extract_entities_by_dict()
        print(f"[extract] entities={stats['entities']} links={stats['links']}")

    if args.render or (not args.extract and not args.render):
        render_entity_pages(Path("docs"), top_n=args.top_n)

    return 0


if __name__ == "__main__":
    sys.exit(main())
