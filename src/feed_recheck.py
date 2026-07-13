"""停止（suspend）中フィードの生存再チェックツール。

feed_health で failure_count が閾値を超えたフィードを実際に取得し直し、
- 復活している → failure_count / suspend_until をリセット（--apply 時のみ）
- リダイレクトされている → 移転先 URL を報告（sources.yaml の更新候補）
- 死んでいる → HTTP ステータス / エラー種別を報告

使い方:
    python src/feed_recheck.py            # レポートのみ（dry-run）
    python src/feed_recheck.py --apply    # 復活フィードの health をリセット
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests

from db import connect

if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "DailyTechTrend/1.0 (+feed health recheck)"}
TIMEOUT = 15


def check_feed(url: str) -> dict:
    """フィードを取得して状態を分類する。"""
    result = {"url": url, "status": "dead", "detail": "", "final_url": url}
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        result["final_url"] = r.url
        result["detail"] = f"http={r.status_code}"
        if r.status_code != 200:
            return result
        parsed = feedparser.parse(r.content)
        entries = len(parsed.entries or [])
        if entries > 0:
            result["status"] = "alive"
            result["detail"] = f"entries={entries}"
            if r.url.rstrip("/") != url.rstrip("/"):
                result["status"] = "moved"
        else:
            result["detail"] = f"http=200 entries=0 bozo={int(bool(parsed.bozo))}"
    except requests.RequestException as e:
        result["detail"] = type(e).__name__
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="復活フィードの feed_health をリセットする")
    p.add_argument("--min-failures", type=int, default=5, help="再チェック対象の最小 failure_count")
    args = p.parse_args()

    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT feed_url, failure_count, last_failure_reason FROM feed_health "
        "WHERE failure_count >= ? ORDER BY failure_count DESC",
        (args.min_failures,),
    )
    targets = cur.fetchall()
    print(f"[feed_recheck] 対象 {len(targets)} 件 (failure_count >= {args.min_failures})")

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda t: check_feed(t[0]), targets))

    alive = [r for r in results if r["status"] == "alive"]
    moved = [r for r in results if r["status"] == "moved"]
    dead = [r for r in results if r["status"] == "dead"]

    print(f"\n=== 復活 ({len(alive)}件) ===")
    for r in alive:
        print(f"  OK  {r['url']} ({r['detail']})")
    print(f"\n=== 移転 ({len(moved)}件) — sources.yaml の更新候補 ===")
    for r in moved:
        print(f"  MOVED {r['url']}\n     -> {r['final_url']} ({r['detail']})")
    print(f"\n=== 死亡 ({len(dead)}件) — sources.yaml から削除または URL 差し替えを検討 ===")
    for r in dead:
        print(f"  NG  {r['url']} ({r['detail']})")

    if args.apply and (alive or moved):
        for r in alive + moved:
            cur.execute(
                "UPDATE feed_health SET failure_count=0, suspend_until='', last_failure_reason='' "
                "WHERE feed_url=?",
                (r["url"],),
            )
        conn.commit()
        print(f"\n[feed_recheck] {len(alive) + len(moved)} 件の health をリセットしました")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
