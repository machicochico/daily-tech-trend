"""ベクトル類似度を用いた記事・トピック dedupe（オプション機能）。

環境変数 USE_VECTOR_DEDUPE=1 のとき有効。sentence-transformers が未インストールなら
自動でフォールバック（既存の文字列類似のみ使用）する。

使い方:
    # 単体実行（既存 dedupe の後に重複を再判定）
    USE_VECTOR_DEDUPE=1 python src/dedupe_vector.py
    python src/dedupe_vector.py --threshold 0.80

設計:
- 既存の dedupe.py は変更しない（互換維持）
- 埋め込みはタイトル単位。本文は重すぎるため使わない
- 類似度 >= threshold かつ同日・同カテゴリの記事ペアを merge 候補として出す
- モデルは paraphrase-multilingual-MiniLM-L12-v2（CPU でも数千件処理可）
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect

DEFAULT_MODEL = os.environ.get(
    "VECTOR_DEDUPE_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)
DEFAULT_THRESHOLD = float(os.environ.get("VECTOR_DEDUPE_THRESHOLD", "0.82"))


def _is_enabled() -> bool:
    return os.environ.get("USE_VECTOR_DEDUPE", "").strip() in ("1", "true", "True", "yes")


def _load_model(model_name: str = DEFAULT_MODEL):
    """sentence-transformers をオプショナルに読み込む。失敗時は None。"""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except Exception as e:
        print(f"[dedupe_vector] sentence-transformers 未利用: {type(e).__name__}: {e}")
        return None


def find_duplicate_candidates(
    *,
    days: int = 7,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL,
    conn=None,
) -> list[dict]:
    """直近 N 日の記事を対象に、ベクトル類似度で重複候補ペアを検出する。

    戻り値の各要素: {
      "a_id", "a_title", "b_id", "b_title", "score", "category"
    }
    a_id < b_id で重複除去済み。同一カテゴリ内でのみ比較。
    """
    if not _is_enabled():
        print("[dedupe_vector] USE_VECTOR_DEDUPE 未設定のため無効（既存 dedupe のみ）")
        return []

    model = _load_model(model_name)
    if model is None:
        return []

    owns_conn = False
    if conn is None:
        conn = connect()
        owns_conn = True
    cur = conn.cursor()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        SELECT id, COALESCE(title_ja, title) AS title, COALESCE(category, 'other')
        FROM articles
        WHERE COALESCE(title_ja, title) IS NOT NULL
          AND COALESCE(title_ja, title) != ''
          AND COALESCE(published_at, fetched_at) >= ?
        ORDER BY id
        """,
        (cutoff,),
    )
    rows = cur.fetchall()
    if owns_conn:
        conn.close()

    if not rows:
        return []

    # カテゴリ別にグルーピングして比較件数を抑える
    by_cat: dict[str, list[tuple[int, str]]] = {}
    for aid, title, cat in rows:
        by_cat.setdefault(cat, []).append((int(aid), title))

    candidates: list[dict] = []
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        titles = [t for _, t in items]
        ids = [i for i, _ in items]
        embeddings = model.encode(titles, show_progress_bar=False, normalize_embeddings=True)
        # cosine 類似度 (正規化済みなので内積 = cosine)
        import numpy as np  # sentence-transformers と一緒に入る

        mat = embeddings @ embeddings.T
        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                score = float(mat[i][j])
                if score >= threshold:
                    candidates.append({
                        "a_id": ids[i], "a_title": titles[i],
                        "b_id": ids[j], "b_title": titles[j],
                        "score": round(score, 3), "category": cat,
                    })

    candidates.sort(key=lambda x: -x["score"])
    return candidates


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--limit", type=int, default=50, help="表示する候補数の上限")
    args = p.parse_args()

    if not _is_enabled():
        # CLI 実行時は環境変数を一時的に有効化（明示操作前提）
        os.environ["USE_VECTOR_DEDUPE"] = "1"

    results = find_duplicate_candidates(
        days=args.days, threshold=args.threshold, model_name=args.model
    )
    print(f"候補 {len(results)} ペア (threshold={args.threshold}, days={args.days})")
    for c in results[: args.limit]:
        print(
            f"  [{c['category']}] {c['score']:.3f}  "
            f"#{c['a_id']} {c['a_title'][:60]}  <->  "
            f"#{c['b_id']} {c['b_title'][:60]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
