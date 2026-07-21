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

---

# 立場別200文字サマリー Phase 1: データ層実装（2026-07-12）

## 背景
README の「立場別200文字サマリー仕様（提案）」を実装。既存の `perspectives`（50字程度の短評、engineer/management/consumer）は変更せず、200字前後の発展版 `perspective_digest` を追加。段階導入方針に基づき、本番の夜間パイプラインには自動組み込みしない。

## 実装内容
- **`src/db.py`**: `topic_insights` に `ensure_column(cur, "topic_insights", "perspective_digest", "TEXT")` を追加
- **`src/llm_insights_pipeline.py`**: `upsert_insight()` の INSERT/ON CONFLICT に `perspective_digest` カラムを追加（`insight.get("perspective_digest")` が無ければ `{}` を保存する後方互換）
- **`src/llm_insights_api.py`**: `_extract_evidence_domain` / `_normalize_perspective_digest` / `call_llm_perspective_digest` を追加。80字未満はフォールバック対象として空文字（実機検証後に120→80へ調整、下記「追補」参照）、260字超は `…` で切り詰め、evidence_urls先頭ドメインを末尾に付与（無ければ「（参考情報未取得）」）
- **`src/generate_perspective_digest.py`**（新規）: 手動バックフィルスクリプト。`perspective_digest` 未生成の `topic_insights` 行を対象に `call_llm_perspective_digest` を呼び、UPDATE。`--limit`（デフォルト20、上限200）と `--dry-run` をサポート
- **`tests/test_perspective_digest.py`**（新規）: 10件（正規化・ドメイン抽出・LLM呼び出しの組み立てをカバー）
- **`README.md`**: 「提案」の見出しを外し、Phase 1実装済みである旨と使い方を追記

## 検証
- `python -m pytest -q` 全体: 236 passed, 12 failed（すべて実装前から存在する pre-existing 失敗。`test_opinion_page.py` 系9件・`test_docs_asset_paths.py` 1件は `render_main.py`/`render.py` の内容不一致、`test_exception_handling.py` 2件は `DummyConn` に `close` 属性が無いテスト側の不備で、いずれも今回変更した `db.py` / `llm_insights_api.py` / `llm_insights_pipeline.py` / `generate_perspective_digest.py` とは無関係）
- 新規10件は全件 pass

## 追補: 実機dogfooding で発覚した重大バグと修正（同日）

初回実装のプロンプトは「各値は170〜230字程度」という**文字数目標**を含んでいた。
これを実際のローカルOllama（PC1、既定モデル `gpt-oss:20b`）で `call_llm_perspective_digest` を直接呼び出して検証したところ、
**全ケースで空応答**になることが判明した。

### 原因
生応答を確認すると、`reasoning` フィールドが「200文字くらい書く。1文字ずつ数えよう…」という
文字カウントの独り言で `max_tokens`（900）を全部消費し、`finish_reason: "length"`・`content` が空文字のまま返っていた。
文字数を厳密に狙わせる指示が gpt-oss の reasoning を暴走させる（＝「実装完了」であって「実用レベル」ではなかった）。

### 修正
- `src/llm_insights_api.py` の `call_llm_perspective_digest`: プロンプトを「170〜230字程度」→「2〜3文」に変更（文字数を数えさせない）
- 同関数のペイロードに `"reasoning_effort": "low"` を追加
- `_DIGEST_MIN_LEN` を 120 → 80 に調整（「2〜3文」指示だと実測150〜200字程度に収まり、120は厳しすぎたため）
- `_DIGEST_PROMPT_SAMPLES` にサンプル文言の新表記を追加

### 検証結果
- 修正後、ローカルOllama（PC1, gpt-oss:20b）に2記事×3視点=6件を実投入。全件で `finish_reason: stop`・150〜200字程度の実用的な内容が3〜4秒で生成されることを確認（例: 「既存のAPIキー方式から新認証方式への移行を計画的に進めることが重要です。まずは移行ガイドを確認し…（参考: example-cloud.com）」）
- `python -m pytest -q`: 236 passed, 12 failed（pre-existing failure のみ、修正前と同一件数・同一テスト名で新規リグレッションなし）

## 次回セッション向け残タスク（Phase 1 時点）
- [x] `render_main.py` での `perspective_digest` レンダリング未実装（表示UIは今回のスコープ外）→ **Phase 2 で確認: 実装済み**（下記参照）
- [ ] 本番パイプライン（`llm_insights_local.py` 等）への自動統合可否の判断（毎晩の所要時間・LLM呼び出し回数への影響を評価してから判断する）。品質は実機検証済みなので統合の障害は解消済み
- [x] `generate_perspective_digest.py --limit 20` を本番DB（NULL件多数）に対して実行し、大量件数でも品質が安定するか確認 → Phase 2 で実施済み
- [ ] 「gpt-oss:20b + 文字数指定 + reasoning肥大化」の知見を `C:\work\★Template\tasks\knowledge.md`（Template本体）に反映する（今回は夜間モードの書き込み禁止に阻まれたため未反映。`隙間時間有効活用\tasks\knowledge.md` には反映済み）
- [ ] 上記12件の pre-existing テスト失敗（`test_opinion_page.py` 等）は本タスクのスコープ外だが、別途根本原因調査が望ましい

---

# 立場別200文字サマリー Phase 2: render_main.py 表示実装の確認・テスト・dogfooding（2026-07-13）

## 発端
Phase 1 の todo.md には「`render_main.py` での `perspective_digest` レンダリング未実装」と残タスク記載があったが、
Phase 2 セッション開始時に `src/render_main.py` の作業ツリー（未コミット）を調査したところ、**該当実装は既に完了していた**ことが判明。
本リポジトリは夜間パイプライン（`daily update (local LLM)` コミット）や他の並行セッションによって継続的に更新されており、
Phase 1 の todo.md 更新後・Phase 2 セッション開始前のどこかのタイミングで、別プロセスが実装を完了させたとみられる（コミット未実施のため git log には現れない）。

