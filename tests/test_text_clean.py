from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from text_clean import clean_for_html, clean_json_like, clean_text


def test_clean_text_nfkc_and_invisible_and_control_removed():
    raw = "ＡＢＣ\u200b\u200c\u200d\ufeff\x00\x1f"
    assert clean_text(raw) == "ABC"


def test_clean_for_html_unescapes_once_for_double_escape_avoidance():
    assert clean_for_html("A &amp;amp; B") == "A &amp; B"


def test_clean_json_like_recursively_cleans_strings():
    data = {"ｋｅｙ\u200b": ["Ａ", {"inner": "A&amp;amp;B\x00"}]}
    assert clean_json_like(data) == {"key": ["A", {"inner": "A&amp;B"}]}
