from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import render_main


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_render_source_contains_opinion_page_links() -> None:
    source = _read("src/render_main.py")
    assert '/daily-tech-trend/opinion/' in source
    assert '意見（お試し版）' in source


def test_opinion_length_is_around_400_chars() -> None:
    item = {
        "summary": "新しい認証基盤の導入計画が公開された。",
        "perspectives": {
            "engineer": "段階移行計画と切り戻し条件を先に定義する",
            "management": "移行コストと停止リスクを比較し意思決定する",
            "consumer": "アカウント影響の告知とFAQ整備を優先する",
        },
        "key_points": ["対象ユーザーは段階的に移行", "旧認証は一定期間併用"],
        "url": "https://example.com/post",
    }

    got = render_main._build_trial_opinion(item, "engineer")
    assert 360 <= len(got) <= 440


def test_opinion_page_exists() -> None:
    assert Path("docs/opinion/index.html").exists()


def test_pick_role_articles_returns_requested_count() -> None:
    items = [
        {"id": 1, "importance": 5, "title": "AI platform", "summary": "AI model update", "key_points": [], "tags": ["ai"], "perspectives": {"engineer": ""}, "dt": "2026-01-01 00:00:00"},
        {"id": 2, "importance": 9, "title": "security incident", "summary": "service outage", "key_points": [], "tags": ["security"], "perspectives": {"engineer": "impact analysis"}, "dt": "2026-01-02 00:00:00"},
        {"id": 3, "importance": 8, "title": "market moves", "summary": "new regulation", "key_points": [], "tags": ["policy"], "perspectives": {"engineer": ""}, "dt": "2026-01-03 00:00:00"},
        {"id": 4, "importance": 7, "title": "api change", "summary": "cloud migration", "key_points": [], "tags": ["cloud"], "perspectives": {"engineer": "migration plan"}, "dt": "2026-01-04 00:00:00"},
    ]

    picked = render_main._pick_role_articles(items, "engineer", max_items=3)
    assert len(picked) == 3
    assert picked[0]["id"] == 2


def test_build_combined_opinion_length_range() -> None:
    picked = [
        {"summary": "クラウド移行で認証基盤の再設計が必要になった。"},
        {"summary": "障害対応の手順を標準化し、運用負荷を下げる検討が進む。"},
        {"summary": "利用者向け通知の改善が継続率と信頼性に影響している。"},
    ]

    text = render_main._build_combined_opinion("engineer", picked)
    assert 260 <= len(text) <= 420


def test_select_role_articles_reduces_overlap() -> None:
    items = [
        {"id": 1, "importance": 10, "title": "security patch", "summary": "zero-day response", "key_points": [], "tags": ["security"], "category": "security", "perspectives": {"engineer": "fix"}, "dt": "2026-01-04 00:00:00"},
        {"id": 2, "importance": 9, "title": "quarter earnings", "summary": "margin and strategy", "key_points": [], "tags": ["market"], "category": "company", "perspectives": {"management": "decision"}, "dt": "2026-01-03 00:00:00"},
        {"id": 3, "importance": 8, "title": "consumer app update", "summary": "pricing and support", "key_points": [], "tags": ["consumer"], "category": "news", "perspectives": {"consumer": "impact"}, "dt": "2026-01-02 00:00:00"},
        {"id": 4, "importance": 7, "title": "policy reform", "summary": "regulation for industry", "key_points": [], "tags": ["policy"], "category": "policy", "perspectives": {}, "dt": "2026-01-01 00:00:00"},
    ]
    selected = render_main._select_role_articles(items, ["engineer", "management", "consumer"], max_items=2)
    top_ids = {role: selected[role][0]["id"] for role in selected if selected[role]}
    assert len(set(top_ids.values())) == len(top_ids)


def test_build_combined_opinion_uses_claim_evidence_impact() -> None:
    picked = [
        {"summary": "クラウド移行で認証基盤の再設計が必要になった。", "source": "Tech Media"},
        {"summary": "障害対応の手順を標準化し、運用負荷を下げる検討が進む。", "source": "Ops Journal"},
        {"summary": "利用者向け通知の改善が継続率と信頼性に影響している。", "source": "Product News"},
    ]
    engineer = render_main._build_combined_opinion("engineer", picked)

    assert "主張:" in engineer
    assert "根拠:" in engineer
    assert "影響:" in engineer
    assert "第1に" not in engineer


def test_fit_text_length_trims_on_sentence_boundary() -> None:
    long_text = "。".join([f"文{i}" for i in range(1, 40)]) + "。"
    got = render_main._fit_text_length(long_text, target=120, min_len=100, max_len=140)
    assert len(got) <= 140
    assert got.endswith("。")