## 確認内容（既存実装の検証）
- **テンプレート**: `HTML`（tech ページ, `t.` ループ, render_main.py:744-750）と `NEWS_HTML`（news ページ, `it.` ループ, render_main.py:998-1005）の両方に、
  既存の `perspectives` ブロック直後に `perspective-digest` div（小見出し「立場別くわしい解説」）が実装済み。`{% if t.perspective_digest %}` / `{% if it.perspective_digest %}` で空/NULL時は非表示。
- **Python側**: `grep '"perspectives": _safe_json_obj'` で見つかった9箇所（依頼書の想定8箇所と近似、実測9）すべてで直後に `"perspective_digest": _safe_json_obj(perspective_digest)` が追加済み。SQL SELECT・タプルアンパックも全箇所で `perspective_digest` カラムを取得済み。
- ただし9箇所のうち実際にテンプレートで `perspective_digest` を表示するのは `topics_by_cat`（tech ページの `t.` ブロック経由）と `render_news_region_page`（news ページの `it.` ブロック経由）の2系統のみ。残り（`jp_priority_top` 等の Top10 サイドウィジェット）は `perspectives`/`perspective_digest` とも元々表示していない簡易カードのため、データだけ保持していても実害なし。

## 追加実装
- **テスト追加**（`tests/test_render_utilities.py`）: レンダリング関数（`render_news_region_page` の出力を実際に `Template(NEWS_HTML).render()` してHTML化）の単体テストを2件追加
  - `test_news_html_renders_perspective_digest_section`: perspective_digest ありの記事で「立場別くわしい解説」見出し・本文が `perspectives`（短評）の直後に表示されることを確認
  - `test_news_html_hides_perspective_digest_when_empty`: perspective_digest が `{}` の記事では見出し自体が出ないことを確認
- 既存の `test_fetch_news_articles_by_category_includes_perspective_digest` / `test_render_news_region_page_item_has_perspective_digest`（データ層）と合わせて計4件が本機能をカバー

## 検証
- `python -m pytest -q`: **240 passed, 12 failed**（Phase 1 と同一の pre-existing 失敗12件のみ。新規リグレッションなし。新規4件はすべて pass）

## dogfooding（実データでの動作確認）
1. 本番DB `data/state.sqlite`（498MB）を `data/state.sqlite.bak2_20260713_0207` にバックアップ
2. `python src/generate_perspective_digest.py --limit 20` を実行 → `updated_rows=20`（news 10件・market 5件・policy 2件・decarbonization_ops 2件・ai 1件）。生成内容を目視確認、日本語として自然・具体的（例:「技術者は、事件発生場所の周辺環境を監視システムやセンサーで継続的にモニタリングし…（参考: news.web.nhk）」）
3. `python src/render.py` を実行（8.6秒で完了）→ `docs/news/index.html` に `立場別くわしい解説` が10件表示されることを grep で確認（news カテゴリの10件と一致）
4. `docs/index.html`（tech ページ、`t.` ブロック側）では今回バックフィルした market/policy/decarbonization_ops/ai の10トピックは **1件も表示されなかった**（`grep topic-<id>` で0件）。原因はレンダリング側のバグではなく、バックフィル対象が `ORDER BY updated_at DESC` で選ばれた「最近 perspective_digest 未生成のまま更新された」トピックであり、必ずしも tech ページの表示条件（直近48h・カテゴリ別 importance/recent 上位N件）を満たすとは限らないため（データ選定上の制約）。tech ページ側のレンダリングロジック自体は news ページと完全に同一パターンであり、コード上・ユニットテスト上は動作確認済み

## 結論
- 依頼内容（render_main.py への表示実装・テスト・dogfooding）はすべて充足。Phase 2 のスコープは完了とする
- 本番パイプラインへの自動統合（Phase 1 残タスク）は引き続き未着手・要判断事項として残す

---

# 立場別200文字サマリー Phase 3: 本番パイプライン自動統合の可否判断（2026-07-13）

## 判断事項
Phase 1/2 から繰り返し持ち越されていた「`perspective_digest` を本番夜間パイプラインに自動統合するか」を検討した。

### 比較した2案
1. **`src/llm_insights_local.py` の1トピックあたりのループ内に `call_llm_perspective_digest` を直接組み込む案**
   - `llm_insights_local.py` は `max_sec`（既定300秒）・`delay`（既定3秒）で予算管理された本番メインループで、`C:\work\run_daily.bat` から `--rescue` 付きで毎晩呼ばれている（直近実行: 2026-07-13 06:33、本セッション開始40分前）
   - ここに2本目のLLM呼び出しを挟むと**1トピックあたりの所要時間が実質2倍**になり、同じ `max_sec` 予算内で処理できるトピック数が黙って半減する。主機能（`perspectives`/`importance`等の本体insight生成）のスループットを犠牲にするため不採用
2. **既存のオプトイン・バックフィルスクリプト `generate_perspective_digest.py` を独立ステップとして夜間バッチに追加する案**
   - 本体ループの予算・挙動に触れずに済み、既存の `forecast_generate`/`forecast_verify`（`run_daily.bat` 内、失敗しても `[WARN] ... continuing` で継続する non-fatal パターン）と同じ位置づけで追加できる
   - **採用**。ただし実行手順（下記）は本セッションでは適用せず、判断と受け入れ準備のみ行う

