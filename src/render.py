"""Compatibility wrappers for the refactored rendering modules."""

from render_main import (
    fmt_date,
    main as _main_impl,
    render_news_pages as _render_news_pages_impl,
    render_news_region_page as _render_news_region_page_impl,
)
from render_models import (
    build_categories_fallback as _build_categories_fallback_impl,
    ensure_category_coverage as _ensure_category_coverage_impl,
    load_categories_from_yaml as _load_categories_from_yaml_impl,
    safe_json_list as _safe_json_list_impl,
    safe_json_obj as _safe_json_obj_impl,
)
from render_queries import (
    count_news_recent_48h as _count_news_recent_48h_impl,
    fetch_news_articles as _fetch_news_articles_impl,
    fetch_news_articles_by_category as _fetch_news_articles_by_category_impl,
)


def _safe_json_list(s):
    return _safe_json_list_impl(s)


def _safe_json_obj(s):
    return _safe_json_obj_impl(s)


def load_categories_from_yaml():
    return _load_categories_from_yaml_impl()


def build_categories_fallback(cur):
    return _build_categories_fallback_impl(cur)


def ensure_category_coverage(cur, categories):
    return _ensure_category_coverage_impl(cur, categories)


def fetch_news_articles(cur, region: str, limit: int = 60):
    return _fetch_news_articles_impl(cur, region, limit)


def fetch_news_articles_by_category(cur, region: str, category: str, limit: int = 40):
    return _fetch_news_articles_by_category_impl(cur, region, category, limit)


def count_news_recent_48h(cur, region: str, category: str, cutoff_dt: str) -> int:
    return _count_news_recent_48h_impl(cur, region, category, cutoff_dt)


def render_news_region_page(cur, region, limit_each=30, cutoff_dt=None):
    return _render_news_region_page_impl(cur, region, limit_each=limit_each, cutoff_dt=cutoff_dt)


def render_news_pages(out_dir, generated_at: str, cur) -> None:
    return _render_news_pages_impl(out_dir, generated_at, cur)


def main():
    return _main_impl()


if __name__ == "__main__":
    main()
