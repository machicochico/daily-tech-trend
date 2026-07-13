"""フィード品質スコアの計算。

各フィード URL に対して 0-100 のスコアを計算する:
- 取得成功率（失敗回数が少ないほど高い）
- 最終成功の鮮度（最近成功しているほど高い）
- 一次情報比率（source_tier='primary' の記事比率）

render_main.py から呼び出され、ops ページに一覧表示される。
"""
from __future__ import annotations

from datetime import datetime, timezone


def _freshness_score(last_success_at: str | None) -> float:
    """最終成功時刻から鮮度スコア（0.0-1.0）を計算。
    24時間以内=1.0、7日超=0.0 の線形。"""
    if not last_success_at:
        return 0.0
    try:
        s = str(last_success_at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s[:25] if len(s) > 25 else s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    except (ValueError, TypeError):
        return 0.0
    if age_h <= 24:
        return 1.0
    if age_h >= 24 * 7:
        return 0.0
    return 1.0 - (age_h - 24) / (24 * 6)


def _failure_score(failure_count: int) -> float:
    """失敗回数からスコア（0.0-1.0）。0回=1.0、10回以上=0.0 の線形。"""
    fc = max(0, int(failure_count or 0))
    if fc == 0:
        return 1.0
    if fc >= 10:
        return 0.0
    return 1.0 - (fc / 10.0)


def compute_feed_quality(cur) -> list[dict]:
    """feed_health と articles から各フィードの品質スコアを計算し、score 降順で返す。

    戻り値の各要素: {
      "url": str, "source": str, "score": int (0-100),
      "failure_count": int, "last_success_at": str,
      "primary_ratio": float, "article_count": int
    }
    """
    # フィード健全性情報
    try:
        cur.execute(
            "SELECT feed_url, failure_count, last_success_at, last_failure_reason "
            "FROM feed_health"
        )
        health_rows = cur.fetchall()
    except Exception:
        return []

    # フィード URL ごとの記事統計（source 名からマッピングできないため、
    # 現状は source_tier のカテゴリ別比率を近似として取得する）
    try:
        cur.execute(
            """
            SELECT
              COALESCE(source, '') AS source,
              COUNT(*) AS total,
              SUM(CASE WHEN source_tier = 'primary' THEN 1 ELSE 0 END) AS primary_count
            FROM articles
            GROUP BY COALESCE(source, '')
            """
        )
        source_stats = {
            row[0]: {"total": int(row[1] or 0), "primary": int(row[2] or 0)}
            for row in cur.fetchall()
        }
    except Exception:
        source_stats = {}

    results = []
    for feed_url, failure_count, last_success_at, last_failure_reason in health_rows:
        # feed_url → source 名は正確には取れないため、ドメイン部分で近似マッチする
        # （feed_url は RSS URL 形式、source は表示名）
        from urllib.parse import urlsplit

        host = (urlsplit(feed_url or "").netloc or "").lower()
        # 該当しそうな source のうち、最大 total を採用
        matched_source = None
        matched_stats = None
        for src, stats in source_stats.items():
            if src and host and host.split(".")[0] in src.lower().replace(" ", ""):
                if matched_stats is None or stats["total"] > matched_stats["total"]:
                    matched_source = src
                    matched_stats = stats

        article_count = matched_stats["total"] if matched_stats else 0
        primary_count = matched_stats["primary"] if matched_stats else 0
        primary_ratio = (primary_count / article_count) if article_count else 0.0

        fresh = _freshness_score(last_success_at)
        failsafe = _failure_score(failure_count)
        # 重み: 失敗率 50%、鮮度 30%、一次情報比率 20%
        score = round((failsafe * 0.5 + fresh * 0.3 + primary_ratio * 0.2) * 100)

        results.append({
            "url": feed_url,
            "source": matched_source or host or "",
            "score": int(score),
            "failure_count": int(failure_count or 0),
            "last_success_at": (last_success_at or "")[:16],
            "last_failure_reason": last_failure_reason or "",
            "primary_ratio": round(primary_ratio * 100, 1),
            "article_count": article_count,
        })

    # スコア昇順（問題のあるフィードを先頭に）
    results.sort(key=lambda r: (r["score"], -r["failure_count"]))
    return results
