"""forecast_generate.py のユニットテスト（LLM呼び出しを含まないもの）"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forecast_generate import (
    build_markdown_report, build_news_digest,
    HORIZONS, CAT_LABELS, MIN_IMPORTANCE,
    _has_prediction_content,
    _looks_english, _normalize_enum, _localize_prediction_item,
    _IMPACT_MAP, _CONFIDENCE_MAP,
)


class TestBuildMarkdownReport:
    def test_contains_title(self):
        md = build_markdown_report([], {}, "2026-03-28 12:00:00")
        assert "# 多視点ニュース分析・未来予測レポート" in md

    def test_contains_generated_at(self):
        md = build_markdown_report([], {}, "2026-03-28 12:00:00")
        assert "2026-03-28 12:00:00" in md

    def test_contains_executive_summary(self):
        summary = [{"title": "テストポイント", "impact_description": "影響あり"}]
        md = build_markdown_report(summary, {}, "2026-03-28 12:00:00")
        assert "テストポイント" in md
        assert "影響あり" in md

    def test_contains_horizons(self):
        predictions = {
            "1週間後": [{"impact": "大", "confidence": "高", "title": "予測A", "prediction": "内容A", "evidence": "根拠A"}],
            "1〜6ヶ月後": [],
            "1年後": [],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        assert "## 1週間後" in md
        assert "予測A" in md
        assert "内容A" in md

    def test_sorts_by_impact_and_confidence(self):
        # P2: evidence 空はレンダから除外される仕様に変更されたため、テストでも明示する
        predictions = {
            "1週間後": [
                {"impact": "小", "confidence": "低", "title": "低優先",
                 "prediction": "本文低", "evidence": "根拠低"},
                {"impact": "大", "confidence": "高", "title": "高優先",
                 "prediction": "本文高", "evidence": "根拠高"},
            ],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        pos_high = md.index("高優先")
        pos_low = md.index("低優先")
        assert pos_high < pos_low

    def test_contains_perspectives_section(self):
        perspectives = {"技術者": "技術分析内容", "経営者": "経営分析内容", "消費者": "消費者分析内容"}
        md = build_markdown_report([], {}, "2026-03-28 12:00:00", perspectives)
        assert "# 3視点分析" in md
        assert "## 技術者視点" in md
        assert "技術分析内容" in md

    def test_no_perspectives_when_empty(self):
        md = build_markdown_report([], {}, "2026-03-28 12:00:00")
        assert "3視点分析" not in md

    def test_empty_horizon_emits_fallback_note(self):
        """予測が1件もない horizon には明示的なフォールバック文を出力する（空殻プレースホルダ防止）"""
        predictions = {
            "1週間後": [],
            "1〜6ヶ月後": [{"impact": "大", "confidence": "高", "title": "実予測",
                           "prediction": "本文", "evidence": "根拠"}],
            "1年後": [],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        # 空 horizon にフォールバック文が出ていること
        assert "この時間軸の予測は今回生成されませんでした" in md
        # 「予測1」のような空殻は出ないこと
        assert "### 1. 予測1" not in md
        # 実予測は正常に描画されていること
        assert "## 1〜6ヶ月後" in md
        assert "実予測" in md

    def test_all_empty_items_filtered_out(self):
        """全フィールドが空の item は除外され、empty-horizon 扱いになる"""
        predictions = {
            "1週間後": [{}, {"impact": "中", "confidence": "中"}],  # title/prediction/evidence なし
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        # 中身のない item は描画されない
        assert "### 1. 予測1" not in md
        # フォールバック文が代わりに出る
        assert "この時間軸の予測は今回生成されませんでした" in md


class TestHasPredictionContent:
    def test_empty_dict_is_empty(self):
        assert _has_prediction_content({}) is False

    def test_only_impact_is_empty(self):
        # impact だけあっても実内容が無いので空扱い
        assert _has_prediction_content({"impact": "大", "confidence": "高"}) is False

    def test_title_only_is_content(self):
        assert _has_prediction_content({"title": "タイトル"}) is True

    def test_prediction_only_is_content(self):
        assert _has_prediction_content({"prediction": "内容"}) is True

    def test_evidence_only_is_content(self):
        assert _has_prediction_content({"evidence": "根拠"}) is True

    def test_whitespace_only_is_empty(self):
        assert _has_prediction_content({"title": "   ", "prediction": "\t\n"}) is False


class TestLoadExistingReport:
    """`_load_existing_today_report` の挙動: 4回/日バッチ運用のリカバリー基盤"""

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        import forecast_generate as fg
        monkeypatch.setattr(fg, "FORECASTS_DIR", tmp_path)
        result = fg._load_existing_today_report("2099-01-01")
        assert result["exists"] is False
        assert result["predictions"] == {}

    def test_parses_filled_and_empty_horizons(self, tmp_path, monkeypatch):
        """既存レポートから、中身ありの horizon は items を、空殻の horizon は除外して返す。"""
        import forecast_generate as fg
        monkeypatch.setattr(fg, "FORECASTS_DIR", tmp_path)

        md = """# 多視点ニュース分析・未来予測レポート

