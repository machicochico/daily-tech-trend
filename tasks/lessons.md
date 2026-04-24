# Lessons Learned

<!-- ミス・修正から得た教訓を記録するファイル -->

## 2026-04-18 大規模改修から得た教訓

### 互換ラッパーの削除判断は慎重に
- `src/render.py` は単なる再エクスポートに見えるが、`.github/workflows/daily.yml` と
  `tests/test_refactor_compat.py` が公開API として依存していた。
- 削除前に必ず grep と CI 設定を両方チェックする。
- **ルール**: 「単なる互換ラッパー」と見えても、呼び出し元が以下3点にあるか確認する
  1. テストファイル（名前に compat/wrapper/api など）
  2. CI ワークフロー（`.github/workflows/*.yml`）
  3. CLAUDE.md や README のコマンド例

### SQLite FTS5 の初期バックフィルは `rebuild` を使う
- `content='articles'` で外部コンテンツ同期モードの FTS5 仮想テーブルに対し、
  `INSERT ... SELECT` で初期化しようとしたが検索が空を返した。
- 正しくは `INSERT INTO articles_fts(articles_fts) VALUES('rebuild')` コマンドを使う。
- **ルール**: FTS5 を content='<table>' モードで作ったら、初期データは必ず rebuild で投入する。

### FTS5 の unicode61 トークナイザは日本語の分割が弱い
- 「セキュリティ」で検索するとヒットするが、分かち書きされないため複合キーワードに弱い。
- 検索UIは title/title_ja/snippet の JS 側 AND 絞込で代替し、FTS5 は将来の高度検索に温存。

### render_main.py 全面分割は範囲外
- 5091行の HTML テンプレート文字列を含む巨大モジュールを一気に分割するのは危険。
- 新規コード（RSS/検索）を別モジュールに切り出すことで分割パターンを確立し、
  既存コードの分割は「変更したい機能に触れるついで」に少しずつ行う方が現実的。

### pre-existing テスト失敗を自分の変更と混同しない
- 作業中に `test_opinion_page.py`・`test_docs_asset_paths.py` が落ちたが、
  `git stash` で base を検証したところ本作業前から failing だった。
- **ルール**: 改修着手前にまず `pytest` を1回走らせ、ベースラインの green/red を記録する。

### Windows での日本語ファイル読み込みは `PYTHONUTF8=1` が必須
- pytest 実行時に cp932 エンコードで UnicodeDecodeError / 表示崩れが発生。
- ローカルでは環境変数 `PYTHONUTF8=1` を付けるか `sys.setdefaultencoding` 相当で回避する。

## 2026-04-24 世界ニュース欠落事案から得た教訓

### LLM 入力ピックは region×kind でバランスする
- `pick_topic_inputs` が `published_at DESC` 単純順だったため、日本の最新 news が
  大量にあると global/news が後回しになり、1日予算内で処理されずに滞留した。
- 結果、`importance > 0` でフィルタする render 側で世界ニュースが3件のみ表示に。
- **ルール**: トピック優先度は「新しさ」単独ではなく「バケット（region×kind）横断の
  ラウンドロビン」で決める。バケットは `ROW_NUMBER() OVER (PARTITION BY bucket)` で
  各バケット最新→2番目→…の順に並べ、ORDER BY rn ASC で横断する。

### LLM 未処理の蓄積を可視化する
- `pipeline_report.py` は未生成トピック総数しか出していなかったため、
  「global だけが滞留している」構造的偏りに気付けなかった。
- **ルール**: バケット別メトリクスを毎日出力する。閾値超過で WARN を出す。
  サイレントな劣化（特定バケットだけ生成されない）を検知する。

### 互換のためクエリはスキーマ差異を許容する
- テスト用 in-memory DB は `articles.region` カラムが無い簡易スキーマのため、
  新クエリで `a.region` を直接参照するとテストが落ちた。
- **ルール**: スキーマ依存のクエリは `PRAGMA table_info()` でカラム存在確認し、
  式を動的に差し替える。これにより古い DB・簡易テスト DB との互換を維持できる。
