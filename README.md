# daily-tech-trend
システム開発者向けに技術トレンドを日次収集・整理・可視化するサイト


## LLM 自動起動（任意）
`src/llm_insights_api.py` は LMStudio API (`http://127.0.0.1:1234`) へ接続します。
実行時に API が未起動なら、環境変数で指定したコマンドを 1 回だけ実行して起動待ちできます。

- `LMSTUDIO_AUTOSTART_CMD`: 起動コマンド（例: `open -a "LM Studio"` や独自起動スクリプト）
- `LMSTUDIO_AUTOSTART_WAIT_SEC`: 起動待ち秒数（デフォルト `45`）

未指定の場合は、従来通りエラー終了します。

- `LMSTUDIO_MODEL`: 利用したいモデルID（デフォルト: `openai/gpt-oss-20b`）
- `LMSTUDIO_FALLBACK_MODEL`: `LMSTUDIO_MODEL` が未ロード時に優先する代替モデルID（任意）

`LMSTUDIO_MODEL` が LM Studio 側で未ロードの場合は、`LMSTUDIO_FALLBACK_MODEL`、それも無ければ `/v1/models` の先頭モデルに自動フォールバックします。
