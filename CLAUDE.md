# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 言語設定
- 常に日本語で会話する
- コメントも日本語で記述する
- エラーメッセージの説明も日本語で行う
- ドキュメントも日本語で生成する

---

# Workflow Orchestration

## 1. Plan Node (Default Behavior)

- 3ステップ以上、または設計判断を含む非自明なタスクは必ずPlanモードで開始する
- 問題が発生した場合は即停止し、再計画してから再開する
- 実装手順だけでなく、検証手順も必ず計画に含める
- 曖昧さを排除するため、着手前に詳細仕様を明文化する

---

## 2. Subagent Strategy

- メインコンテキストを整理するため、積極的にサブエージェントを活用する
- 調査・探索・並列分析はサブエージェントに委譲する
- 複雑な問題はサブエージェントに計算資源を集中させる
- 1つは集中実行専用サブエージェントとして使用する

---

## 3. Self-Improvement Loop

- ユーザーから修正を受けた場合は `tasks/lessons.md` に記録する
- 同じミスを防ぐための再発防止ルールを明文化する
- ミス率が下がるまで継続的に改善する
- 関連プロジェクト開始前に lessons を確認する

---

## 4. Verification Before Done

- 動作確認できるまで「完了」としない
- 必要に応じて main との差分を確認する
- 「スタッフエンジニアが承認できるか？」を基準に自己レビューする
- テスト実行・ログ確認・証跡提示で正しさを証明する

---

## 5. Demand Elegance (Balanced)

- 非自明な変更では「より簡潔で堅牢な方法はないか」を検討する
- 修正が単純な場合は過剰設計を避ける
- 実装前に自分の案に対して反証思考を行う
- 既知の範囲で最も合理的な解を選択する

---

## 6. Autonomous Bug Fixing

- バグ報告を受けたら即修正する
- ログ・エラー・失敗テストを自律的に特定する
- ユーザーに追加コンテキストを要求しない
- CI失敗は明示指示がなくても解消する

---

# Task Management

1. Plan First  
   - `tasks/todo.md` にチェック可能なタスクとして計画を書く  

2. Verify Plan  
   - 実装前に計画を自己レビューする  

3. Track Progress  
   - 作業と同時に進捗を更新する  

4. Explain Changes  
   - 各ステップで高レベル要約を残す  

5. Document Results  
   - `tasks/todo.md` にレビュー結果を追記する  

6. Capture Lessons  
   - 修正後に `tasks/lessons.md` を更新する  

---

# PRO Edition Operational Enhancements

## 7. Context Window Management

- 長時間タスクではコンテキスト肥大を防ぐため、定期的に要約を生成する
- 不要になった議論・検討ログは削除または圧縮する
- 仕様・前提条件・決定事項は常に明文化し、曖昧な記憶依存を避ける
- 大規模修正前には「現在の前提」を再整理してから着手する
- 会話の流れではなく、常に最新の仕様書を正とする

---

## 8. Long Task Decomposition Strategy

- 長時間タスクは必ずフェーズ分割する（設計 → 実装 → 検証）
- 各フェーズ終了時に成果物を確定させる
- 1フェーズは明確な完了条件（Definition of Done）を持つ
- 並列可能な作業はサブエージェントに分離する
- 途中状態を残さない（常にビルド可能状態を維持）

---

## 9. High-Capacity Utilization Rules

- PROの大規模コンテキストを「雑談拡張」に使わない
- 広いコンテキストは設計整合性確認・依存関係解析に活用する
- 既存コード全体を俯瞰してから設計判断を行う
- 部分最適ではなく全体整合性を優先する

---

## 10. Stability Over Speed

- 速度より再現性を優先する
- 一発成功より、検証可能な成功を重視する
- 変更は常にロールバック可能にする
- 大規模変更は段階的に導入する

---

# Core Principles

- Simplicity First  
  変更は最小限・最短経路で行う  

- Fix Root Cause  
  応急処置ではなく根本原因を修正する  

- Minimal Impact  
  必要な箇所のみ変更し、新規バグを持ち込まない  
  
---

## プロジェクト概要

製造業（鉄鋼）・IT技術系のRSSフィードを日次で収集し、重複排除・トピック統合・LLM分析を行い、GitHub Pages上に静的HTMLとして公開する技術トレンドサイト。言語は日本語中心。

## コマンド

