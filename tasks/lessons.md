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

## 2026-05-20 未来予測パイプライン全面オーバーホールから得た教訓

### LLM 翻訳系は空応答を必ず防御せよ
- `_translate_to_ja` (forecast_generate.py) が稀に空文字を返し、
  `_localize_prediction_item` がそれで title を上書きすることで
  本番レポートに「### 1. （タイトル無し）」が複数件出ていた。
- **ルール**: LLM翻訳・正規化を文字列フィールドに適用する全箇所で
  `result = llm_call(x); field = result if result.strip() else x` を徹底する。
  これを横断適用するため `_safe_translate` のような薄いラッパー1関数を作って
  そこを単一の通り道にする方が、後の改修コストが低い。

### パイプライン下流モジュールは上流の出力欠陥を「検知」する責務を持つ
- forecast_verify が title 空のアイテムを LLM に渡す際 `- : 本文...` という
  入力を作り、LLM が解析放棄して verdict_json が空配列 `[]` で保存され、
  以降のレポート的中率がほぼ全件 None になっていた（67件中 40件が破損）。
- silent に空配列で上書きする設計は障害を見えなくし、データ的中率の劣化を
  気付かないうちに広げる。
- **ルール**: 下流モジュールでは「上流の出力欠陥」を `None` などで明示的に
  区別して伝搬し、既存データを空で上書きしない。リトライ失敗時は **既存判定を
  保持** する保守的選択をデフォルトとする。

### 文字列ベースの enum は最初から内部キー+表示名分離で設計する
- `HORIZONS = ["1週間後", "1〜6ヶ月後", "1年後"]` のキー文字列が
  forecast_generate / forecast_verify / DB の horizon カラム / parser まで
  横断して使われており、リネームのコストが膨大（互換マップ運用）。
- 表示名と内部キーは設計時に分離するか、最低でも単一の場所に enum 定義を
  集約しておくべきだった。
- **ルール**: 「ユーザーに見せる表示文字列」を内部識別子として共用しない。
  enum 風の文字列を複数モジュールが参照する場合、定義は1モジュールに
  集中させ、表示用ラベルマップを別に持つ。

### 「1呼び出しで複数の独立出力を要求する」設計は失敗時の全滅リスクを必ず見積もる
- 3 horizon を1回の LLM 呼び出しで生成する設計は理論上効率的だが、
  1回の解析失敗で 3 horizon 全滅、品質安定性も下がる。
- 直列+後処理マージ（rapidfuzz による重複除去）の方が、
  失敗局所化・部分成功の積み上げで結果的に安定する。
- **ルール**: 「LLM 呼び出しの粒度を粗くしてバッチ化する」最適化は、
  失敗時の被害範囲と品質安定性を必ず A/B 比較してから採用する。

### 破損データの自動回復は明示的に実装する
- forecast_verifications の verdict_json="[]" + accuracy_score=None という
  破損レコードは「ラウンド1済」とみなされ、修正後も自動再検証されなかった。
- **ルール**: silent failure で生まれたゾンビレコードを後から検出・修復する
  ロジック（_find_verification_targets の「破損は再検証対象」拡張）を、
  パイプライン修正時に必ずセットで入れる。「直したから次から正しい」では
  既存データは救えない。

### Ollama の `/v1/models` は埋め込みモデルとチャットモデルを区別しない
- `_pick_model_candidates` が `/v1/models` の全モデルを順にチャット候補に追加し、
  `bge-m3` / `nomic-embed-text` を `/v1/chat/completions` に POST して連続 400。
  1 verify あたり20分超の暴走を起こしていた。
- **ルール**: ローカル LLM ホストから取得したモデル一覧をフォールバック候補に
  使う場合、必ず**用途（chat / embed / vision）でフィルタする**。Ollama API には
  メタ情報がないので名前パターン（bge / nomic-embed / embed / e5 / gte 等）で
  ヒューリスティック判定し、誤判定時は環境変数で上書き可能にしておく。

### LLM 解析失敗は raw 応答の先頭をログに残せ
- `_call_verify_llm` が「JSON 解析失敗」と言うだけで応答内容を捨てていたため、
  原因がモデル選択ミス（埋め込みフォールバック）か応答品質劣化か切り分けに
  E2E 実行を何度も繰り返す羽目になった。
- **ルール**: LLM 出力を構造化解析する箇所で失敗ハンドラを書くときは、
  raw 応答の先頭 N 字を必ず WARN レベルでログに出す。デバッグ可観測性は
  パース堅牢化より優先順位が高い。

### Ollama OpenAI 互換エンドポイントで `response_format` を試行的に付けない
- `response_format={"type":"json_object"}` を「受理されなければ通常応答に戻る」と
  期待して付けたが、gpt-oss:20b では応答品質が逆に悪化し JSON 解析が3連続失敗した。
- **ルール**: OpenAI 互換だがバックエンドが Ollama の場合、`response_format` は
  「黙って無視される」のではなく「黙って品質劣化させる」可能性がある。実環境で
  A/B を取ってから本採用する。先に system prompt の「JSON のみ」指示で十分なことが多い。
