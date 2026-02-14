from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

import yaml

from collect import load_feed_list, normalize_url


HEURISTIC_NON_FEED_PATH_SEGMENTS = {
    "about",
    "company",
    "contact",
    "careers",
    "products",
    "pricing",
    "docs",
    "documentation",
    "support",
}
HEURISTIC_FEED_HINTS = {
    "rss",
    "feed",
    "atom",
    "xml",
    ".rdf",
}


@dataclass(frozen=True)
class LintIssue:
    severity: str
    code: str
    message: str


def _looks_non_feed_url(url: str) -> bool:
    lower_url = url.lower()
    if any(h in lower_url for h in HEURISTIC_FEED_HINTS):
        return False

    path = urlsplit(url).path.lower().strip("/")
    if not path:
        return True

    segments = [s for s in path.split("/") if s]
    return any(seg in HEURISTIC_NON_FEED_PATH_SEGMENTS for seg in segments)


def lint_feed_list(feeds: Iterable[dict]) -> list[LintIssue]:
    feeds = list(feeds)
    issues: list[LintIssue] = []

    by_exact: dict[str, list[dict]] = defaultdict(list)
    by_normalized: dict[str, list[dict]] = defaultdict(list)

    for feed in feeds:
        url = feed["url"]
        by_exact[url].append(feed)
        by_normalized[normalize_url(url)].append(feed)

        if url.lower().startswith("http://"):
            issues.append(
                LintIssue(
                    severity="warning",
                    code="http-url",
                    message=f"HTTP URL detected (prefer HTTPS): {url}",
                )
            )

        if _looks_non_feed_url(url):
            issues.append(
                LintIssue(
                    severity="warning",
                    code="non-rss-heuristic",
                    message=f"URL may not be a feed endpoint: {url}",
                )
            )

    for url, items in by_exact.items():
        if len(items) > 1:
            contexts = ", ".join(f"{item.get('source')}:{item.get('category')}" for item in items)
            issues.append(
                LintIssue(
                    severity="error",
                    code="duplicate-exact-url",
                    message=f"Duplicate feed URL: {url} ({contexts})",
                )
            )

    for nurl, items in by_normalized.items():
        exact_urls = {item["url"] for item in items}
        if len(items) > 1 and len(exact_urls) > 1:
            contexts = ", ".join(f"{item.get('source')}:{item.get('category')} => {item.get('url')}" for item in items)
            issues.append(
                LintIssue(
                    severity="error",
                    code="duplicate-normalized-url",
                    message=f"Normalized duplicate URL: {nurl} ({contexts})",
                )
            )

    return issues


def run(config_path: Path) -> int:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    feeds = load_feed_list(cfg)
    issues = lint_feed_list(feeds)

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    if issues:
        print("Feed lint report")
        print("=" * 64)
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN"
            print(f"[{tag}] {issue.code}: {issue.message}")
        print("=" * 64)

    print(f"Checked {len(feeds)} feeds: {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors:
        print("Feed lint failed due to error-level issues.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint sources.yaml feed configuration")
    parser.add_argument("--config", default="src/sources.yaml", help="Path to feed config yaml")
    args = parser.parse_args()
    return run(Path(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
