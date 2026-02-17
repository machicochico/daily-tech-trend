# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
