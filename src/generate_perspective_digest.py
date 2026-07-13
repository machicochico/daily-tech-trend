"""立場別200文字サマリー(perspective_digest)を手動生成するバックフィルスクリプト。

段階導入方針: 本番の夜間パイプライン(llm_insights_pipeline/llm_insights_local)には
自動組み込みしない。既存の perspective_digest が未生成(NULL または '{}')な
topic_insights 行を対象に、オプトインでこのスクリプトを実行して生成する。

使い方:
    python src/generate_perspective_digest.py --limit 20
    python src/generate_perspective_digest.py --limit 20 --dry-run
    python src/generate_perspective_digest.py --limit 30 --max-sec 120  # 無人実行時の時間予算ガード
"""
from __future__ import annotations

import argparse
import json
import os
import time

from db import connect
from llm_insights_api import call_llm_perspective_digest

DEFAULT_LIMIT = 20
MAX_LIMIT = 200  # 暴走防止（LLM呼び出しの上限）


def _fetch_targets(cur, limit: int):
    sql = """
    SELECT
      ti.topic_id,
      COALESCE(NULLIF(t.title_ja, ''), NULLIF(t.title, ''), '') AS title,
      COALESCE(ti.summary, '') AS summary,
      COALESCE(ti.perspectives, '{}') AS perspectives,
      COALESCE(ti.evidence_urls, '[]') AS evidence_urls
    FROM topic_insights ti
    JOIN topics t ON t.id = ti.topic_id
    WHERE ti.perspective_digest IS NULL OR ti.perspective_digest = '{}'
    ORDER BY ti.updated_at DESC
    LIMIT ?
    """
    cur.execute(sql, (limit,))
    return cur.fetchall()


def _parse_json_field(raw: str, default):
    try:
        return json.loads(raw)
    except Exception:
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate perspective_digest (200字前後の立場別サマリー) for topic_insights")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"処理件数の上限（デフォルト {DEFAULT_LIMIT}、最大 {MAX_LIMIT}）")
    parser.add_argument("--dry-run", action="store_true", help="LLM呼び出しをせず対象件数のみ表示する")
    parser.add_argument(
        "--max-sec",
        type=int,
        default=int(os.environ.get("PERSPECTIVE_DIGEST_MAX_SEC", "0") or "0"),
        help="処理時間の上限秒（デフォルト: env PERSPECTIVE_DIGEST_MAX_SEC または 0=無制限）。"
        "夜間バッチ等の無人実行から呼ぶ場合は暴走防止のため必ず指定すること。",
    )
    args = parser.parse_args()

    limit = max(1, min(int(args.limit or DEFAULT_LIMIT), MAX_LIMIT))
    max_sec = max(0, int(args.max_sec or 0))

    conn = connect()
    cur = conn.cursor()
    targets = _fetch_targets(cur, limit)

    if args.dry_run:
        print(f"[generate_perspective_digest] dry-run target_count={len(targets)}")
        conn.close()
        return

    t0 = time.perf_counter()
    done = 0
    for row in targets:
        if max_sec and (time.perf_counter() - t0) >= max_sec:
            print(f"[TIME] generate_perspective_digest budget reached sec={time.perf_counter() - t0:.1f} max_sec={max_sec}")
            break

        topic_id, title, summary, perspectives_raw, evidence_urls_raw = row
        perspectives = _parse_json_field(perspectives_raw, {})
        evidence_urls = _parse_json_field(evidence_urls_raw, [])
        url = evidence_urls[0] if evidence_urls and isinstance(evidence_urls[0], str) else ""

        try:
            digest = call_llm_perspective_digest(title, summary, perspectives, url=url)
        except Exception as e:
            print(f"[generate_perspective_digest] topic_id={topic_id} failed err={e}")
            continue

        cur.execute(
            "UPDATE topic_insights SET perspective_digest=? WHERE topic_id=?",
            (json.dumps(digest, ensure_ascii=False), topic_id),
        )
        conn.commit()
        done += 1
        print(f"[generate_perspective_digest] topic_id={topic_id} done")

    conn.close()
    print(f"[generate_perspective_digest] updated_rows={done} sec={time.perf_counter() - t0:.1f}")


if __name__ == "__main__":
    main()
