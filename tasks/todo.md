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

---

# 未来予測パイプライン全面オーバーホール（2026-05-20）

## 背景
data/forecasts/report_*.md の品質に複数の構造的欠陥を観測:
- タイトル空欄（5/19で4件、5/20で1件）
- forecast_verifications 67件中 verdict_json 空配列40件（accuracy_score None率97%）
- 「予測」が既報の言い換えに退化／horizon跨ぎ重複／3視点見出し階層崩壊／数値捏造

## 実装した対策（Plan: ~/.claude/plans/lexical-percolating-puddle.md）

### Phase 1: 即効修正 ✅
- T1: `_safe_translate` ラッパー追加、`build_markdown_report` で title 空時に prediction 先頭40字フォールバック、空ならアイテムスキップ
- T2: PERSPECTIVES_USER_TMPL を ### 強制、後処理で `^## ` を `### ` に降格
- T3: `_extract_body_head` 追加で title 空アイテムを LLM に渡す際 body 先頭を代替ラベル化、`_item_key` で carry-over も同様

### Phase 2: 予測品質強化 ✅
- T4: SYSTEM_PROMPT 全面書き換え（未来時制必須／[推定]ラベル必須／impact閾値／confidence閾値）、subjects/numeric_claims フィールド追加
- T5: previous_context に主体+prediction先頭、`_dedupe_across_horizons` (rapidfuzz token_set_ratio≥85) 後処理、requirements.txt に rapidfuzz 追記
- T6: HORIZON_CONFIG["1週間後"].focus 強化、`_SHORT_TERM_LEAK_RE` で「2027年/中期的/長期的/数年」混入を除去

### Phase 3: 構造改善 ✅
- T7: `_aggregate_topic_perspectives` で topic_insights.perspectives (engineer/management/consumer JSON) を集約し、generate_perspectives の主要素材として注入。LLM の役割を「自由推論」から「集約と構造化」に格下げ
- T9: `_call_verify_llm` をリトライ化 (max_retries=2)、JSON-mode `response_format` 試行、解析失敗時は None 返却で空配列上書きを停止、main で既存 verdict 保持

### Phase 4: 信頼性可視化 ✅
- T10: `_validate_numeric_claims` で digest 裏付けのない数値を `unverified_numerics` メタデータに記録、build_markdown_report に ⚠ バッジ＋脚注（本文改変なし）
- T11: 既存 accuracy UI (render_main.py:3044-3049) はコード変更なし。verify 修正で自動的に活性化

### 追加: 破損データ自動回復 ✅
- `_find_verification_targets` を拡張: 過去の verdict_json="[]" + accuracy=None レコードを再検証対象に含め、DELETE して再 INSERT

## 検証
- `tests/test_forecast_generate.py` 38→52テスト（新規14件追加）✅
- `tests/test_forecast_verify.py` 12→18テスト（新規6件追加）✅
- `tests/test_forecast_backward_compat.py` 新設 2テスト（過去30レポートの parse 互換性）✅
- 既存全テスト regression なし（pre-existing 12件の失敗は無関係）

## 記録
- `tasks/lessons.md` に5教訓追記 ✅

## 追補（同日）: verify 実行が極端に遅い問題の修正

### 観測（E2E 実行ログ）
- `forecast_verify.py --limit 1` で 1 件処理に **1237秒**
- ログに `bge-m3:latest failed / nomic-embed-text:latest failed` という想定外の警告
- JSON 解析が3回連続で失敗

### 原因
1. `llm_insights_api._pick_model_candidates` (llm_insights_api.py:71) が Ollama にある
   全モデル ID を区別なくチャット候補に追加し、埋め込み専用モデル (`bge-m3`,
   `nomic-embed-text`) もチャット完了エンドポイントに POST されて 400 で失敗
2. `_call_verify_llm` が試行的に付けていた `response_format={"type":"json_object"}` が
   gpt-oss:20b の応答品質を逆に悪化させていた
3. 解析失敗時に raw 応答の中身が見えず根本原因がわからなかった

### 修正
- **F1**: `_call_verify_llm` から JSON-mode (`response_format`) 試行を完全除去
- **F2**: `_is_embedding_model` 追加 + `_pick_model_candidates` の自動候補から埋め込み除外。
  ユーザー明示指定 (`OLLAMA_MODEL` / `OLLAMA_FALLBACK_MODEL`) は尊重（pinned model は通す）
- **F3**: JSON 解析失敗時に raw 応答の先頭200字を WARN ログに出す

### 効果
- `forecast_verify.py --limit 1` の実行時間: **1237秒 → 8.9秒** (約138倍高速化)
- 埋め込みモデルへのフォールバック試行が消滅
- JSON 解析成功

### 追加テスト
- `tests/test_llm_embedding_filter.py` 新設 8件 ✅
- 全テスト 183件 pass (pre-existing 失敗を除く)

---

# Phase 5 品質チューニング（2026-05-27）

## 背景
オーバーホール後1週間の生成レポートを目視レビューしたところ、新たに見えた品質問題:
- 5/25, 5/27 で **3視点分析が予測と無関係な「発砲事件」「軍事輸送」を分析** している
- 5/27 1週間後 horizon の**根拠 evidence が4件すべて空欄**
- タイトルが途中切れ（「日本のO」「電気SUVを発売し」）・冗長（title=prediction の丸写し）
- `[推定]` ラベルゼロ、⚠ バッジ 12件と過剰警告（5/25）

## 修正内容

### P1: 3視点分析のカテゴリフィルタ ✅
- `_aggregate_topic_perspectives` の SQL に `a.category IN (_TECH_CATEGORIES)` を追加
- allowlist は IT/製造業/テクノロジー系16カテゴリ（ai, dev, system, manufacturing, security, security_ot, policy, market, environment 等）
- 事件・テロ・スポーツ系トピックが3視点分析を乗っ取る問題を根絶
- prefix に category 名を含めて、LLM に「どのカテゴリの立場別コメントか」を可視化

### P2: 根拠空欄アイテムの除去 ✅
- `build_markdown_report` で evidence が空のアイテムを除外
- SYSTEM_PROMPT に「evidence は実質的に必須、元タイトル丸写し禁止、先行事例・市場動向・統計を引用」を強化

### P3: タイトル冗長/切れ防止 ✅
- `_smart_truncate_for_title`: 句読点（。.!?）優先で切り、なければ 70% 以降の読点（、,）で切る、それもなければ … 付与
- `_is_title_redundant`: title が prediction の prefix にある場合の冗長検知
- build_markdown_report で title が空・50字超・冗長のいずれかなら整形

### P4: ⚠ バッジニュートラル化 ✅
- `⚠[出典未確認数値あり]` → `📊 [推定値あり]`（読者を不安にさせない語感）
- 脚注 `⚠ 出典未確認の数値:` → `📊 推定値（ニュース原文での明示なし）:`
- `_validate_numeric_claims` でパーセンテージ (`\d+%`) を検証対象外に。「200社」「90ドル」「1000万」など根拠が問われるべきカウント・金額のみ対象

## 検証
- `tests/test_forecast_generate.py` に新規 17件追加（smart truncate 5, redundant 4, evidence filter 1, badge 1, category filter 1, percentage 1 + 既存修正4）
- 既存テスト regression なし: forecast 系 94件全 pass
- 全体 pre-existing 失敗除く: 全 pass