### 本セッションで実施した受け入れ準備
- `generate_perspective_digest.py` に `llm_insights_local.py` と同様の **`--max-sec` 時間予算ガード**を追加（既定は env `PERSPECTIVE_DIGEST_MAX_SEC`、未設定なら0=無制限）。従来は `--limit` のみで時間上限がなく、無人実行に組み込むには危険だった
- ユニットテスト4件追加（`tests/test_generate_perspective_digest.py`）: 全件処理・時間予算超過時の早期打ち切り・env変数からのデフォルト解決・dry-run
- `python -m pytest -q`: **244 passed, 12 failed**（Phase 1/2 と同一の pre-existing 失敗12件のみ、新規4件は全件pass、リグレッションなし）
- 本番DBを `data/state.sqlite.bak2_20260713_0715` にバックアップ後、実機dogfooding: `python src/generate_perspective_digest.py --limit 20 --max-sec 5` を実行 → モデルのコールドスタート込みで1件処理した時点で経過9.6秒 > max_sec(5) となり `[TIME] ... budget reached` を出力して安全に打ち切られることを確認。DBには当該1件の `perspective_digest` が実際に保存されていることも確認済み

### run_daily.bat / .github/workflows/daily.yml への実際の組み込みは今回は見送った
**理由**:
- `run_daily.bat`（`C:\work\run_daily.bat`）は **未git管理**かつ、本セッション開始のわずか34分前（06:33）に自動push付きで実行されたばかりの生きた無人本番パイプライン。作業ツリー（`git status`）は他プロセスによる多数の未コミット変更が既に存在する状態で、ここに自律発案セッションが割り込んで手を入れると、可逆性（誤りがあってもすぐ戻せるか）と安全性（次回無人実行が想定通り動くか）を十分検証しないまま本番に影響してしまうリスクがある
- CLAUDE.md の「Stability Over Speed」「変更は常にロールバック可能にする」の原則に照らし、今回は判断とスクリプト側の安全策（`--max-sec`）の追加に留め、実際の配線はユーザーの明示的な承認を得てから行うのが適切と判断した

### 組み込み手順（ユーザー承認後に適用する想定の具体案）
`run_daily.bat` の `llm_insights_local --rescue` ステップの直後・`render` ステップの前に、`forecast_generate`/`forecast_verify` と同じ non-fatal パターンで以下を追加する:
```bat
set "LASTSTEP=generate_perspective_digest"
py -3.11 -u src\generate_perspective_digest.py --limit 30 --max-sec 120 >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" (
  echo [WARN] generate_perspective_digest failed rc=!RC!, continuing >> "%LOG%"
)
```
`--limit 30 --max-sec 120` は保守的な初期値の一例（1晩で最大30件・最大2分）。実運用に入れる場合は数晩分のログ（`[TIME] generate_perspective_digest ... sec=`）を見ながら調整するとよい。

## 次回セッション向け残タスク
- [ ] （ユーザー承認前提）上記の `run_daily.bat` 組み込みを実際に適用し、1晩分のログで想定通り動くか確認する
- [ ] 「gpt-oss:20b + 文字数指定 + reasoning肥大化」の知見の Template本体 (`C:\work\★Template\tasks\knowledge.md`) への反映（引き続き夜間モードの書き込み制限で未実施）
- [x] pre-existing テスト失敗12件（`test_opinion_page.py` 等）の根本原因調査 → 2026-07-13 全体改善タスク（下記）で解消

---

# プロジェクト全体改善タスク（2026-07-13）

3並列調査（src/ コード品質・docs/ 出力とDB・CI/リポジトリ衛生）の結果を受け、ユーザー承認のもと全項目に対応する。

## 事前調査で確定した重要事実
- 直近100コミットすべてローカル（PC2）発。CI（daily.yml）のコミットは実質機能していない
- `docs/index.html` と `docs/tech/index.html` の完全一致は `run_daily.bat` の意図的な copy（バグではない）
- `topic_snapshots`（150万行、DB肥大の主因）の利用者は `diff_view.py` のみで直近2日しか参照しない → retention 導入は安全
- `.bak2_*` バックアップは過去セッションの手動作成（自動生成コードなし）
- 意見ページは `7fafd026 "remove: 立場別意見ページを廃止"` で意図的に廃止済み。`OPINION_HTML` は削除漏れの死コード、`test_opinion_page.py` は廃止機能への陳腐化テスト
- **`.gitignore` の許可リスト漏れにより `docs/topic/` `entity/` `diff/` `exec/` `api/` `search*.{html,json}` `sitemap.xml` `feed.xml` が未追跡 → GitHub Pages で404**（追跡は102ファイルのみ）

## Phase A: リポジトリ衛生
- [x] .gitignore: docs 許可リストに topic/entity/diff/exec/api/search/sitemap/feed を追加、opinion 許可を削除、ローカル bat（★*.bat, 01_git pull.bat）・.claude/・docs_backup/ を除外
- [x] `git rm --cached data/state.sqlite`（.gitignore の「DO NOT COMMIT」意図に合わせ追跡解除。504MB は GitHub の 100MB 制限で push 不能になるため必須）
- [x] 古いバックアップ削除（bak2_20260712_1217, bak2_20260713_0207, 旧 .bak。最新 bak2_20260713_0715 は保持）→ 約1GB 解放
- [x] 未追跡の新規 src/tests/tasks ファイルをコミット対象に

## Phase B: テスト整備（12件の失敗解消）
- [x] test_opinion_page.py を削除（廃止済み機能のテスト）
- [x] OPINION_HTML と意見ページ専用の死コードを render_main.py から削除
- [x] test_exception_handling.py: DummyConn に close() 追加
- [x] test_docs_asset_paths.py の失敗調査・修正

## Phase C: CI 再設計
- [x] daily.yml をパイプライン実行+コミットから検証専用（feed_lint + pytest）へ転換。デバッグステップ削除。発行はローカル（PC2）に一本化