def test_extract_clear_point_prefers_title_and_is_short() -> None:
    article = {
        "title": "これは非常に長いタイトルですが、途中で切れて意味不明にならないように短くしたいタイトルです",
        "summary": "summary text",
    }
    point = render_main._extract_clear_point(article)
    assert len(point) <= 73
    assert point.startswith("これは非常に長いタイトル")


def test_role_filter_excludes_weather_and_incidents_for_management_consumer() -> None:
    weather = {"id": 1, "title": "関東で大雨", "summary": "天気の急変", "category": "news", "tags": ["weather"]}
    crime = {"id": 2, "title": "広島で殺人事件", "summary": "事件の捜査", "category": "news", "tags": ["incident"]}
    business = {"id": 3, "title": "半導体投資を拡大", "summary": "サプライチェーン強化", "category": "industry", "tags": ["投資"]}

    assert not render_main._is_role_compatible(weather, "management")
    assert not render_main._is_role_compatible(crime, "consumer")
    assert render_main._is_role_compatible(business, "management")


def test_extract_conclusion_line_prefers_claim_sentence() -> None:
    opinion = "主張: 結論文です。根拠: 事実A。影響: 次の一手。"
    assert render_main._extract_conclusion_line(opinion) == "結論文です。"


def test_opinion_template_is_collapsed_by_default() -> None:
    source = _read("src/render_main.py")
    assert "詳細を読む（{{ role.label }}の意見約{{ role.full_text_len }}文字・ニュースソース）" in source
    assert '<details class="insight" open>' not in source


def test_extract_recommended_action_line_prefers_impact_sentence() -> None:
    opinion = "主張: 結論。根拠: 事実。影響: 段階導入で検証を進める。"
    assert render_main._extract_recommended_action_line(opinion) == "段階導入で検証を進める。"


def test_opinion_template_has_view_mode_switch_and_comparison_labels() -> None:
    source = _read("src/render_main.py")
    assert "縦スクロール表示" in source
    assert "比較表示（タブ/3カラム）" in source
    assert "立場別の結論サマリ" in source
    assert "<h4>結論</h4>" in source
    assert "<h4>主要根拠</h4>" in source
    assert "<h4>推奨アクション</h4>" in source


def test_opinion_template_has_anchor_toc_and_scroll_helpers() -> None:
    source = _read("src/render_main.py")
    assert 'aria-label="立場別目次"' in source
    assert 'href="#{{ role.anchor_id }}"' in source
    assert '"management": "executive"' in source
    assert 'class="sticky-mini-nav"' in source
    assert "window.scrollTo({ top: 0, behavior: 'smooth' });" in source


def test_opinion_summary_shows_top_evidence_tags() -> None:
    source = _read("src/render_main.py")
    assert "根拠 {{ loop.index }}:" in source
    assert '"top_evidence_tags": _build_top_evidence_tags(picked, limit=2)' in source


def test_opinion_news_sources_show_timestamps_and_reason() -> None:
    source = _read("src/render_main.py")
    assert "公開日時:" in source
    assert "取得元時刻:" in source
    assert "重要度理由:" in source


def test_opinion_template_has_role_discussion_block() -> None:
    source = _read("src/render_main.py")
    assert "立場間ディスカッション（仕様検討）" in source
    assert "{{ pair.from }}＞{{ pair.to }}" in source
    assert '"discussion_pairs"' in source


def test_build_role_discussion_generates_cross_role_pairs() -> None:
    sections = [
        {"role": "engineer", "summary": "監視設計を先に固定する。", "recommendation": "段階導入する。"},
        {"role": "management", "summary": "投資優先順位を整理する。", "recommendation": "四半期計画を更新する。"},
        {"role": "consumer", "summary": "利用条件を比較する。", "recommendation": "設定変更を今週中に実行する。"},
    ]

    discussions = render_main._build_role_discussion(sections)

    assert set(discussions.keys()) == {"engineer", "management", "consumer"}
    assert len(discussions["engineer"]) == 4
    assert discussions["engineer"][0]["from"] == "技術者"
    assert discussions["engineer"][0]["to"] == "経営者"
    assert "仕様の確定タイミングと受け入れ条件" in discussions["engineer"][0]["text"]
    assert discussions["management"][0]["from"] == "経営者"


def test_build_opinion_body_sections_splits_labels() -> None:
    opinion = "主張: 結論。根拠: 事実A。根拠: 事実B。影響: 次の一手。"
    sections = render_main._build_opinion_body_sections(opinion)
    assert [sec["label"] for sec in sections] == ["主張", "根拠", "根拠 2", "影響"]
    assert sections[0]["text"] == "結論。"


def test_build_opinion_body_sections_fallback_for_unlabelled_text() -> None:
    sections = render_main._build_opinion_body_sections("ラベルのない文章です。")
    assert sections == [{"label": "本文", "text": "ラベルのない文章です。"}]
