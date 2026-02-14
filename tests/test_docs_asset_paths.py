from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_docs_root_uses_root_relative_assets() -> None:
    html = _read("docs/index.html")
    assert 'href="./assets/css/common.css"' in html
    assert 'src="./assets/js/common.js"' in html
    assert 'href="../assets/css/common.css"' not in html
    assert 'src="../assets/js/common.js"' not in html


def test_docs_news_uses_parent_relative_assets() -> None:
    html = _read("docs/news/index.html")
    assert 'href="../assets/css/common.css"' in html
    assert 'src="../assets/js/common.js"' in html


def test_render_source_sets_root_page_assets_to_root_relative() -> None:
    source = _read("src/render_main.py")
    assert 'common_css_href="./assets/css/common.css"' in source
    assert 'common_js_src="./assets/js/common.js"' in source
