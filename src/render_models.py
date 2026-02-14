from __future__ import annotations

import json
from typing import Any

import yaml

from text_clean import clean_for_html, clean_json_like

NAME_MAP = {
    "system": "システム",
    "manufacturing": "製造",
    "blast_furnace": "高炉",
    "eaf": "電炉",
    "rolling": "圧延",
    "quality": "品質",
    "maintenance": "保全",
    "security": "セキュリティ",
    "standards": "標準化・規格",
    "ai": "AI",
    "dev": "開発",
    "other": "その他",
}


def safe_json_list(s: str | None) -> list[str]:
    if not s:
        return []
    try:
        v = clean_json_like(json.loads(s))
        if isinstance(v, list):
            return [clean_for_html(str(x)) for x in v if x is not None]
    except Exception:
        pass
    return []


def safe_json_obj(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        v = clean_json_like(json.loads(s))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def load_categories_from_yaml() -> list[dict[str, str]]:
    try:
        with open("src/sources.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cats = cfg.get("categories")
        if isinstance(cats, list):
            out = []
            for c in cats:
                if isinstance(c, dict) and "id" in c and "name" in c:
                    out.append({"id": str(c["id"]), "name": str(c["name"])})
            return out
    except Exception:
        return []
    return []


def build_categories_fallback(cur) -> list[dict[str, str]]:
    cur.execute("SELECT DISTINCT category FROM topics WHERE category IS NOT NULL AND category != ''")
    cats = [r[0] for r in cur.fetchall()]
    if not cats:
        cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
        cats = [r[0] for r in cur.fetchall()]
    if not cats:
        cats = ["standards", "other"]
    return [{"id": c, "name": NAME_MAP.get(c, c)} for c in cats]


def ensure_category_coverage(cur, categories: list[dict[str, str]]) -> list[dict[str, str]]:
    ids = {c["id"] for c in categories}
    cur.execute("SELECT DISTINCT category FROM topics WHERE category IS NOT NULL AND category != ''")
    db_cats = [r[0] for r in cur.fetchall()]
    for c in db_cats:
        if c not in ids:
            categories.append({"id": c, "name": NAME_MAP.get(c, c)})
            ids.add(c)
    if not categories:
        categories = [
            {"id": "standards", "name": NAME_MAP["standards"]},
            {"id": "other", "name": NAME_MAP["other"]},
        ]
    return categories
