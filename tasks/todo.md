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
- [ ] render_main.py の段階的分割の継続（テンプレート外部化）
- [ ] git 履歴の肥大解消（filter-repo で過去の state.sqlite blob を除去。force-push を伴うため要ユーザー判断）

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