**生成日時:** 2026-04-22 06:00:00

---

# 今週の最重要ポイント

1. **ポイントA**
   *あなたへの影響:* なにか

---

# 未来予測

## 1週間後

### 1. 予測1

**影響度: 中 / 確信度: 中**

- **予測内容**：

> **根拠**:

## 1〜6ヶ月後

### 1. 実予測タイトル

**影響度: 大 / 確信度: 高**

- **予測内容**：実際の予測内容

> **根拠**: 参考ニュースA

## 1年後

### 1. 1年後の実予測

**影響度: 中 / 確信度: 中**

- **予測内容**：1年後の本文

> **根拠**: 参考ニュースB
"""
        (tmp_path / "report_2026-04-22.md").write_text(md, encoding="utf-8")
        result = fg._load_existing_today_report("2026-04-22")

        assert result["exists"] is True
        # 1週間後 は空殻 → predictions に入らない
        assert "1週間後" not in result["predictions"]
        # 1〜6ヶ月後 と 1年後 は中身あり → 入る
        assert len(result["predictions"]["1〜6ヶ月後"]) == 1
        assert result["predictions"]["1〜6ヶ月後"][0]["title"] == "実予測タイトル"
        assert result["predictions"]["1〜6ヶ月後"][0]["prediction"] == "実際の予測内容"
        assert result["predictions"]["1〜6ヶ月後"][0]["evidence"] == "参考ニュースA"
        assert result["predictions"]["1〜6ヶ月後"][0]["impact"] == "大"
        assert result["predictions"]["1〜6ヶ月後"][0]["confidence"] == "高"
        assert len(result["predictions"]["1年後"]) == 1

    def test_fallback_note_not_treated_as_prediction(self, tmp_path, monkeypatch):
        """`※ この時間軸の予測は今回生成されませんでした` 注記は predictions に含まれない。"""
        import forecast_generate as fg
        monkeypatch.setattr(fg, "FORECASTS_DIR", tmp_path)

        md = """**生成日時:** 2026-04-22 06:00:00

# 未来予測

## 1週間後

> ※ この時間軸の予測は今回生成されませんでした（LLM応答の解析に失敗した可能性があります）。

## 1〜6ヶ月後

### 1. 実予測

**影響度: 大 / 確信度: 高**

- **予測内容**：ちゃんと中身があります

> **根拠**: 参考ニュース
"""
        (tmp_path / "report_2026-04-22.md").write_text(md, encoding="utf-8")
        result = fg._load_existing_today_report("2026-04-22")
        # フォールバック注記だけの horizon は predictions に含まれない
        assert "1週間後" not in result["predictions"]
        # 実予測のある horizon は含まれる
        assert len(result["predictions"]["1〜6ヶ月後"]) == 1

    def test_placeholder_title_excluded_not_counted_as_real(self, tmp_path, monkeypatch):
        """'予測1' のような連番プレースホルダタイトルは real_title として扱わない。"""
        import forecast_generate as fg
        monkeypatch.setattr(fg, "FORECASTS_DIR", tmp_path)

        md = """**生成日時:** 2026-04-22 06:00:00

# 未来予測

## 1週間後

### 1. 予測1

**影響度: 中 / 確信度: 中**

- **予測内容**：中身あり予測

