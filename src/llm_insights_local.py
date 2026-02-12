import argparse
import re
import sys
import time

from llm_insights_api import (
    _extract_json_object,
    _get_lm_content,
    call_llm,
    call_llm_short_news,
    post_lmstudio,
)
from llm_insights_pipeline import (
    compute_src_hash,
    connect,
    pick_topic_inputs,
    postprocess_insight,
    upsert_insight,
)


def _looks_english(s: str) -> bool:
    letters = sum(c.isascii() and c.isalpha() for c in s)
    return letters >= 20


def _has_japanese(s: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龥]", s or ""))


def _now_sec():
    return time.perf_counter()


def _parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(description="Generate LLM insights for topics")
    parser.add_argument("limit", nargs="?", type=int, default=300, help="Maximum topics to process")
    parser.add_argument("--rescue", action="store_true", help="Reprocess rows even when source hash is unchanged")
    return parser.parse_args(argv)


def _row_get(row, key, default=""):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def main():
    t0 = _now_sec()
    args = _parse_args(sys.argv[1:])
    limit = args.limit
    rescue = args.rescue

    conn = connect()
    rows = pick_topic_inputs(conn, limit=limit, rescue=rescue)
    pending = 0

    for r in rows:
        topic_id = r["topic_id"]
        try:
            title = (r["topic_title"] or "").strip()
            url = (r["url"] or "").strip()
            body = (r["body"] or "").strip()
            src_hash = compute_src_hash(title, url, body)

            prev_hash = (r["prev_src_hash"] or "").strip()
            if (not rescue) and prev_hash and (prev_hash == src_hash):
                print(f"[SKIP] same src_hash topic_id={topic_id}")
                continue

            t1 = _now_sec()
            category = _row_get(r, "category", "other") or "other"
            kind = _row_get(r, "kind", "")
            raw = call_llm(title, category, url, body, kind=kind)
            ins = postprocess_insight(raw, r)
            print(f"[TIME] llm_one topic={topic_id} sec={_now_sec() - t1:.1f}")

            upsert_insight(conn, topic_id, ins, r["src_article_id"], src_hash)
            pending += 1
            if pending >= 50:
                conn.commit()
                pending = 0
            print(f"[OK] insight saved topic_id={topic_id} imp={ins['importance']} cat={r['category']}")
        except (RuntimeError, ValueError, TypeError) as e:
            print(
                "[WARN] insight skipped "
                f"topic_id={topic_id} cat={_row_get(r, 'category', '')} source={_row_get(r, 'source', '')} "
                f"url={_row_get(r, 'url', '')} err={e}"
            )
            continue

    if pending:
        conn.commit()

    print(f"[TIME] step=llm end sec={_now_sec() - t0:.1f}")


if __name__ == "__main__":
    main()