## Phase D: コード修正
- [x] git_auto_push.py: shell=True + f-string → リスト形式 subprocess、state.sqlite コンフリクト特例削除（追跡解除に伴い不要）、docstring 修正
- [x] サイト URL 一元化（site_config）+ og:url の dachshund-github ドメイン誤り修正
- [x] data-date="None" 修正（published_at 欠損時の str(None) 漏出）
- [x] entities.yaml 作成（entities.py が参照するのに未存在）
- [x] watchdog.py: index.lock 自動削除の安全化（git プロセス生存確認）
- [x] 新規5モジュールの重複 HTML スタイルを共通モジュールへ
- [x] collect_health_*.jsonl のローテーション（90日超を削除）

## Phase E: データ整備
- [x] topic_snapshots に retention（14日）を組み込み + 一回限りの purge & VACUUM（481MB→縮小）
- [x] suspended フィード44件の HTTP 再チェック → 生きているものは failure_count リセット、死んでいるものは一覧化

## Phase F: 検証・ドキュメント・コミット
- [x] pytest 全 green
- [x] render 実行で docs 生成確認
- [x] CLAUDE.md / README 更新（opinion 廃止反映・新モジュール追記）
- [x] 論理単位でコミット & push
- [x] lessons.md 更新

## スコープ外（今回は見送り・提案のみ）
- render_main.py（5,419行）の全面分割 → 段階的に実施すべき大規模リファクタのため別タスク化
- git 履歴の肥大解消（filter-repo）→ force-push を要するため要ユーザー判断
- forecast の過去欠損日（6/13-23, 6/29）→ 過去日付の予測は遡及生成不能
- 古い topic ページの削除 → パーマリンク価値があるため保持

## 実施結果（2026-07-13）
- テスト: 256件(244 pass/12 fail) → **224件 全pass**（意見ページ廃止に伴う陳腐化テスト34件を削除、DBエラー再送出仕様を復元）
- render_main.py: 5,419行/232KB → **4,355行/179KB**（意見ページの死コード1,064行を削除）
- DB: **504MB → 231MB**（topic_snapshots 113万行パージ + VACUUM。以後14日retentionで自動パージ）
- data/: 旧バックアップ削除で**約1GB解放**（最新 bak2_20260713_0715 は保持）
- .gitignore 修正により docs/topic・entity・diff・exec・api・search・sitemap・feed.xml が**初めて公開対象に**（従来はローカル生成止まりで本番404）
- entities: 辞書を13→45エントリに拡充（entities.yaml 新設）、単語境界照合に修正。誤リンク再構築で 12,145 → 3,673 links（約7割が「Meta→metal」等の誤マッチだった）
- CI: daily.yml 廃止 → ci.yml（feed_lint + pytest の検証専用）。発行はPC2に一本化
- 停止フィード45件を再チェック（src/feed_recheck.py 新設）: **全滅（復活0件）**。failure_count>=100 の32件は30日suspendに変更

### 死亡フィード一覧（sources.yaml の棚卸し候補・要URL差し替えまたは削除）
404: iso.org, enisa, jisc.go.jp, ai.googleblog.com, ai.facebook.com, github.blog/ml,
nipponsteel.com, kobelco.co.jp, posco-inc.com:4451, nucor.com, ussteel.com, thyssenkrupp-steel.com,
siemens.com/cert, aveva.com, rockwellautomation.com, nttdata.com, aws.amazon.com/blogs/industries,
digital.go.jp, soumu.go.jp, nedo.go.jp, metro.tokyo.lg.jp, ec.europa.eu, ipa.go.jp, prtimes.jp/it,
automationworld.com, controlglobal.com, primetals.com, steeltimesint.com, sms-group.com,
danieli.com, zeiss.com, ghgprotocol.org, env.go.jp
403: cisa.gov(KEV/SBOM/ICS), iec.ch, arcelormittal.com, tatasteel.com, meti.go.jp
200だが空: cloud.google.com/blog/rss, recyclingtoday.com, tenova.com
接続不可: azure.microsoft.com(IoT blog, timeout), blog.skf.com

### 残タスク（次回以降）
- [ ] 上記死亡フィードの URL 差し替え（各サイトの新フィードURLを Web で調査）または sources.yaml からの削除
- [x] render_main.py の段階的分割の継続（テンプレート外部化）→ 2026-07-21 第1弾・第2弾実施（下記参照）。残り2テンプレート（`FORECAST_HTML`/`FORECAST_HITS_HTML`）は未着手
- [ ] git 履歴の肥大解消（filter-repo で過去の state.sqlite blob を除去。force-push を伴うため要ユーザー判断）

---

# render_main.py テンプレート外部化 第1弾（2026-07-21・自律発案）

## 実施内容
render_main.py（4,397行）にインライン埋め込みされていた6個の巨大Jinja2テンプレート文字列
（`PORTAL_HTML`/`HTML`/`NEWS_HTML`/`OPS_HTML`/`FORECAST_HTML`/`FORECAST_HITS_HTML`）のうち、
`PORTAL_HTML` と `NEWS_HTML` の2個を `src/templates/` に外部化した（commit `049dfc82`）。

- `_TEMPLATE_DIR = Path(__file__).parent / "templates"` と
  `_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))` を追加
- `NEWS_HTML` → `src/templates/news.html`。`Template(NEWS_HTML).render(...)` を
  `_jinja_env.get_template("news.html").render(...)` に置換（news/index.html 生成で実使用中）
