"""Slack / Discord webhook 通知モジュール。

パイプライン末尾から呼び出し、重要度が一定値以上のトピックを通知する。
環境変数で動作を切り替え:
- SLACK_WEBHOOK_URL: Slack の incoming webhook URL（未設定なら Slack 通知しない）
- DISCORD_WEBHOOK_URL: Discord の webhook URL（未設定なら Discord 通知しない）
- NOTIFY_MIN_IMPORTANCE: 通知対象の最小 importance（デフォルト 80）
- NOTIFY_MAX_ITEMS: 1回の通知で送る最大トピック数（デフォルト 5）

CLI:
    python src/notify.py               # importance>=80 のトピックを通知
    python src/notify.py --dry-run     # 送信せずに本文だけ表示
    python src/notify.py --min 60      # 閾値を 60 に下げる
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import urllib.error
import urllib.request

from db import connect
from site_config import SITE_URL as _SITE_URL


DEFAULT_MIN_IMPORTANCE = int(os.environ.get("NOTIFY_MIN_IMPORTANCE", "80"))
DEFAULT_MAX_ITEMS = int(os.environ.get("NOTIFY_MAX_ITEMS", "5"))
SITE_URL = _SITE_URL.rstrip("/")


def collect_notifiable_topics(cur, *, min_importance: int, limit: int) -> list[dict]:
    """notifiable なトピックを降順 importance で取得。

    当日作成＆ insight 付きのみを対象。24時間以内のトピックに絞る。
    """
    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(t.category, '') AS category,
          COALESCE(ti.importance, 0) AS importance,
          COALESCE(ti.summary, '') AS summary,
          COALESCE(ti.updated_at, t.created_at) AS updated_at
        FROM topics t
        JOIN topic_insights ti ON ti.topic_id = t.id
        WHERE COALESCE(ti.importance, 0) >= ?
          AND datetime(COALESCE(ti.updated_at, t.created_at)) >= datetime('now', '-24 hours')
        ORDER BY ti.importance DESC, ti.updated_at DESC
        LIMIT ?
        """,
        (int(min_importance), int(limit)),
    )
    items = []
    for tid, title, category, importance, summary, updated_at in cur.fetchall():
        items.append({
            "id": tid,
            "title": title,
            "category": category,
            "importance": int(importance or 0),
            "summary": summary,
            "updated_at": updated_at,
        })
    return items


def _format_slack_blocks(items: list[dict]) -> dict:
    """Slack Block Kit フォーマットのペイロードを組み立てる。"""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔥 本日の重要トピック {len(items)}件"},
        }
    ]
    for it in items:
        text = (
            f"*<{SITE_URL}|{it['title']}>*\n"
            f"_{it['category']} · 重要度 {it['importance']}_\n"
            f"{(it['summary'] or '')[:200]}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        blocks.append({"type": "divider"})

    # 末尾の divider を除去
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    return {
        "text": f"本日の重要トピック {len(items)}件",
        "blocks": blocks,
    }


def _format_discord_embeds(items: list[dict]) -> dict:
    """Discord webhook 用の embeds ペイロード。"""
    embeds = []
    for it in items:
        embeds.append({
            "title": it["title"][:250],
            "url": SITE_URL,
            "description": (it["summary"] or "")[:400],
            "color": 0xDC2626 if it["importance"] >= 90 else 0xD97706,
            "fields": [
                {"name": "カテゴリ", "value": it["category"] or "-", "inline": True},
                {"name": "重要度", "value": str(it["importance"]), "inline": True},
            ],
        })
    return {
        "content": f"**本日の重要トピック {len(items)}件**",
        # Discord は 1メッセージ 10 embeds まで
        "embeds": embeds[:10],
    }


def _post_webhook(url: str, payload: dict, *, timeout: int = 10) -> tuple[int, str]:
    """汎用 webhook POST。戻り値は (HTTPステータス, レスポンス冒頭)。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, (resp.read(200) or b"").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, f"error: {e}"


def notify(
    *,
    min_importance: int = DEFAULT_MIN_IMPORTANCE,
    max_items: int = DEFAULT_MAX_ITEMS,
    dry_run: bool = False,
) -> dict:
    """DB から対象トピックを取得し、設定されている webhook へ送信する。

    戻り値: {"count": N, "channels": {"slack": status, "discord": status}, "items": [...]}
    """
    conn = connect()
    items = collect_notifiable_topics(conn.cursor(), min_importance=min_importance, limit=max_items)
    conn.close()

    result: dict[str, Any] = {"count": len(items), "channels": {}, "items": items}
    if not items:
        result["channels"]["noop"] = "no notifiable topics"
        return result

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    if slack_url:
        payload = _format_slack_blocks(items)
        if dry_run:
            result["channels"]["slack"] = {"status": "dry_run", "payload": payload}
        else:
            status, body = _post_webhook(slack_url, payload)
            result["channels"]["slack"] = {"status": status, "body": body[:120]}

    if discord_url:
        payload = _format_discord_embeds(items)
        if dry_run:
            result["channels"]["discord"] = {"status": "dry_run", "payload": payload}
        else:
            status, body = _post_webhook(discord_url, payload)
            result["channels"]["discord"] = {"status": status, "body": body[:120]}

    if not slack_url and not discord_url:
        result["channels"]["noop"] = (
            "no SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL env set"
        )

    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--min", type=int, default=DEFAULT_MIN_IMPORTANCE, dest="min_importance")
    p.add_argument("--max", type=int, default=DEFAULT_MAX_ITEMS, dest="max_items")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    result = notify(
        min_importance=args.min_importance,
        max_items=args.max_items,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
