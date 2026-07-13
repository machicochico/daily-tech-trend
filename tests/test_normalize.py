"""normalize.py のユニットテスト"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from normalize import normalize


class TestNormalize:
    def test_lowercases_netloc(self):
        result = normalize("https://WWW.Example.COM/path")
        assert "www.example.com" in result

    def test_strips_trailing_slash(self):
        result = normalize("https://example.com/path/")
        assert result.endswith("/path")

    def test_removes_query_and_fragment(self):
        result = normalize("https://example.com/page?q=1&r=2#section")
        assert "?" not in result
        assert "#" not in result

    def test_preserves_scheme(self):
        result = normalize("http://example.com/page")
        assert result.startswith("http://")

    def test_handles_empty_path(self):
        result = normalize("https://example.com")
        assert result == "https://example.com"
