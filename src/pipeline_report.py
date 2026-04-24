"""パイプライン実行結果のサマリレポートを生成する。

各ステップのログ出力から統計情報を収集し、簡潔なサマリを標準出力に出力する。
CIの最終ステップから呼ぶことを想定。
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _parse_collect_health(log_dir: Path) -> dict:
    """logs/ 内の直近 collect_health ログからサマリ情報を抽出する。"""
    health_files = sorted(log_dir.glob("collect_health_*.jsonl"), reverse=True)
    if not health_files:
        return {}
    latest = health_files[0]
    feed_ok, feed_fail = 0, 0
    for line in latest.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            if entry.get("status") == "ok":
                feed_ok += 1
            else:
                feed_fail += 1
        except (json.JSONDecodeError, KeyError):
            pass
    return {"feeds_ok": feed_ok, "feeds_failed": feed_fail}


def _count_db_stats(db_path: Path) -> dict:
    """SQLite から主要テーブルの件数を取得する。"""
    import sqlite3

    stats = {}
    if not db_path.exists():
        return stats

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    for table in ("articles", "topics", "topic_articles", "topic_insights"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cur.fetchone()[0]
        except Exception:
            stats[table] = -1

    # 未翻訳記事数
    try:
        cur.execute(
            "SELECT COUNT(*) FROM articles "
            "WHERE kind IN ('news','tech') "
            "AND title IS NOT NULL AND title != '' "
            "AND (title_ja IS NULL OR title_ja = '')"
        )
        stats["untranslated"] = cur.fetchone()[0]
    except Exception:
        stats["untranslated"] = -1

    # insight未生成トピック数
    try:
        cur.execute(
            "SELECT COUNT(*) FROM topics t "
            "WHERE NOT EXISTS (SELECT 1 FROM topic_insights i WHERE i.topic_id = t.id)"
        )
        stats["topics_without_insight"] = cur.fetchone()[0]
    except Exception:
        stats["topics_without_insight"] = -1

    # region × kind バケット別の未生成件数（代表記事ベース）
    try:
        # articles に region があるかを検査
        cols = [r[1] for r in cur.execute("PRAGMA table_info(articles)").fetchall()]
        if "region" in cols:
            cur.execute(
                """
                SELECT
                  CASE
                    WHEN a.kind='news' AND COALESCE(a.region,'')='global' THEN 'global_news'
                    WHEN a.kind='news' AND COALESCE(a.region,'')='jp'     THEN 'jp_news'
                    WHEN a.kind='news'                                     THEN 'other_news'
                    WHEN a.kind='tech' AND COALESCE(a.region,'')='global' THEN 'global_tech'
                    WHEN a.kind='tech'                                     THEN 'jp_tech'
                    ELSE 'other'
                  END AS bucket,
                  COUNT(DISTINCT t.id)
                FROM topics t
                JOIN topic_articles ta ON ta.topic_id = t.id
                JOIN articles a ON a.id = ta.article_id
                LEFT JOIN topic_insights i ON i.topic_id = t.id
                WHERE i.topic_id IS NULL
                GROUP BY bucket
                """
            )
            stats["topics_without_insight_by_bucket"] = {
                row[0]: int(row[1]) for row in cur.fetchall()
            }
        else:
            stats["topics_without_insight_by_bucket"] = {}
    except Exception:
        stats["topics_without_insight_by_bucket"] = {}

    conn.close()
    return stats


# バケット別未生成件数の警告閾値（超過で WARN 表示）
INSIGHT_BACKLOG_WARN_THRESHOLD = 100


def record_category_trends(db_path: Path | None = None) -> int:
    """当日分のカテゴリ別集計を category_trends に UPSERT する。

    戻り値は書き込んだ行数（カテゴリ数）。
    """
    import sqlite3
    from datetime import datetime, timezone

    if db_path is None:
        db_path = Path("data/state.sqlite")
    if not db_path.exists():
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 当日受信の articles をカテゴリ別に集計
    cur.execute(
        """
        SELECT
          COALESCE(NULLIF(category,''), 'other') AS cat,
          COUNT(*) AS ac
        FROM articles
        WHERE date(COALESCE(published_at, fetched_at)) = date(?)
        GROUP BY cat
        """,
        (today,),
    )
    article_counts = {row[0]: int(row[1] or 0) for row in cur.fetchall()}

    # 当日作成された topics をカテゴリ別に集計
    cur.execute(
        """
        SELECT
          COALESCE(NULLIF(category,''), 'other') AS cat,
          COUNT(*) AS tc
        FROM topics
        WHERE date(created_at) = date(?)
        GROUP BY cat
        """,
        (today,),
    )
    topic_counts = {row[0]: int(row[1] or 0) for row in cur.fetchall()}

    categories = set(article_counts.keys()) | set(topic_counts.keys())
    written = 0
    for cat in categories:
        cur.execute(
            """
            INSERT INTO category_trends(report_date, category, articles_count, topics_count)
            VALUES(?,?,?,?)
            ON CONFLICT(report_date, category) DO UPDATE SET
              articles_count = excluded.articles_count,
              topics_count = excluded.topics_count
            """,
            (today, cat, article_counts.get(cat, 0), topic_counts.get(cat, 0)),
        )
        written += 1

    conn.commit()
    conn.close()
    return written


def main():
    log_dir = Path("logs")
    db_path = Path("data/state.sqlite")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "steps": {},
        "db_stats": _count_db_stats(db_path),
        "output_pages": {},
    }

    collect_stats = _parse_collect_health(log_dir)
    if collect_stats:
        report["steps"]["collect"] = collect_stats

    # カテゴリ別日次集計を category_trends に記録
    try:
        written = record_category_trends(db_path)
        report["steps"]["category_trends_written"] = written
    except Exception as e:
        report["steps"]["category_trends_error"] = str(e)

    # 出力ページの確認
    docs_dir = Path("docs")
    if docs_dir.exists():
        for html_file in docs_dir.rglob("index.html"):
            rel = str(html_file.relative_to(docs_dir))
            report["output_pages"][rel] = html_file.stat().st_size

    db = report["db_stats"]
    pages = report["output_pages"]

    print("=" * 60)
    print("  Pipeline Summary Report")
    print("=" * 60)
    print(f"  articles:     {db.get('articles', '?')}")
    print(f"  topics:       {db.get('topics', '?')}")
    print(f"  insights:     {db.get('topic_insights', '?')}")
    print(f"  untranslated: {db.get('untranslated', '?')}")
    print(f"  no insight:   {db.get('topics_without_insight', '?')}")

    buckets = db.get("topics_without_insight_by_bucket") or {}
    if buckets:
        print("  no insight by bucket:")
        for bkt in sorted(buckets.keys()):
            n = buckets[bkt]
            mark = "  WARN" if n >= INSIGHT_BACKLOG_WARN_THRESHOLD else ""
            print(f"    {bkt:12s} {n:5d}{mark}")
    print()

    if collect_stats:
        print(f"  collect: feeds_ok={collect_stats['feeds_ok']} feeds_failed={collect_stats['feeds_failed']}")
        print()

    print("  Output pages:")
    for page, size in sorted(pages.items()):
        status = "OK" if size > 1024 else "WARN (small)"
        print(f"    {page}: {size:,} bytes [{status}]")

    print("=" * 60)

    # JSON形式でもログ出力（CI解析用）
    log_dir.mkdir(exist_ok=True)
    report_path = log_dir / "pipeline_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Report saved to {report_path}")


if __name__ == "__main__":
    main()
