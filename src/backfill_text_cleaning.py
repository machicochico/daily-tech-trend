from __future__ import annotations

import json

from db import connect
from text_clean import clean_for_html, clean_json_like

TEXT_COLUMNS = {
    "articles": ["url", "url_norm", "title", "title_ja", "source", "category", "content"],
    "topics": ["topic_key", "title", "title_ja", "category", "kind", "region"],
    "topic_insights": ["type", "summary", "impact_guess", "next_actions", "key_points", "evidence_urls", "tags", "perspectives"],
    "low_priority_articles": ["url", "title", "content", "source", "vendor", "category", "source_tier", "kind", "region", "reason"],
}
JSON_COLUMNS = {"key_points", "evidence_urls", "tags", "perspectives"}


def _table_columns(cur, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _clean_value(column: str, value):
    if value is None:
        return None
    if column in JSON_COLUMNS:
        try:
            parsed = json.loads(value)
            return json.dumps(clean_json_like(parsed), ensure_ascii=False)
        except Exception:
            return clean_for_html(value)
    return clean_for_html(value)


def main() -> None:
    conn = connect()
    cur = conn.cursor()
    total_updates = 0

    for table, columns in TEXT_COLUMNS.items():
        existing = _table_columns(cur, table)
        target_columns = [c for c in columns if c in existing]
        if not target_columns:
            continue

        select_cols = ", ".join(["rowid", *target_columns])
        cur.execute(f"SELECT {select_cols} FROM {table}")
        for row in cur.fetchall():
            rowid, *values = row
            cleaned = [_clean_value(col, val) for col, val in zip(target_columns, values)]
            if cleaned != values:
                set_clause = ", ".join(f"{col}=?" for col in target_columns)
                cur.execute(f"UPDATE {table} SET {set_clause} WHERE rowid=?", (*cleaned, rowid))
                total_updates += 1

    conn.commit()
    conn.close()
    print(f"[backfill_text_cleaning] updated_rows={total_updates}")


if __name__ == "__main__":
    main()