### パイプライン実行（CI/ローカル共通の順序）
```bash
pip install -r requirements.txt
python src/feed_lint.py --config src/sources.yaml   # フィード定義の検証
python src/collect.py                                # RSS収集→articles テーブル
python src/normalize.py                              # URL正規化
python src/dedupe.py                                 # 重複記事除去
python src/normalize_categories.py                   # カテゴリ名の正規化
python src/thread.py                                 # 記事→トピック統合
python src/translate.py                              # 英語タイトル→日本語翻訳
python src/render.py                                 # HTML生成→docs/
```

### LLM分析（ローカルのみ・LM Studio必要）
```bash
python src/llm_insights_local.py [limit] [--rescue]  # トピックごとにLLM要約生成
python src/forecast_generate.py [--max-sec 600]       # ニュース記事から未来予測を自動生成
```

### テスト
```bash
python -m pytest tests/                # 全テスト
python -m pytest tests/test_dedupe.py  # 単一テスト
```

## アーキテクチャ

### データフロー
```
sources.yaml → collect.py → [articles] → normalize.py → dedupe.py
→ normalize_categories.py → thread.py → [topics/topic_articles]
→ translate.py → llm_insights_local.py → [topic_insights]
→ render.py → docs/*.html (GitHub Pages)
```

### データストア
- **SQLite** (`data/state.sqlite`): 全データ格納。主要テーブルは `articles`, `topics`, `topic_articles`, `topic_insights`
- スキーマ定義は `src/db.py` の `init_db()` にある。カラム追加は `ensure_column()` で後方互換的に行う

### 主要モジュール
- **collect.py**: RSSフィード巡回。`sources.yaml` のフィード定義を読み、記事をDBへ格納。本文が薄い場合はWebページからフルテキスト補完する
- **dedupe.py**: `SequenceMatcher` でタイトル類似度ベースの重複判定。カテゴリごとに閾値を調整
- **thread.py**: `rapidfuzz` でトピック統合。類似記事を1トピックにまとめる
- **llm_insights_api.py**: LM Studio API (`localhost:1234`) へのLLM呼び出しラッパー。自動起動・モデルフォールバック・リトライ処理を含む
- **llm_insights_pipeline.py**: LLM分析のDB操作（`pick_topic_inputs`, `upsert_insight`）
- **llm_insights_local.py**: LLMパイプラインのエントリポイント。トピックごとに要約・重要度・立場別分析を生成
- **render_main.py**: Jinja2テンプレート（インラインHTML）で全ページ生成する巨大モジュール。render.py はこの互換ラッパー
- **render_models.py / render_queries.py**: レンダリング用のデータモデルとDBクエリを分離

### 出力先 (docs/)
- `docs/index.html`: メインページ（技術トレンド）
- `docs/news/index.html`: ニュースページ
- `docs/opinion/index.html`: 意見・分析ページ
- `docs/ops/index.html`: 運用ページ
- `docs/assets/css/common.css`, `docs/assets/js/common.js`: 共通アセット

### フィード定義
`src/sources.yaml` にカテゴリとRSSソースを定義。カテゴリIDは英語（`system`, `manufacturing`, `ai`, `security` 等）。

### LM Studio環境変数
- `LMSTUDIO_MODEL`: 使用モデルID（デフォルト: `openai/gpt-oss-20b`）
- `LMSTUDIO_FALLBACK_MODEL`: 代替モデル
- `LMSTUDIO_AUTOSTART_CMD`: LM Studio自動起動コマンド
- `LMSTUDIO_AUTOSTART_WAIT_SEC`: 起動待ち秒数（デフォルト `45`）

## CI/CD
- GitHub Actions (`.github/workflows/daily.yml`): 毎日UTC 0:00にパイプライン実行→`docs/` と `data/state.sqlite` をコミット＆プッシュ
- Python 3.11、`src/` 内のスクリプトをワーキングディレクトリから直接実行

## 注意事項
- `src/` 内のモジュールは `src.` プレフィックスなしで相互importする（`from db import connect`）。実行時のカレントディレクトリは `src/` またはパスが通っている前提
- `render_main.py` は150KB超の巨大ファイル。HTMLテンプレートがインライン文字列として埋め込まれている
- `data/` と `logs/` は `.gitignore` 対象（`state.sqlite` のみCIでコミット）
- テストは `tests/` に `test_*.py` 形式で配置。外部API依存のテストはモック化されている
