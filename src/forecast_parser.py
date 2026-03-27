# src/forecast_parser.py
"""未来予測レポート(Markdown)を構造化データにパースする"""

import re
from dataclasses import dataclass, field


@dataclass
class ForecastReport:
    """パース済み未来予測レポート"""
    report_date: str = ""
    executive_summary: str = ""
    predictions: dict = field(default_factory=dict)   # {"1週間後": md, ...}
    checked_report: str = ""
    perspectives: dict = field(default_factory=dict)   # {"技術者": md, ...}
    appendix_factcheck: str = ""
    appendix_news: str = ""
    raw_markdown: str = ""


# --- セクション見出しのキーワード ---
_SECTION_PATTERNS = [
    ("executive_summary", re.compile(r"^#\s+.*最重要ポイント", re.MULTILINE)),
    ("predictions",       re.compile(r"^#\s+未来予測",        re.MULTILINE)),
    ("checked_report",    re.compile(r"^#\s+検証済み予測",     re.MULTILINE)),
    ("perspectives",      re.compile(r"^#\s+3視点分析",       re.MULTILINE)),
    ("appendix_fc",       re.compile(r"^#\s+付録A",           re.MULTILINE)),
    ("appendix_news",     re.compile(r"^#\s+付録B",           re.MULTILINE)),
]

_HORIZON_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)
_PERSPECTIVE_RE = re.compile(r"^##\s+(技術者|経営者|消費者)視点", re.MULTILINE)


def _split_by_h1(text: str) -> list[tuple[str, str, int]]:
    """H1見出しで分割し [(name, content, start_pos), ...] を返す"""
    parts = []
    pattern = re.compile(r"^(#\s+.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        heading = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((heading, text[start:end].strip(), m.start()))
    return parts


def _extract_date(text: str) -> str:
    """**生成日時:** YYYY-MM-DD HH:MM:SS から日付を抽出"""
    m = re.search(r"\*\*生成日時:\*\*\s*(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else ""


def _split_predictions(text: str) -> dict[str, str]:
    """未来予測セクションを時間軸ごとに分割"""
    result = {}
    matches = list(_HORIZON_RE.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[key] = text[start:end].strip()
    return result


def _split_perspectives(text: str) -> dict[str, str]:
    """3視点分析セクションを視点ごとに分割"""
    result = {}
    matches = list(_PERSPECTIVE_RE.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[key] = text[start:end].strip()
    return result


def parse_forecast_markdown(md_text: str) -> ForecastReport:
    """Markdownレポートを構造化データに変換する

    見出しが見つからない場合はraw_markdownにフォールバック。
    """
    report = ForecastReport(raw_markdown=md_text)
    report.report_date = _extract_date(md_text)

    sections = _split_by_h1(md_text)
    if not sections:
        return report

    section_map: dict[str, str] = {}
    for heading, content, _ in sections:
        for key, pat in _SECTION_PATTERNS:
            if pat.match(heading):
                section_map[key] = content
                break

    report.executive_summary = section_map.get("executive_summary", "")
    report.checked_report = section_map.get("checked_report", "")
    report.appendix_factcheck = section_map.get("appendix_fc", "")
    report.appendix_news = section_map.get("appendix_news", "")

    # 未来予測を時間軸ごとに分割
    pred_raw = section_map.get("predictions", "")
    if pred_raw:
        report.predictions = _split_predictions(pred_raw)

    # 3視点を視点ごとに分割
    persp_raw = section_map.get("perspectives", "")
    if persp_raw:
        report.perspectives = _split_perspectives(persp_raw)

    return report
