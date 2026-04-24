# 世界ニュース欠落対策（2026-04-24）

## 現状の問題
- `docs/news/index.html` の「🌍 世界ニュース」表示が **3件のみ**
- DB 実態: BBC World の global/news 記事 298件（直近14日）、insight 未生成 545件
- 今日の insight 生成数 48件（通常 100前後）

## 根本原因
1. `pick_topic_inputs` (llm_insights_pipeline.py:17) が `published_at DESC` 単純順
   → jp/news が上位を占め、global/news が後回しに
2. 既定 `--max-sec 300` で途中打ち切り → 未処理が累積
3. insight 不足を検知する仕組み無し

## 恒久対策

### A. `pick_topic_inputs` フェアネス改善 ✅
- region (jp/global/other) × kind (news/tech) のバケット単位で `ROW_NUMBER() OVER`
- 新しい順は維持しつつバケット間をラウンドロビンで優先度付け
- 既存テスト (test_llm_pick_topic_inputs.py) を壊さない設計（PRAGMA で region 列有無検査）

### B. `pipeline_report.py` に未生成バケット別メトリクス ✅
- `topics_without_insight_by_bucket` を出力 (region × kind)
- 閾値 100 超で WARN 表示

### C. テスト追加 ✅
- `tests/test_llm_pick_topic_inputs.py` にフェアネス検証テスト（4件 green）
- `tests/test_pipeline_report.py` 新規（2件 green）

## 現状復旧
1. A 適用後、`python src/llm_insights_local.py 400 --max-sec 1800` を実行（進行中）
2. `python src/render.py` で再生成（未着手）
3. `docs/news/index.html` の 🌍 カウントを確認（未着手）

## 検証
- `python -m pytest tests/` 全グリーン（pre-existing 12件の失敗は無関係と確認済み）
- 旧 insight の上書きは発生しない（ti IS NULL 条件は維持）
- render 後、global セクションに複数件表示

## 記録
- `tasks/lessons.md` に教訓追記 ✅
