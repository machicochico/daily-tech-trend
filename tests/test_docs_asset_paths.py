from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
    assert 'opinion_assets = build_asset_paths()' in source


def test_navigation_contains_ops_page_link() -> None:
    source = _read("src/render_main.py")
    assert '/daily-tech-trend/ops/' in source
    assert '/daily-tech-trend/opinion/' in source


def test_gitignore_allows_ops_page_publish() -> None:
    source = _read(".gitignore")
    assert "!docs/ops/" in source
    assert "!docs/ops/index.html" in source
    assert "!docs/opinion/" in source
    assert "!docs/opinion/index.html" in source


def test_ops_page_exists() -> None:
    assert Path("docs/ops/index.html").exists()
