"""thread.py のユニットテスト"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thread import normalize_title, make_topic_key, find_best_topic


class TestNormalizeTitle:
    def test_removes_brackets(self):
        assert "[update]" not in normalize_title("[Update] New Release v2.0")

    def test_removes_parentheses(self):
        assert "(beta)" not in normalize_title("Feature (beta) Released")

    def test_keeps_japanese(self):
        result = normalize_title("新しいAI技術の発表について")
        assert "新しい" in result
        assert "技術" in result

    def test_lowercases(self):
        result = normalize_title("OpenAI GPT-5 RELEASED")
        assert "openai" in result

    def test_collapses_whitespace(self):
        result = normalize_title("a   b   c")
        assert "  " not in result


class TestMakeTopicKey:
    def test_truncates_at_120(self):
        long_title = "a" * 200
        assert len(make_topic_key(long_title)) == 120

    def test_short_title_unchanged(self):
        assert make_topic_key("short title") == "short title"


class TestFindBestTopic:
    def test_returns_match_above_threshold(self):
        candidates = {
            ("tech", "", "ai"): [
                (1, "python machine learning framework", "Python ML Framework"),
            ]
        }
        tid, score = find_best_topic(
            "python machine learning framework release",
            "tech", "", "ai", candidates,
        )
        assert tid == 1
        assert score >= 88

    def test_returns_none_for_low_similarity(self):
        candidates = {
            ("tech", "", "ai"): [
                (1, "python machine learning framework", "Python ML Framework"),
            ]
        }
        tid, score = find_best_topic(
            "completely unrelated topic about cooking recipes",
            "tech", "", "ai", candidates,
        )
        assert tid is None

    def test_returns_none_for_empty_candidates(self):
        tid, score = find_best_topic("some title", "tech", "", "ai", {})
        assert tid is None
