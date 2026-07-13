# daily-tech-trend
システム開発者向けに技術トレンドを日次収集・整理・可視化するサイト

## 運用構成
- **発行元はローカル（PC2）**: タスクスケジューラ → `C:\work\run_daily.bat` が毎晩パイプラインを実行し、`src/git_auto_push.py` が `docs/` をコミット & プッシュする（GitHub Pages で公開）
- **GitHub Actions（`.github/workflows/ci.yml`）は検証専用**: push/PR 時に `feed_lint` と `pytest` を実行するのみで、リポジトリへの書き込みはしない
- **`data/state.sqlite` は git 管理外**（`.gitignore` の方針どおり）。DB のスナップショットが必要な場合はローカルでバックアップを取る


## LLM 自動起動（任意）
`src/llm_insights_api.py` は LMStudio API (`http://127.0.0.1:1234`) へ接続します。
実行時に API が未起動なら、環境変数で指定したコマンドを 1 回だけ実行して起動待ちできます。

- `LMSTUDIO_AUTOSTART_CMD`: 起動コマンド（例: `open -a "LM Studio"` や独自起動スクリプト）
- `LMSTUDIO_AUTOSTART_WAIT_SEC`: 起動待ち秒数（デフォルト `45`）

未指定の場合は、従来通りエラー終了します。

- `LMSTUDIO_MODEL`: 利用したいモデルID（デフォルト: `openai/gpt-oss-20b`）
- `LMSTUDIO_FALLBACK_MODEL`: `LMSTUDIO_MODEL` が未ロード時に優先する代替モデルID（任意）
- `LMSTUDIO_MODEL_LOAD_CMD`: モデル未ロード時に明示ロードを行うコマンド（例: `python scripts/load_model.py --model {model}`）
- `LMSTUDIO_MODEL_LOAD_WAIT_SEC`: 明示ロード後に `/v1/models` へ反映されるまでの待機秒数（デフォルト `30`）

`LMSTUDIO_MODEL` が LM Studio 側で未ロードの場合は、`LMSTUDIO_FALLBACK_MODEL`、それも無ければ `/v1/models` の先頭モデルに自動フォールバックします。


LM Studio が `Failed to load model` / `ErrorOutOfDeviceMemory` を返した場合は、まず `LMSTUDIO_MODEL_LOAD_CMD` で明示ロードを再試行し、失敗時はそのモデルを除外して別のロード済みモデルへ自動で再試行します。

## 立場別200文字サマリー仕様
ユーザが記事を行動に繋げやすくするため、各記事で「技術者・経営者・消費者」の3立場別に、考え方・推奨行動・注意点を含む要約（2〜3文、実測150〜200文字程度）を生成する。各要約末尾に参考情報（evidence_urls由来のドメイン）を明示し、未取得時は「（参考情報未取得）」のフラグを付ける。既存`perspectives`（50字程度の短評）は互換維持したまま変更せず、`topic_insights.perspective_digest`カラムに発展版として追加した。

**プロンプトに文字数の目標を書かないこと**: 当初「170〜230字程度」という文字数目標をプロンプトに含めていたところ、既定モデル`gpt-oss:20b`が文字を1つずつ数える`reasoning`ループに入り`max_tokens`を使い切って空応答（`finish_reason: length`）になる不具合が実機検証で見つかった。「2〜3文」という文数指定＋`reasoning_effort: "low"`指定に変更して解消した（詳細は`tasks/knowledge.md`参照）。

**現状（Phase 2 まで完了）**: データ層と `render_main.py` での表示（tech / news ページの「立場別くわしい解説」）は実装・検証済み。生成は毎晩の本番パイプラインには自動組み込みせず、手動実行のバックフィルスクリプトとして提供する（自動統合は Phase 3 で判断済み・配線はユーザー承認待ち。`tasks/todo.md` 参照）。

使い方:
```
python src/generate_perspective_digest.py --limit 20
python src/generate_perspective_digest.py --limit 20 --dry-run   # 対象件数のみ確認（LLM呼び出しなし）
python src/generate_perspective_digest.py --limit 30 --max-sec 120  # 時間予算つき（無人実行向け）
```
`topic_insights.perspective_digest` が未生成（NULLまたは`'{}'`）の行を対象に、`llm_insights_api.call_llm_perspective_digest` でLLM生成し、UPDATEする。`--limit` の上限は200件（暴走防止）。
