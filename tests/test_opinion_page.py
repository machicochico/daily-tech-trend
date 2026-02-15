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


def test_build_combined_opinion_includes_role_specific_tone() -> None:
    picked = [
        {"summary": "クラウド移行で認証基盤の再設計が必要になった。"},
        {"summary": "障害対応の手順を標準化し、運用負荷を下げる検討が進む。"},
        {"summary": "利用者向け通知の改善が継続率と信頼性に影響している。"},
    ]
    engineer = render_main._build_combined_opinion("engineer", picked)
    management = render_main._build_combined_opinion("management", picked)
    consumer = render_main._build_combined_opinion("consumer", picked)

    assert "設計レビュー" in engineer
    assert "経営判断" in management
    assert "生活者" in consumer
