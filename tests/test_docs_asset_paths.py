from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_render_sources() -> str:
    """render_main.py と外部化された src/templates/*.html を連結して返す。

    render_main.py のHTML文字列は段階的にテンプレート外部化されており
    (PORTAL_HTML/NEWS_HTML/HTML/OPS_HTML/FORECAST_HTML/FORECAST_HITS_HTML)、
    ナビゲーション等の共通マークアップは外部化先のテンプレートファイル側にある。
    """
    parts = [_read("src/render_main.py")]
    for template in Path("src/templates").glob("*.html"):
        parts.append(template.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_render_source_uses_absolute_project_asset_paths() -> None:
    source = _read("src/render_main.py")
    assert 'def build_asset_paths(base_path: str = "/daily-tech-trend/")' in source
    assert 'normalized_base = f"/{base_path.strip(\'/\')}/"' in source
    assert 'f"{normalized_base}assets/css/common.css"' in source
    assert 'f"{normalized_base}assets/js/common.js"' in source


def test_render_source_uses_common_asset_builder_for_all_pages() -> None:
    source = _read("src/render_main.py")
    assert 'news_assets = build_asset_paths()' in source
    assert 'tech_sub_assets = build_asset_paths()' in source
    assert 'tech_root_assets = build_asset_paths()' in source
    assert 'ops_assets = build_asset_paths()' in source


def test_navigation_contains_ops_page_link() -> None:
    source = _read_render_sources()
    assert '/daily-tech-trend/ops/' in source


def test_gitignore_allows_generated_pages_publish() -> None:
    source = _read(".gitignore")
    for entry in (
        "!docs/ops/",
        "!docs/news/",
        "!docs/tech/",
        "!docs/forecast/",
        "!docs/topic/",
        "!docs/entity/",
        "!docs/diff/",
        "!docs/exec/",
        "!docs/api/",
        "!docs/search-index.json",
        "!docs/sitemap.xml",
        "!docs/feed.xml",
    ):
        assert entry in source, f"missing gitignore allow entry: {entry}"


def test_ops_page_exists() -> None:
    assert Path("docs/ops/index.html").exists()