- `PORTAL_HTML` → `src/templates/portal.html`。**着手前の調査で、現在このテンプレートは
  render_main.py 内のどこからも `render()` されていない死コードと判明**
  （docs/index.html は `HTML`/`tech_html_root` から生成されており、`PORTAL_HTML` を参照する
  呼び出し箇所は存在しなかった）。git log では継続的に編集されている形跡があり、
  過去に明示的な「廃止」コミット（OPINION_HTML削除時の `7fafd026` のような）も見当たらないため、
  安全側の判断として削除はせず、内容を保持したままファイル化するに留めた
  （将来ポータルページとして再利用する場合は `_jinja_env.get_template("portal.html")` で読み込める）
- `tests/test_render_utilities.py` の `_render_news_html` ヘルパーを新しい読み込み方式に追従修正

## 検証方法・結果
- 変更前後で `python src/render.py` を実行し、生成された `docs/` を比較
  （タイムスタンプが常時変動するため厳密なバイト完全一致にはならない前提で、
  全108件の差分ファイルについて `generated_at` 系タイムスタンプ行以外に差分がないことを
  Pythonスクリプトで自動検証。非タイムスタンプ差分ゼロを確認）
- `python -m pytest -q`: 224 passed（新規リグレッションなし）
- `render_main.py`: 4,397行 → 4,093行（-304行）
- 検証用に生成した `docs/` の差分・`docs_baseline_compare/` 退避コピーはコミット前に
  `git checkout -- docs` で元に戻し、退避ディレクトリも削除済み（リポジトリはクリーンな状態でコミット）

## 次回候補（未着手・残り4テンプレート）
- [ ] `HTML`（tech ページ本体、約400行）
- [ ] `OPS_HTML`（運用メトリクスページ）
- [ ] `FORECAST_HTML`（未来予測ページ・過去分含め複数箇所で呼び出し）
- [ ] `FORECAST_HITS_HTML`（予想的中ページ）
- 上記いずれも `_jinja_env.get_template(...)` への置換で同様の手順が使える
  （Jinja2の `Environment`/`FileSystemLoader` インフラは今回のコミットで整備済み）
- 抽出時の注意点: 元の `r"""..."""` 文字列は開始直後に改行が1つ入る（`r"""\n<!doctype...`）ため、
  外部化したテンプレートファイルの先頭に空行を1行残さないと出力の先頭に空行が1行減るバグになる
  （今回の作業で実際にハマった箇所。ファイル抽出後は必ず元の文字列と1文字単位で比較すること）

---

# render_main.py テンプレート外部化 第2弾（2026-07-21・夜間ランナー）

## 実施内容
第1弾の続き。残り4テンプレートのうち `HTML`（tech ページ本体・docs/index.html および
docs/tech/index.html 生成に実使用中）と、時間に余裕があったため `OPS_HTML`（運用メトリクスページ・
docs/ops/index.html 生成に実使用中）の2個を追加で `src/templates/` に外部化した。

- `HTML` → `src/templates/tech.html`。`Template(HTML).render(...)` の2箇所（`tech_html_sub` /
  `tech_html_root` 生成、それぞれ docs/tech/index.html と docs/index.html に対応）を
  `_jinja_env.get_template("tech.html").render(...)` に置換
- `OPS_HTML` → `src/templates/ops.html`。`Template(OPS_HTML).render(...)` を
  `_jinja_env.get_template("ops.html").render(...)` に置換（docs/ops/index.html 生成で実使用中）
- 抽出は手作業の書き写しではなく、Python スクリプトで `render_main.py` の該当行範囲を
  バイト単位でスライスして `src/templates/*.html` に書き出し、`import render_main` した
  実行時の変数値（`render_main.HTML` / `render_main.OPS_HTML`）と文字列完全一致することを
  スクリプトで検証してから元の変数定義を削除する手順を踏んだ（第1弾で判明した「先頭改行」の
  落とし穴を機械的に回避するため）
- `tests/test_render_utilities.py` 等を確認したが、`HTML`/`OPS_HTML` 変数や専用ヘルパーに
  依存するテストは存在しなかった（`NEWS_HTML` の `_render_news_html` のような追従修正は不要）

## 検証方法・結果
- `HTML`→`tech.html`: 変更前（`git stash` で一時的に旧コードへ戻す）と変更後それぞれで
  `python src/render.py` を実行し `docs/` を比較。バイト差分が出た109ファイルのうち
  非タイムスタンプ差分は5ファイル（`feed.xml` の `lastBuildDate`、`index.html`/`tech/index.html`/
  `news/index.html`/`ops/index.html` の `new48h` 系カウント・`+NN/48h` バッジ）のみ。
  これらが本変更由来か切り分けるため、変更後コード のみで `render.py` を数十秒間隔で2回連続実行し
  再度比較したところ、同一コードでも同じ種類の差分（時刻・48h集計カウント）が発生することを確認。
  すなわち `datetime.now()` 基準の48h集計が実行タイミングでぶれる既存の仕様であり、
  今回のテンプレート外部化によるレンダリング内容の変化ではないと判断した
  （tech.html の内容自体は `render_main.HTML`（旧変数）とスクリプトでバイト完全一致を確認済み）
- `OPS_HTML`→`ops.html`: 同様に `python src/render.py` 実行後、`docs/ops/index.html` を
  変更前（コミット済み `docs/`）と比較。差分は701行中6行のみで、いずれもタイムスタンプ行と
  ソース別48h集計カウント（`BBC World`/`OilPrice.com`/`ITmedia NEWS`等の数値列）で、
  上記と同種の時刻依存の揺れと確認。行数・構造の差分はゼロ
- `python -m pytest -q`: 224 passed, 0 failed（新規リグレッションなし。前回セッションで
  記録されていた pre-existing 12件の失敗は、その後の別コミット（daily update 等）で
  解消済みとみられ今回は再現しなかった）
