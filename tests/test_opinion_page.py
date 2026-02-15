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