> **根拠**: 根拠あり
"""
        (tmp_path / "report_2026-04-22.md").write_text(md, encoding="utf-8")
        result = fg._load_existing_today_report("2026-04-22")
        # title が空扱いになっても prediction があるので保持される
        assert len(result["predictions"]["1週間後"]) == 1
        item = result["predictions"]["1週間後"][0]
        assert item["title"] == ""  # プレースホルダは空扱い
        assert item["prediction"] == "中身あり予測"


class TestCatLabels:
    """CAT_LABELS が sources.yaml の主要カテゴリを網羅していること"""

    def test_covers_core_categories(self):
        required = [
            "system", "manufacturing", "quality", "maintenance",
            "smart_factory", "policy", "decarbonization_ops",
            "security", "standards", "market", "ai", "dev",
        ]
        for cat_id in required:
            assert cat_id in CAT_LABELS, f"CAT_LABELS に {cat_id} がありません"

    def test_covers_additional_categories(self):
        additional = ["news", "industry", "company", "security_ot"]
        for cat_id in additional:
            assert cat_id in CAT_LABELS, f"CAT_LABELS に {cat_id} がありません"


class TestMinImportance:
    def test_min_importance_is_positive(self):
        assert MIN_IMPORTANCE > 0

    def test_min_importance_not_too_high(self):
        assert MIN_IMPORTANCE <= 50


class TestLooksEnglish:
    """英語残存検知: 予測フィールドの言語判定"""

    def test_pure_japanese_is_not_english(self):
        assert _looks_english("Microsoftが新サービスを発表") is False

    def test_pure_english_is_english(self):
        assert _looks_english("Microsoft releases new Azure service") is True

    def test_short_proper_noun_only_is_not_english(self):
        # 短い略語1つだけは固有名詞混入とみなす
        assert _looks_english("GPU価格が15%下がる") is False
        assert _looks_english("OpenAIの新モデル") is False

    def test_empty_is_not_english(self):
        assert _looks_english("") is False
        assert _looks_english(None) is False

    def test_two_short_words_not_english(self):
        # 3文字以下の単語は英単語カウントに入れない
        assert _looks_english("AI と IoT の連携") is False


class TestNormalizeEnum:
    """impact/confidence の英語値→日本語enum 正規化"""

    def test_japanese_passthrough(self):
        assert _normalize_enum("大", _IMPACT_MAP, "中") == "大"
        assert _normalize_enum("高", _CONFIDENCE_MAP, "中") == "高"

    def test_english_high_medium_low(self):
        assert _normalize_enum("High", _IMPACT_MAP, "中") == "大"
        assert _normalize_enum("Medium", _IMPACT_MAP, "中") == "中"
        assert _normalize_enum("Low", _IMPACT_MAP, "中") == "小"
        assert _normalize_enum("High", _CONFIDENCE_MAP, "中") == "高"
        assert _normalize_enum("Low", _CONFIDENCE_MAP, "中") == "低"

    def test_descriptive_english_uses_first_word(self):
        # "Lower latency for Asian customers" → 先頭"lower" → 小
        assert _normalize_enum("Lower latency for Asian customers", _IMPACT_MAP, "中") == "小"
        # "GPU market shift; AI workloads cheaper" → 先頭"gpu" → デフォルト
        assert _normalize_enum("GPU market shift; AI workloads cheaper", _IMPACT_MAP, "中") == "中"

    def test_unknown_returns_default(self):
        assert _normalize_enum("Unknown", _IMPACT_MAP, "中") == "中"
        assert _normalize_enum("", _IMPACT_MAP, "小") == "小"
        assert _normalize_enum(None, _IMPACT_MAP, "中") == "中"


class TestLocalizePredictionItem:
    """予測アイテムのローカライズ: enum正規化はLLM不要で動作確認"""

    def test_normalizes_enums_without_llm(self, monkeypatch):
        # _translate_to_ja は日本語のみなら呼ばれない
        item = {
            "title": "日本語のタイトル",
            "prediction": "日本語の予測内容",
            "evidence": "日本語の根拠",
            "impact": "High",
            "confidence": "Low",
        }
        out = _localize_prediction_item(item)
        assert out["impact"] == "大"
        assert out["confidence"] == "低"
        # 日本語フィールドは変更されない
        assert out["title"] == "日本語のタイトル"
        assert out["prediction"] == "日本語の予測内容"

    def test_translates_english_fields(self, monkeypatch):
        # _translate_to_ja を差し替えて LLM 呼び出しを回避
        import forecast_generate as fg
        calls = []

        def fake_translate(text):
            calls.append(text)
            return f"[訳]{text}"

        monkeypatch.setattr(fg, "_translate_to_ja", fake_translate)

        item = {
            "title": "Microsoft releases new Azure service",
            "prediction": "Microsoft will release new Azure service",
            "evidence": "Microsoft press release",
            "impact": "Medium",
            "confidence": "High",
        }
        out = fg._localize_prediction_item(item)
        # 3つの英文フィールドが翻訳されている
        assert out["title"].startswith("[訳]")
        assert out["prediction"].startswith("[訳]")
        assert out["evidence"].startswith("[訳]")
        # enum は正規化される
        assert out["impact"] == "中"
        assert out["confidence"] == "高"

    def test_non_dict_passthrough(self):
        # 想定外型はそのまま返す（防御）
        assert _localize_prediction_item("not a dict") == "not a dict"
        assert _localize_prediction_item(None) is None


class TestBuildNewsDigest:
    """build_news_digest の重要度フィルタリングテスト（in-memory SQLite使用）"""

    def _setup_db(self):
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                title TEXT,
                category TEXT,
                fetched_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE topic_articles (
                article_id INTEGER,
                topic_id INTEGER,
                is_representative INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE topic_insights (
                topic_id INTEGER PRIMARY KEY,
                summary TEXT,
                importance INTEGER
            )
        """)
        return conn, cur

    def test_excludes_low_importance_articles(self):
        conn, cur = self._setup_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # 重要度10の記事（除外されるべき）
        cur.execute("INSERT INTO articles VALUES (1, '低重要度記事', 'ai', ?)", (now,))
        cur.execute("INSERT INTO topic_articles VALUES (1, 1, 1)")
        cur.execute("INSERT INTO topic_insights VALUES (1, '要約', 10)")
        # 重要度80の記事（含まれるべき）
        cur.execute("INSERT INTO articles VALUES (2, '高重要度記事', 'ai', ?)", (now,))
        cur.execute("INSERT INTO topic_articles VALUES (2, 2, 1)")
        cur.execute("INSERT INTO topic_insights VALUES (2, '重要な要約', 80)")
        conn.commit()

        digest = build_news_digest(cur, hours=24, per_cat=5)
        assert "高重要度記事" in digest
        assert "低重要度記事" not in digest
        conn.close()

    def test_includes_articles_without_insights(self):
        """insight未生成の新着記事はデフォルト50扱いで含まれる"""
        conn, cur = self._setup_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO articles VALUES (1, '新着記事', 'ai', ?)", (now,))
        conn.commit()

        digest = build_news_digest(cur, hours=24, per_cat=5)
        assert "新着記事" in digest
        conn.close()

    def test_empty_when_no_recent_articles(self):
        conn, cur = self._setup_db()
        # 古い記事のみ
        cur.execute("INSERT INTO articles VALUES (1, '古い記事', 'ai', '2020-01-01 00:00:00')")
        conn.commit()

        digest = build_news_digest(cur, hours=24, per_cat=5)
        assert digest.strip() == ""
        conn.close()