- `render_main.py`: 4,093行 → 3,495行（-598行）
- 検証用に生成した `docs_baseline_compare` / `docs_before` / `docs_after1` / `docs_baseline2`
  等の退避ディレクトリ、および抽出・検証用の一時スクリプト（`extract_*.py` / `verify_*.py` /
  `remove_*.py` / `compare_*.py`）はすべて削除し、`git checkout -- docs` で `docs/` を
  コミット前の状態に戻した上でコミットした

## 次回候補（未着手・残り2テンプレート）
- [ ] `FORECAST_HTML`（未来予測ページ・過去分を含め複数箇所から呼び出されており依存関係が複雑なため
  今回もスコープ外とした）
- [ ] `FORECAST_HITS_HTML`（予想的中ページ）
- 上記も `_jinja_env.get_template(...)` への置換で同様の手順が使える見込みだが、
  呼び出し箇所が複数・条件分岐を伴う可能性があるため、着手前に呼び出し箇所を全て洗い出すこと

---

# render_main.py テンプレート外部化 第3弾（2026-07-22 02:07・夜間ランナー・自律発案）

## 実施内容
残り2テンプレート（`FORECAST_HTML`・`FORECAST_HITS_HTML`）を`src/templates/forecast.html`・
`src/templates/forecast_hits.html`として外部化した。これで全6テンプレートの外部化が完了。

- 呼び出し箇所を事前にgrepで洗い出し: `FORECAST_HTML`は2箇所（現在レポート`forecast_html`・
  過去レポートループ内`pr_html`）、`FORECAST_HITS_HTML`は1箇所（`html`）
- 抽出は第2弾と同じ「バイト単位スライス→`import render_main`した実行時変数値との文字列完全一致を
  スクリプトで検証→元の変数定義を削除」手順を踏襲
- **CRLF保持に関する新知見**: `render_main.py`はCRLF改行だが、Pythonがソースをコンパイルする際に
  文字列リテラル内の`\r\n`も含めユニバーサル改行変換で`\n`のみに正規化してメモリ上に保持するため、
  `open(path, encoding="utf-8").read()`（デフォルトのテキストモード）で読んだ変数値は常に`\n`のみになる。
  これをそのまま`open(outfile, "w", encoding="utf-8", newline="\n")`で書き出すとテンプレートファイルが
  LFのみになり、既存4テンプレート（すべてCRLF）と不整合が生じる。回避策: 書き込み時は`newline`引数を
  指定せず（Windowsのデフォルトテキストモード書き込みに`\n`→`\r\n`変換を任せる）、CRLFで統一する。
  一方、`render_main.py`自体の行削除・置換編集は`open(path, encoding="utf-8", newline="")`で読み書きし
  ユニバーサル改行変換自体を無効化してCRLFを文字通り保持する必要がある（読み込み時にデフォルトモードを
  使うと全行がLFに正規化され、無関係な行まで含めた巨大な差分になってしまう）
- `render_main.py`: 3,495行 → 3,109行（-386行）

## 検証方法・結果
- `python -m pytest -q`実行で1件失敗（`test_navigation_contains_ops_page_link`）を発見:
  `render_main.py`本体のソース文字列に`/daily-tech-trend/ops/`というナビリンク文字列が含まれることを
  検証するテストだったが、このリンクは`FORECAST_HTML`（今回外部化）に残っていた最後の1箇所であり、
  外部化によってrender_main.py本体からこの文字列が消えたため失敗した。`git stash`で変更前のコードに
  戻して同テストを実行し、変更前は成功（＝今回の変更による純粋なリグレッション）であることを確認した。
  第1弾・第2弾で外部化した`PORTAL_HTML`/`NEWS_HTML`/`HTML`/`OPS_HTML`にも同じナビリンク文字列が
  含まれていたが、当時はまだ`FORECAST_HTML`が本体に残っていたためテストが通っていた、という
  「段階的外部化の副作用が最後の1個を消すまで顕在化しなかった」ケースだった。
  `tests/test_docs_asset_paths.py`に`_read_render_sources()`（render_main.py本体＋
  `src/templates/*.html`全件を連結して返す）を追加し、`test_navigation_contains_ops_page_link`が
  このヘルパーを使うよう修正。修正後`python -m pytest -q`で224件全合格を確認
