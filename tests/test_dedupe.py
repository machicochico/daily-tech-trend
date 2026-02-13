from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dedupe import (
    category_threshold,
    normalize_title,
    normalize_url,
    _composite_score,
)


def test_normalize_title_standardizes_case_symbols_and_spacing():
    title = "  OpenAI、GPT-5  発表!!!  "
    assert normalize_title(title) == "openai gpt 5 発表"


def test_normalize_url_strips_tracking_and_www():
    url = "https://www.example.com/path/?utm_source=x&a=1#frag"
    assert normalize_url(url) == "https://example.com/path?a=1"


def test_category_threshold_uses_default_for_unknown():
    assert category_threshold("security") == 90
    assert category_threshold("unknown") == 91


def test_composite_score_prefers_closer_title_and_url():
    score_similar = _composite_score(
        "openai launches new model",
        "openai launches new model today",
        "https://example.com/news/openai-model",
        "https://example.com/news/openai-model",
    )
    score_different = _composite_score(
        "openai launches new model",
        "apple releases new iphone",
        "https://example.com/news/openai-model",
        "https://another.com/posts/iphone",
    )
    assert score_similar > score_different