class TestSafeTranslate:
    """T1: _safe_translate が翻訳失敗時に原文を維持することを確認"""

    def test_returns_original_when_translation_empty(self, monkeypatch):
        import forecast_generate as fg
        monkeypatch.setattr(fg, "_translate_to_ja", lambda x: "")
        assert fg._safe_translate("Microsoft releases Azure update") == "Microsoft releases Azure update"

    def test_returns_translated_when_non_empty(self, monkeypatch):
        import forecast_generate as fg
        monkeypatch.setattr(fg, "_translate_to_ja", lambda x: "Microsoftが更新をリリース")
        assert fg._safe_translate("Microsoft releases Azure update") == "Microsoftが更新をリリース"

    def test_empty_input_short_circuit(self):
        import forecast_generate as fg
        assert fg._safe_translate("") == ""
        assert fg._safe_translate("   ") == "   "


class TestBuildMarkdownReportTitleFallback:
    """T1: title 空時のフォールバック（prediction 先頭）と最終スキップ"""

    def test_uses_prediction_head_when_title_empty(self):
        predictions = {
            "1週間後": [
                {"impact": "中", "confidence": "中", "title": "",
                 "prediction": "AzureがアジアでIoTサブスクリプションを12%成長させる",
                 "evidence": "公式発表"}
            ],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        # 空タイトルが prediction 先頭で補完されている
        assert "### 1. AzureがアジアでIoTサブスクリプションを12%" in md or "### 1. AzureがアジアでIoT" in md
        # 「予測1」プレースホルダは出ない
        assert "### 1. 予測1" not in md

    def test_skips_when_title_and_prediction_both_empty(self):
        predictions = {
            "1週間後": [
                {"impact": "中", "confidence": "中", "title": "",
                 "prediction": "", "evidence": "根拠だけ"}
            ],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        # アイテムは描画されず、フォールバック文が出る
        assert "### 1." not in md or "この時間軸の予測は今回生成されませんでした" in md


class TestDedupeAcrossHorizons:
    """T5: rapidfuzz による horizon 跨ぎ重複除去"""

    def test_short_term_kept_long_term_removed(self):
        from forecast_generate import _dedupe_across_horizons, HORIZONS
        predictions = {
            "1週間後": [
                {"title": "Azure IoTのアジア成長", "prediction": "Azure IoTがアジア市場で12%成長する",
                 "subjects": ["Microsoft", "Asia"]},
            ],
            "1〜6ヶ月後": [
                # 短期側とほぼ同テーマ → 除去される想定
                {"title": "Azure IoTアジア市場拡大", "prediction": "Azure IoTがアジア市場で12%成長する見込み",
                 "subjects": ["Microsoft", "Asia"]},
            ],
            "1年後": [
                # 全く別テーマ → 残る
                {"title": "SMR需要が増加", "prediction": "米国のSMR需要が25%上昇する",
                 "subjects": ["US", "SMR"]},
            ],
        }
        result = _dedupe_across_horizons(predictions, HORIZONS, threshold=70)
        assert len(result["1週間後"]) == 1
        assert len(result["1〜6ヶ月後"]) == 0  # 短期と重複しているため除去
        assert len(result["1年後"]) == 1  # 別テーマなので残る

    def test_no_signature_items_pass_through(self):
        from forecast_generate import _dedupe_across_horizons, HORIZONS
        predictions = {
            "1週間後": [{"title": "", "prediction": "", "evidence": "x"}],
        }
        result = _dedupe_across_horizons(predictions, HORIZONS)
        # signature が空なら判定対象外で素通り
        assert len(result["1週間後"]) == 1


class TestShortTermLeakFilter:
    """T6: 短期 horizon に混入する中長期スパン語彙を generate_predictions が除去するか"""

    def test_regex_matches_long_term_keywords(self):
        from forecast_generate import _SHORT_TERM_LEAK_RE
        assert _SHORT_TERM_LEAK_RE.search("2027年までに普及する")
        assert _SHORT_TERM_LEAK_RE.search("中期的に投資が拡大")
        assert _SHORT_TERM_LEAK_RE.search("長期的な成長")
        assert _SHORT_TERM_LEAK_RE.search("数年後の市場")

    def test_regex_does_not_match_short_term(self):
        from forecast_generate import _SHORT_TERM_LEAK_RE
        assert not _SHORT_TERM_LEAK_RE.search("来週リリース予定")
        assert not _SHORT_TERM_LEAK_RE.search("2026年5月までに")


class TestValidateNumericClaims:
    """T10: 数値出典トレース（警告のみ・本文改変なし）"""

    def test_unverified_count_recorded(self):
        # P4: パーセンテージは予測の本質として検証対象外。社数・件数等のカウント値のみ対象。
        from forecast_generate import _validate_numeric_claims
        item = {
            "prediction": "Azure IoTがアジアで200社の採用を獲得する",
            "numeric_claims": [],
        }
        digest = "Microsoft press release: Gartner Magic Quadrant leader for Industrial IoT"
        out = _validate_numeric_claims(item, digest)
        assert "200社" in out.get("unverified_numerics", [])
        # 本文は改変されないこと
        assert out["prediction"] == "Azure IoTがアジアで200社の採用を獲得する"

    def test_percentage_not_recorded(self):
        # P4: パーセンテージは予測の推定値として許容され、unverified に入らない
        from forecast_generate import _validate_numeric_claims
        item = {
            "prediction": "Azure IoTがアジアで40%シェアを獲得する",
            "numeric_claims": [],
        }
        digest = "Microsoft press release"  # digest に 40% は無い
        out = _validate_numeric_claims(item, digest)
        assert "40%" not in out.get("unverified_numerics", [])

    def test_verified_count_not_recorded(self):
        from forecast_generate import _validate_numeric_claims
        item = {
            "prediction": "Aurora採用は200社に達する",
            "numeric_claims": [],
        }
        # digest に 200社 が含まれているので裏付けあり
        digest = "AWS Auroraの導入は既に200社を超えています"
        out = _validate_numeric_claims(item, digest)
        assert "unverified_numerics" not in out or "200社" not in out.get("unverified_numerics", [])

    def test_estimated_prefix_skips_validation(self):
        from forecast_generate import _validate_numeric_claims
        item = {
            "prediction": "Azure IoTが[推定] 100社で導入される",
            "numeric_claims": [{"value": "100社", "source": "[推定]"}],
        }
        digest = "Microsoft press release"
        out = _validate_numeric_claims(item, digest)
        # [推定] 宣言があるので unverified には入らない
        assert "100社" not in out.get("unverified_numerics", [])


class TestSmartTruncateForTitle:
    """P3: タイトル整形 (句読点優先で切る + ... 付与)"""

    def test_cuts_at_period(self):
        from forecast_generate import _smart_truncate_for_title
        s = "ブレント原油先物は2％上昇する。米国市場で続伸。"
        out = _smart_truncate_for_title(s, max_len=40)
        assert out == "ブレント原油先物は2％上昇する。"

    def test_falls_back_to_ellipsis_when_no_punct(self):
        from forecast_generate import _smart_truncate_for_title
        s = "a" * 60
        out = _smart_truncate_for_title(s, max_len=20)
        assert out.endswith("…")
        assert len(out) <= 21

    def test_keeps_short_text_intact(self):
        from forecast_generate import _smart_truncate_for_title
        s = "短いタイトル"
        assert _smart_truncate_for_title(s, max_len=40) == "短いタイトル"

    def test_empty_input(self):
        from forecast_generate import _smart_truncate_for_title
        assert _smart_truncate_for_title("") == ""
        assert _smart_truncate_for_title(None) == ""

    def test_japanese_period_dot(self):
        from forecast_generate import _smart_truncate_for_title
        s = "AIサービスがリリースされる. 来週初公開."
        out = _smart_truncate_for_title(s, max_len=40)
        assert out.endswith(".")


class TestIsTitleRedundant:
    """P3: title と prediction の冗長検知"""

    def test_identical_strings_redundant(self):
        from forecast_generate import _is_title_redundant
        s = "ブレント原油先物は来週までに2％上昇する見込みです。"
        assert _is_title_redundant(s, s)

    def test_title_is_prefix_of_prediction_redundant(self):
        from forecast_generate import _is_title_redundant
        t = "AWS Aurora採用が拡大"
        p = "AWS Aurora採用が拡大し、200社が導入する見込み"
        assert _is_title_redundant(t, p)

    def test_distinct_strings_not_redundant(self):
        from forecast_generate import _is_title_redundant
        t = "Azure IoT普及"
        p = "Microsoftが新しいAIエージェントを発表する"
        assert not _is_title_redundant(t, p)

    def test_empty_inputs_not_redundant(self):
        from forecast_generate import _is_title_redundant
        assert not _is_title_redundant("", "x")
        assert not _is_title_redundant("x", "")


class TestPredictionEmptyEvidenceFiltered:
    """P2: evidence 空のアイテムが build_markdown_report で除外される"""

    def test_skips_item_without_evidence(self):
        predictions = {
            "1週間後": [
                {"impact": "中", "confidence": "中", "title": "evidenceなし",
                 "prediction": "本文あり", "evidence": ""},
                {"impact": "中", "confidence": "中", "title": "evidenceあり",
                 "prediction": "本文", "evidence": "根拠あり"},
            ],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        assert "evidenceあり" in md
        assert "evidenceなし" not in md


class TestEstimatedBadgeLabel:
    """P4: ⚠[出典未確認数値あり] が 📊 [推定値あり] にニュートラル化された"""

    def test_badge_uses_neutral_label(self):
        predictions = {
            "1週間後": [
                {"impact": "中", "confidence": "中", "title": "テスト",
                 "prediction": "100社が導入する", "evidence": "根拠",
                 "unverified_numerics": ["100社"]},
            ],
        }
        md = build_markdown_report([], predictions, "2026-03-28 12:00:00")
        assert "📊 [推定値あり]" in md
        assert "⚠[出典未確認数値あり]" not in md


class TestAggregateTopicPerspectivesCategoryFilter:
    """P1: _aggregate_topic_perspectives がカテゴリ allowlist で絞り込む"""

    def _setup_db(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, category TEXT, fetched_at TEXT)")
        cur.execute("CREATE TABLE topic_articles (article_id INTEGER, topic_id INTEGER, is_representative INTEGER DEFAULT 0)")
        cur.execute("CREATE TABLE topic_insights (topic_id INTEGER PRIMARY KEY, summary TEXT, importance INTEGER, perspectives TEXT)")
        return conn, cur

    def test_news_category_excluded(self):
        import json as _json
        from forecast_generate import _aggregate_topic_perspectives
        from datetime import datetime, timezone
        conn, cur = self._setup_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # 事件系（news）と AI 系の topic を1件ずつ。news は除外されるはず。
        cur.execute("INSERT INTO articles VALUES (1, '発砲事件', 'news', ?)", (now,))
        cur.execute("INSERT INTO topic_articles VALUES (1, 1, 1)")
        cur.execute(
            "INSERT INTO topic_insights VALUES (1, '事件', 90, ?)",
            (_json.dumps({"engineer": "事件分析", "management": "事件管理", "consumer": "事件消費"}),),
        )
        cur.execute("INSERT INTO articles VALUES (2, 'AIニュース', 'ai', ?)", (now,))
        cur.execute("INSERT INTO topic_articles VALUES (2, 2, 1)")
        cur.execute(
            "INSERT INTO topic_insights VALUES (2, 'AI', 80, ?)",
            (_json.dumps({"engineer": "AI分析", "management": "AI管理", "consumer": "AI消費"}),),
        )
        conn.commit()

        result = _aggregate_topic_perspectives(cur, hours=24, top_n=8)
        # AI のコメントは含まれる
        assert any("AI分析" in c for c in result["engineer"])
        # 事件のコメントは含まれない
        assert not any("事件分析" in c for c in result["engineer"])
        conn.close()


class TestLocalizeAllowsNewFields:
    """T4: subjects / numeric_claims が _localize_prediction_item を通り抜けて保持されるか"""

    def test_subjects_list_preserved(self):
        from forecast_generate import _localize_prediction_item
        item = {
            "title": "テスト",
            "prediction": "テスト",
            "evidence": "テスト",
            "impact": "中",
            "confidence": "中",
            "subjects": ["Microsoft", "Asia"],
            "numeric_claims": [{"value": "12%", "source": "[推定]"}],
        }
        out = _localize_prediction_item(item)
        assert out["subjects"] == ["Microsoft", "Asia"]
        assert len(out["numeric_claims"]) == 1

    def test_subjects_string_normalized_to_list(self):
        from forecast_generate import _localize_prediction_item
        item = {"title": "x", "subjects": "Microsoft"}
        out = _localize_prediction_item(item)
        assert out["subjects"] == ["Microsoft"]

    def test_missing_new_fields_defaults_to_empty_list(self):
        from forecast_generate import _localize_prediction_item
        item = {"title": "x"}
        out = _localize_prediction_item(item)
        assert out["subjects"] == []
        assert out["numeric_claims"] == []