- `python src/render.py`実行前後で`docs/`を比較したところ、forecast配下99ページ・feed.xml・
  api/*.json含め109ファイルに差分が出た。中身を確認したところタイムスタンプ以外に、
  Markdown箇条書き（`1. **予測内容**：...`形式）が`<p>`羅列と`<ol><li>`の2パターンで揺れる
  構造的な差分が見つかり、当初は今回の変更による影響を疑った。しかし**同一コード（変更後）で
  render.pyを2回連続実行しても差分が発生**し、さらに**`git stash`で変更前の旧コードに戻して
  実行しても同じ揺れが再現**したため、今回のテンプレート外部化とは無関係な、既存のMarkdown
  変換処理の非決定性（原因未特定、`markdown`ライブラリの拡張処理順序等が疑われる）であると
  切り分けられた。検証用に生成した`docs_baseline_compare`/`docs_after1`退避コピーと
  一時スクリプト（`extract_forecast_tmp.py`/`remove_forecast_tmp.py`/`debug_forecast_tmp.py`）は
  すべて削除し、`git checkout -- docs`で`docs/`をコミット前の状態に戻した上でコミットした
  （forecastページのMarkdown非決定性は本タスクのスコープ外のため、下記「次回候補」に記録するに留める）
- 着手前・完了後とも`Get-ScheduledTask`で`Daily Tech Trend`/`Watchdog Daily Tech Trend`/
  `CollectedInfo_Pipeline`が`Ready`（実行中でない）であることを確認済み。`run_daily.bat`には触れていない

## 次回候補
- [ ] テンプレート外部化自体は6/6完了。今後は`render_main.py`の残り約3,100行（DB読み書き・
  データ集計ロジック中心）の可読性改善が次の分割候補になりうるが、テンプレート文字列のような
  自己完結した単位ではないため難易度が上がる

---

## 2026-07-22 07:07 自律発案: forecastページMarkdown非決定性の再調査（結論: 誤診断・対応不要）

前回セッション（02:07）で「forecastページのMarkdown箇条書きレンダリングが`<p>`羅列と
`<ol><li>`の間で非決定的に揺れる」と報告された件を再調査した。結論: **再現せず。実際には
`generated_at`系タイムスタンプの差分のみであり、Markdownレンダリング自体は完全に決定的**
だったと判明した（前回セッションの診断は誤り）。

### 調査内容
1. `md_to_html()`が実際に使っているのは`markdown`パッケージではなく`mistune`
   （`mistune.create_markdown(plugins=["table"])`、`render_forecast_page()`内でローカル関数として
   都度生成）だったため、まずこの前提を訂正した
2. `parse_forecast_markdown`/`parse_prediction_items`で全101件の`data/forecasts/report_*.md`から
   抽出した全セクション（executive_summary・checked_report・appendix×2・perspectives・
   predictions各horizon×item、計1,960項目）を`md_to_html()`でレンダリングしSHA256ハッシュ化する
   スクリプトを作成し、別プロセスとして3回起動して比較 → **1,960項目×3回、完全に同一のハッシュ**
   （mistuneのレンダリングはプロセスを跨いでも決定的）
3. 上記だけでは実際のパイプライン全体（Jinja2テンプレート結合・DB読み取り順序等）をカバーしないため、
   `python src/render.py`を同一DB状態で2回連続実行し`docs/`を比較する、前回と同じ手法で再検証した。
   着手前に`Get-ScheduledTask`で`Daily Tech Trend`/`Watchdog Daily Tech Trend`/`CollectedInfo_Pipeline`
   が`Ready`であることを確認済み
4. 差分が出たファイルは110件（前回の109件とほぼ同数）だったが、**全ファイルとも差分行数はちょうど2行
   （1行の書き換えのみ）で、中身は`generated_at`/`Generated (JST)`/`最終更新`いずれかの
   タイムスタンプ表示だけ**だった（`diff <file1> <file2> | grep -c '^[<>]'`で110ファイル全件を機械的に
   確認、Markdown構造（`<p>`/`<ol>`等）の差分は1件も存在しなかった）
5. 前回セッションが「タイムスタンプ以外の構造差分」と報告したのは、`grep -v`等での除外パターンが
   `generated_at`表記ゆれ（ページごとに"Generated (JST)"/"最終更新"/ラベルなしの3パターンがある）を
   拾いきれず、除外しきれなかったタイムスタンプ行を構造差分と誤認した可能性が高いと推測される
   （今回のログでも同じ誤認が再現しかけたため、これが原因だとほぼ断定できる）

### 対応
- 実際のバグが存在しないため、コード修正は行わない
- `python -m pytest -q`は変更なしのため未実行（コード変更ゼロ）
- 検証用一時ファイル（`repro_md_nondeterminism.py`・`repro_hashes_*.txt`・`docs_run1`/`docs_run2`・
  `render_run*.log`）はすべて削除し、`git checkout -- docs`で`docs/`をコミット前の状態に戻して
  作業ツリーをクリーンにした（`git status --short`で確認済み）
- 上記「次回候補」から本項目を削除した（対応不要と判明したため）

---

# 利用価値向上 第1弾（2026-07-13）

## 実施内容
- **ナビ導線整備**: 全5ページ共通ナビに「差分」「企業別」「エグゼクティブ」「🔍検索」「RSS」を追加（従来これらのページへのリンクはゼロで発見不能だった）
- **📈 経緯リンク**: tech ページの各トピックカードからトピックタイムライン（topic/<id>/）へリンク。リンク切れ防止のため、render 時に生成済み HTML から実リンク ID を回収してタイムライン生成対象に含める自己整合方式（render_main.py → topic_timeline.render_topic_timelines(include_ids=...)）
- **RSS 自動検出**: 全5ページの head に <link rel="alternate" type="application/rss+xml">
- **通知の配線**: run_daily.bat に notify.py ステップ追加（webhook 環境変数未設定なら no-op。設定手順は README）
- **perspective_digest 自動生成の配線**: run_daily.bat に --limit 30 --max-sec 120 で組み込み（Phase 3 準備済み案の適用）
- **計測フック**: common.js に GoatCounter フック（DTT_GOATCOUNTER_ENDPOINT 空なら無効。手順は README）
- run_daily.bat は編集前に C:\workun_daily.bat.bak_20260713 へバックアップ済み

## 派生バグ修正（経緯リンク検証で発見）
- **topic_articles の孤児行 9,281件**: dedupe.py が記事削除時に紐付けを掃除していなかった。一括削除＋ dedupe.py 末尾に恒久掃除を追加（テスト用最小DB対応の存在チェック付き）
- **タイムラインの記事0件スキップ**: スキップすると 404 になるため、空状態メッセージつきページを生成する方式に変更
- 検証: 経緯リンク 215件 → 404 ゼロ、全テスト 224 pass

## 残り（第2弾以降・計測データを見てから優先度決定）
- [ ] トップページ軽量化（936KB → 初期表示絞り込み）
- [ ] 検索インデックス(1.9MB)の遅延ロード
- [ ] ダークモード（common.css の変数上書き）
- [ ] ウォッチリスト（localStorage）
- [ ] 死亡フィードの URL 差し替え（Web調査は別エージェントで進行中）

---

# 死亡フィードの棚卸し・差し替え完了（2026-07-13 利用価値向上 第1弾の続き）

Web 調査（別エージェント・全候補を実取得検証）に基づき sources.yaml を更新。

## 復旧・差し替え（実取得検証済み・18/18 OK）
- Google Cloud Blog → cloudblog.withgoogle.com/rss/
- Google AI Blog → research.google/blog/rss/（Research Blog に統合）
- Meta AI → engineering.fb.com/category/ai-research/feed/（公式RSS廃止のため代替）
- GitHub ML → github.blog/ai-and-ml/machine-learning/feed/
- 日本製鉄 → nipponsteel.com/newsroom/news/rss.xml
- Tata Steel → tatasteelnederland.com（欧州部門 Presspage）
- Siemens ProductCERT → cert-portal.siemens.com/productcert/rss/advisories.atom
- Azure IoT → /blog/category/internet-of-things/feed/（要ブラウザUA）
- デジタル庁 → digital.go.jp/rss/news.xml / 総務省 → soumu.go.jp/news.rdf / IPA → alert.rdf
- CISA all/ics/ics-medical: URL 据え置きで復旧（403 の原因は UA。下記参照）
- METI: URL 据え置きで復旧（AWS WAF。ブラウザUA指定）
- 新規追加: SteelOnTheNet（Steel Times Int'l 廃止の代替）、Automation World、Control Global

## collect.py の機能追加
- フィード単位の `user_agent:` オプション（sources.yaml、YAML アンカー &browser_ua で共有）
- user_agent 指定時は Accept/Accept-Language を含むブラウザ相当ヘッダ一式を送信
  （CISA は UA 単体では 403 のまま。ヘッダ一式で 200 になることを実測確認）

## 廃止（コメントで sources.yaml に記録）
- ENISA（新サイトで RSS 全廃・公式告知あり）、神戸製鋼（RSS 終了）、ArcelorMittal（新サイトに RSS なし）、
  CISA の sbom.xml / KEV catalog.xml / ics-recommended-practices.xml（404。KEV は all.xml に流れる。
  KEV 全量が必要なら公式 JSON API → 将来の JSON インジェスト課題）

## 未対応（優先度低・次回以降）
- iso.org / iec.ch / jisc.go.jp / nedo.go.jp / 東京都 / ec.europa.eu(taxation) / prtimes.jp/it /
  recyclingtoday / tenova / sms-group / danieli / zeiss / ghgprotocol / env.go.jp / nucor / ussteel /
  thyssenkrupp / posco / aveva / rockwellautomation / nttdata / aws industries / skf blog（今回の調査対象外）

## DB 整備
- feed_health: sources.yaml に存在しない陳腐化 28行を削除、UA対応で復旧した4フィードの suspend を解除

---

# 利用価値向上 第2弾（2026-07-13）

## 実施内容
- **ダークモード**: common.css に prefers-color-scheme:dark 追従（変数上書き＋ハードコード色の個別補正）。
  サブページ（diff/entity/exec/topic）にも page_common.PAGE_DARK_CSS を適用
- **描画軽量化**: .topic-row に content-visibility:auto（トップは200件超の行があるため画面外の描画をスキップ）
- **検索の遅延ロード**: search-index.json(約2MB) をページ表示時ではなく最初の入力時に fetch
- **タグ選択の永続化**: 選択タグ・AND/OR モードを localStorage に保存し次回訪問時に復元（ウォッチリスト的な使い方）
- **エグゼクティブサマリーの定常運用化**:
  - run_daily.bat に exec_summary ステップを追加（ナビから導線を張ったため毎晩更新が必要になった）
  - gpt-oss の reasoning 暴走による空応答（finish_reason=length）を修正: reasoning_effort=low + max_tokens 1600 + リトライ2回
  - --category 単体実行で index.html が1件に上書きされるバグを修正（ディスク上の全ページから index を構築）
  - 全7カテゴリを llm=yes で再生成済み

## 検証
- render 後、diff/entity/topic/exec 各ページに dark CSS が入っていること、search.html が遅延ロードになっていることを確認
- 全テスト 224 pass

---

# 死亡フィード棚卸し 第2弾 完了（2026-07-13）

Web 調査（24件・全候補を実取得検証）に基づき sources.yaml を更新。第1弾と合わせて棚卸しは完了。

## 復旧・差し替え（9件・全件 collect.py 実取得経路で entries>0 を確認）
- POSCO → newsroom.posco.com/en/feed/（tls_mode: relaxed の例外運用も解消）
- Nucor → IR プレスリリース RSS / thyssenkrupp → グループ全体 RSS / Rockwell → IR プレスリリース RSS
- SMS group → PresseBox 配信 RSS（新規再追加）
- AWS Manufacturing → カテゴリパス変更に追従
- 東京都報道発表 → 新 RSS URL / EU CBAM → taxation-customs.ec.europa.eu / GHG Protocol → rss.xml（再追加）

## 廃止確定（コメントで sources.yaml に記録・14件）
ISO, IEC(ボット保護), JISC, NEDO, 環境省, U.S. Steel(IRサイト消滅), Recycling Today,
Tenova(空フィード), Primetals, AVEVA, NTT DATA, SKF(更新停止), ZEISS, Danieli(ボット保護),
PR TIMES カテゴリ別RDF（index.rdf のみ提供・非IT混在のためカテゴリフィルタ実装まで見送り）

## これで死亡フィード45件の棚卸しがすべて完了
- 第1弾: 17件復旧（うち4件は UA/WAF 対策で復旧）+ 廃止4件
- 第2弾: 9件復旧 + 廃止14件
- feed_health の陳腐化行も全掃除済み（sources.yaml と完全同期）
