# src/render.py
from __future__ import annotations
import os
import re

import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml
from jinja2 import Template, Environment, FileSystemLoader
from datetime import datetime, timedelta, timezone

from db import connect
from text_clean import clean_for_html, clean_json_like

from typing import Any, List
import logging
import time

# 外部化したJinja2テンプレート（src/templates/）を読み込むためのEnvironment
# render_main.py の巨大インラインHTML文字列を段階的にテンプレートファイルへ移す一環
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))

# レンダリング中の非致命エラーを集計するためのグローバルリスト
# 各要素は (section, error_message) のタプル
_render_errors: list[tuple[str, str]] = []

# logging は既定で WARNING 以上を stderr に出す。コード全体で共用する。
_logger = logging.getLogger("render_main")
if not _logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


def _log_render_error(section: str, err: BaseException | str, *, level: str = "warning") -> None:
    """レンダリング中の非致命エラーを統一ルートで記録する。

    section: どの処理箇所で発生したかを示すラベル（例: "news.fetch", "ops.feed_health"）
    err: 例外または文字列
    level: "debug" | "info" | "warning" | "error"（既定 warning）
    """
    msg = f"{section}: {err}" if err else section
    level_fn = getattr(_logger, level, _logger.warning)
    # 例外オブジェクトならスタックトレースも出す
    if isinstance(err, BaseException):
        _logger.log(
            getattr(logging, level.upper(), logging.WARNING),
            msg,
            exc_info=True,
        )
    else:
        level_fn(msg)
    _render_errors.append((section, str(err)))


def fmt_date(s):
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z",""))
        return dt.astimezone(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M")
    except (ValueError, TypeError, OSError):
        return str(s)[:16]

def _now_sec():
    return time.perf_counter()


def build_asset_paths(base_path: str = "/daily-tech-trend/") -> dict[str, str]:
    """Return absolute asset paths under the GitHub Pages project base path."""
    normalized_base = f"/{base_path.strip('/')}/"
    return {
        "common_css_href": f"{normalized_base}assets/css/common.css",
        "common_js_src": f"{normalized_base}assets/js/common.js",
        "nav_prefix": normalized_base,
    }

COMMON_CSS = r"""
:root{
  /* Base */
  --bg: #fff;
  --panel: #f9fafb;
  --text-main: #1f2937;
  --text-sub: #6b7280;
  --border: #e5e7eb;

  /* Accent */
  --accent: #2563eb;
  --accent-soft: #dbeafe;

  /* Status */
  --new: #dc2626;
  --new-soft: #fee2e2;

  --important: #f59e0b;
  --important-soft: #fef3c7;
}
body{
  background:var(--bg);
  color:var(--text-main);
}
h1{margin:0 0 10px}
h2{margin:22px 0 10px}
.meta{color:var(--text-sub);font-size:12px;margin:6px 0 14px}
.nav{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 18px}
.nav a{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:6px 10px;text-decoration:none;color:#111}
.nav a.active{border-color:#333;font-weight:700}
.meta,.small{
  color:var(--text-sub);
}

.card{
  background:var(--panel);
  border:1px solid var(--border);
}

.badge{
  border:1px solid var(--border);
  color:var(--text-main);
}
.badge.recent{
  background:var(--new-soft);
  color:var(--new);
  border-color:var(--new);
  font-weight:700;
}
.btn{padding:6px 10px;border:1px solid var(--border);border-radius:10px;background:var(--bg);cursor:pointer;display:inline-block;text-decoration:none}
.btn:hover{background:var(--panel)}
ul{margin:0;padding-left:18px}
li{margin:10px 0}
a{color:inherit}
a{
  color:inherit;
  text-decoration:none;
}

a:hover{
  color:var(--accent);
}

.nav a.active{
  color:var(--accent);
  border-color:var(--accent);
  font-weight:700;
}

"""
TECH_EXTRA_CSS = r"""
/* techの箱・構造を定義している部分をここへ集約 */
.summary-card, .topbox, .top-col, .insight{
  background:#fafafa;
  border:1px solid var(--border);
  border-radius:12px;
  padding:12px 14px;
}
.top-col{ background:var(--bg); }

/* techの見出し間隔・小文字 */
.small{color:#666;font-size:12px}
.badge{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 8px;font-size:12px;color:#444;margin-left:6px}

/* もしtechにタグの見た目があるなら寄せる */
.tag{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 8px;font-size:12px;color:#444;margin-left:6px}


     /* --- UX改善①: 上部サマリー + 横断TOP --- */
    .summary-card{background:#fafafa;border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin:10px 0 14px}
    .summary-title{font-weight:800;font-size:16px;margin:0 0 6px}
    .summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:8px}
    .summary-item .k{color:#666;font-size:11px}
    .summary-item .v{font-size:13px;font-weight:650}

    .top-zone{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:10px 0 18px}
    .top-col{background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:10px 12px}
    .top-col h3{margin:0 0 8px;font-size:14px}
    .top-list{margin:0;padding-left:18px}
    .mini{color:#666;font-size:12px;margin-top:2px}
    .source-table{width:100%;border-collapse:collapse;font-size:13px}
    .source-table th,.source-table td{padding:6px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
    .source-table th.num,.source-table td.num{text-align:right;white-space:nowrap}
    .warn-text{color:#b91c1c;font-weight:700}
    .metric-note{margin:6px 0 10px;font-size:12px;color:#4b5563;line-height:1.6}

    .quick-controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:10px}
    #q{padding:6px 10px;border:1px solid var(--border);border-radius:10px;min-width:260px}
    .btn{padding:6px 10px;border:1px solid var(--border);border-radius:10px;background:var(--bg);cursor:pointer}

    .badge.hot{font-weight:800}
    .badge.new{border-style:dashed}

   .badge.imp{
      background:var(--important-soft);
      color:var(--important);
      border-color:var(--important);
    }
    .imp-2{border-color:#6c6}
    .imp-1{border-color:#9ad}
    .imp-0{border-color:#ccc}

    .category-section{margin-top:18px}
    .category-header{display:flex;align-items:center;gap:10px}
    .category-body{margin-top:8px}
    .category-section.collapsed .category-body{display:none}
    
    /* ===== Mobile-first overrides ===== */
    h1{font-size:26px}
    h2{font-size:18px}

    .summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
    .top-zone{grid-template-columns:1fr}
    .top-list{padding-left:18px}
    .top-item, .topic-row{margin:10px 0}

    /* 長いタイトル対策（はみ出し防止） */
    .topic-link, a{
      display:inline;
      overflow-wrap:anywhere;
      word-break:break-word;
    }

    /* 検索・フィルタは縦積み気味に */
    .quick-controls{gap:8px}
    #q{min-width:0; width:100%}
    .quick-controls label{font-size:12px}
    .btn{padding:8px 12px} /* タップ領域増 */

    /* カテゴリ見出し周り */
    .category-header{gap:8px}
    .category-header .btn{margin-left:auto}

    /* スマホで「今日の要点」ゾーンを見やすく */
    .summary-card{padding:12px}
    .top-col{padding:10px}

    /* 画面幅が広い時だけPCレイアウトへ */
    @media (min-width: 820px){
      body{margin:24px; font-size:16px}
      .summary-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
      .top-zone{grid-template-columns:1fr 1fr}
      #q{width:auto; min-width:260px}
    }

    /* デフォルト（スマホ）：固定しない */
    .summary-card{
      position: static;
    }

    /* PCサイズ以上のみ固定 */
    @media (min-width: 820px){
      .summary-card{
        position: sticky;
        top: 8px;
        z-index: 10;
      }
    }
    details.insight { margin-top:6px; }
    details.insight > summary {
      cursor:pointer;
      list-style:none;
    }
    details.insight > summary::-webkit-details-marker {
      display:none;
    }
    details.insight > summary::before {
      content:"▶ ";
    }
    details.insight[open] > summary::before {
      content:"▼ ";
    }
    /* details 展開時の視認性向上 */
    details.insight {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 6px 8px;
      background: var(--bg);
    }

    details.insight[open] {
      background: #f7faff;           /* 薄い青 */
      border-color: #dbe7ff;
    }

    /* summary（トグル）の見た目 */
    details.insight > summary {
      cursor: pointer;
      padding: 4px 0;
      font-weight: 500;
    }

    details.insight > summary::-webkit-details-marker {
      display: none;
    }

    /* 開閉アイコン */
    details.insight > summary::before {
      content: "▶ ";
      color: #4c6ef5;
    }
    details.insight[open] > summary::before {
      content: "▼ ";
    }

    /* 展開後の中身の余白 */
    details.insight[open] > *:not(summary) {
      margin-top: 6px;
    }
    /* 開いている要約だけ影を付ける */
    details.insight[open] {
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
    }

    /* スマホで浮きすぎないように微調整 */
    @media (max-width: 640px) {
      details.insight[open] {
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.07);
      }
    }
    /* ジャンプ時に sticky に隠れない */
    .topic-row { scroll-margin-top: 88px; }
    
    #filter-count { color:#555; }
    
    #filter-hint { color:#666; }
    #filter-hint strong { color:#444; }

    .nas .small{display:block;margin-top:2px}

    .close-floating{
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 9999;
      padding: 10px 14px;
      border-radius: 999px;
    }
    .category-header{
      position: sticky;
      top: 0;
      z-index: 10;
      background: var(--bg); /* 背景必須 */
    }

    /* Tag bar: wrap + mobile collapse */
    .tag-bar{
      display:flex;
      flex-wrap:wrap;
      gap:6px;
      align-items:center;
    }

    .btn-reset{
      background:#f5f5f5;
      border:1px solid #ccc;
      font-weight:700;
    }

    .btn-more{
      background:var(--bg);
      border:1px dashed var(--border);
      font-weight:650;
    }

    /* スマホ時：初期は7個まで表示（Reset + OR + タグ群含めて調整可） */
    @media (max-width: 640px){
      #tagBar.collapsed button:nth-of-type(n+8){
        display:none;
      }
      /* ORチェックのラベルは常に見せたいなら、上のnth-of-type対象外にするため別classで扱う */
      .tag-mode{ margin-left:4px; }
    }
    .date{
      margin-left: 6px;
      font-size: 0.85em;
      color: #666;
      white-space: nowrap;
    }
"""

HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>技術動向ダイジェスト</title>
  <meta name="description" content="国内外の技術トレンドをカテゴリ別に要約し、注目度・新着・解説を1ページで確認できる技術動向ダイジェスト。">
  <link rel="canonical" href="/daily-tech-trend/">
  <link rel="alternate" type="application/rss+xml" title="Daily Tech Trend RSS" href="/daily-tech-trend/feed.xml">

  <meta property="og:title" content="技術動向ダイジェスト">
  <meta property="og:description" content="国内外の技術トレンドをカテゴリ別に要約し、注目度・新着・解説を1ページで確認できる技術動向ダイジェスト。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="/daily-tech-trend/">
  <meta property="og:site_name" content="Daily Tech Trend">
  <meta property="og:locale" content="ja_JP">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="技術動向ダイジェスト">
  <meta name="twitter:description" content="国内外の技術トレンドをカテゴリ別に要約し、注目度・新着・解説を1ページで確認できる技術動向ダイジェスト。">
  <link rel="stylesheet" href="{{ common_css_href }}">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"Daily Tech Trend","url":"/daily-tech-trend/"}</script>
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","name":"技術動向ダイジェスト","description":"国内外の技術トレンドをカテゴリ別に要約し、注目度・新着・解説を1ページで確認できる技術動向ダイジェスト。","url":"/daily-tech-trend/","isPartOf":{"@type":"WebSite","name":"Daily Tech Trend","url":"/daily-tech-trend/"}}</script>
</head>
<body data-filter-total="1">
  <h1>技術動向ダイジェスト</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/forecast/hits/" class="{{ 'active' if page=='forecast_hits' else '' }}">予想的中</a>
    <a href="/daily-tech-trend/diff/" class="">差分</a>
    <a href="/daily-tech-trend/entity/" class="">企業別</a>
    <a href="/daily-tech-trend/exec/" class="">エグゼクティブ</a>
    <a href="/daily-tech-trend/search.html" class="">🔍 検索</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
    <a href="/daily-tech-trend/feed.xml" class="" title="RSSフィード">RSS</a>
  </div>

    <div class="summary-card">
    <div class="summary-title">今日の要点（技術動向）</div>
    <button id="closeFloating" class="close-floating" hidden>閉じる</button>
    <div class="summary-grid">
      <div class="summary-item">
        <div class="k">Generated (JST)</div>
        <div class="v">{{ meta.generated_at_jst }}</div>
      </div>
      <div class="summary-item">
        <div class="k">Runtime</div>
        <div class="v">{{ meta.runtime_sec }} sec</div>
      </div>
      <div class="summary-item">
        <div class="k">Articles</div>
        <div class="v">{{ meta.total_articles }} <span class="small">(new48h {{ meta.new_articles_48h }})</span></div>
      </div>
      <div class="summary-item">
        <div class="k">RSS Sources</div>
        <div class="v">{{ meta.rss_sources }}</div>
      </div>
    </div>
    <div class="small" style="margin-top:10px">
      <span class="badge">Tags</span>

      <div id="tagBar" class="tag-bar collapsed" role="toolbar" aria-label="タグフィルタ" style="margin-top:6px">
        <button class="btn btn-reset" type="button" onclick="clearTagFilter()">🔄 リセット</button>

        <label class="small tag-mode">
          <input type="checkbox" id="tagModeOr"> OR（どれか）
        </label>

        {% for group_name, group_tags in tag_groups %}
          <span class="tag-group-label">{{ group_name }}</span>
          {% for tg, cnt in group_tags %}
            <button class="btn" type="button" data-tag-btn="{{ tg }}" onclick="toggleTag('{{ tg }}')">
              {{ tg }} ({{ cnt }})
            </button>
          {% endfor %}
        {% endfor %}
      </div>

      <button id="tagMore" class="btn btn-more" type="button" style="margin-top:6px">＋ よく使うタグ以外も表示</button>

    </div>
    <div id="tag-active" class="small" style="margin-top:6px; display:none;"></div>
    <div class="quick-controls">
      <input id="q" type="search" placeholder="タイトル・要約を検索" aria-label="タイトル・要約を検索" />
      <button class="btn" type="button" data-toggle-all-cats onclick="toggleAllCats()">すべて閉じる</button>
      <label class="small">並び替え
        <select id="sortKey">
          <option value="date">日付</option>
          <option value="importance">重要度</option>
          <option value="composite">重要度×新着</option>
        </select>
      </label>

      <label class="small">順序
        <select id="sortDir">
          <option value="desc">降順</option>
          <option value="asc">昇順</option>
        </select>
      </label>

      <button class="btn" type="button" onclick="applySort()" aria-label="ソートを適用">適用</button>

    </div>
    <div id="filter-count" class="small" style="margin-top:6px; display:none;"></div>
    <div id="filter-hint" class="small" style="margin-top:4px; display:none;"></div>
  </div>

  <section class="quick-jump" aria-label="クイックジャンプ（カテゴリへ移動）">
    <div class="small" style="margin-bottom:6px"><strong>クイックジャンプ（カテゴリへ移動）</strong></div>
    <div class="tag-bar">
      {% for cat in categories %}
        <a class="btn" href="#cat-{{ cat.id }}">{{ cat.name }}</a>
      {% endfor %}
    </div>
  </section>

  {% if market_top or market_trending_top %}
  <details class="foldable-section top-zone-fold" data-top-zone-details>
    <summary>📈 Market ハイライト</summary>
    <section class="top-zone">
    <div class="top-col" id="market-card">
      <h3>📈Market Top 10（importance × recent）</h3>
      <ol class="top-list">
        {% for t in market_top %}
          <li class="topic-row"
              data-title="{{ t.title|e }}"
              data-summary="{{ (t.summary or '')|e }}"
              data-imp="{{ t.importance or 0 }}"
              data-recent="{{ t.recent or 0 }}"
              data-date="{{ t.date }}"
              data-tags="{{ t.tags|default([])|join(',') }}">
            <span class="badge imp">重要度 {{ t.importance or 0 }}</span>
            {% if t.recent > 0 %}
              <span class="badge recent {% if t.recent >= 5 %}hot{% endif %}">
                48h +{{ t.recent }}
              </span>
            {% endif %}
            <a href="#topic-{{ t.id }}">{{ t.title }}</a>
            <span class="date">{{ fmt_date(t.date) }}</span>
            <span class="badge"><a href="#cat-market">{{ cat_name.get('market', 'market') }}</a></span>
          </li>
        {% endfor %}
      </ol>
    </div>

    <div class="top-col">
      <h3>📊Market Trending（48h増分）</h3>
      <ol class="top-list">
        {% for t in market_trending_top %}
          <li class="topic-row"
              data-title="{{ t.title|e }}"
              data-summary="{{ (t.summary or '')|e }}"
              data-imp="{{ t.importance or 0 }}"
              data-recent="{{ t.recent or 0 }}"
              data-date="{{ t.date }}"
              data-tags="{{ t.tags|default([])|join(',') }}">
            <span class="badge imp">重要度 {{ t.importance or 0 }}</span>
            {% if t.recent > 0 %}
              <span class="badge recent {% if t.recent >= 5 %}hot{% endif %}">
                48h +{{ t.recent }}
              </span>
            {% endif %}
            <a href="#topic-{{ t.id }}">{{ t.title }}</a>
            <span class="date">{{ fmt_date(t.date) }}</span>
            <span class="badge"><a href="#cat-market">{{ cat_name.get('market', 'market') }}</a></span>
          </li>
        {% endfor %}
      </ol>
    </div>
    </section>
  </details>
  {% endif %}

  <div class="layout-with-sidebar">
    <aside class="category-toc" aria-label="カテゴリ一覧">
      <div class="category-toc-title">カテゴリ一覧</div>
      <label for="category-toc-select" class="sr-only">カテゴリへ移動</label>
      <select id="category-toc-select" class="category-toc-select" aria-label="カテゴリへ移動">
        <option value="">カテゴリへ移動</option>
        {% for cat in categories %}
          <option value="#cat-{{ cat.id }}">{{ cat.name }}</option>
        {% endfor %}
      </select>
      <nav class="category-toc-links">
        {% for cat in categories %}
          <a href="#cat-{{ cat.id }}" data-category-link="{{ cat.id }}">{{ cat.name }}</a>
        {% endfor %}
      </nav>
    </aside>

    <div class="layout-with-sidebar-content">
    {% for cat in categories %}
  <section class="category-section" id="cat-{{ cat.id }}" role="region" aria-label="{{ cat.name }}">
    <div class="category-header">
      <h2 style="margin:0">{{ cat.name }} <span class="tag">{{ cat.id }}</span></h2>
      {% if cat.id in news_link_map %}
        <a class="btn small" href="./news/index.html#cat-{{ news_link_map[cat.id][0] }}" style="font-size:12px;">
          → {{ news_link_map[cat.id][1] }}
        </a>
      {% endif %}
      <button class="btn" type="button" onclick="toggleCat('{{ cat.id }}')">表示切替</button>
    </div>

    <div class="category-body">
      <!-- ここに既存の topbox と topics list をそのまま置く -->


    <div class="topbox">
      <h3>⭐注目TOP5（48h増分）</h3>
      {% if hot_by_cat.get(cat.id) %}
        <ul>
          {% for item in hot_by_cat[cat.id] %}
            <li>
              <a href="#topic-{{ item.id }}">{{ item.title }}</a>
              <span class="date">
                {{ fmt_date(item.date) }}
              </span>
              {% if item.recent > 0 %}
                <span class="badge recent {% if item.recent >= 5 %}hot{% endif %}">
                  48h +{{ item.recent }}
                </span>
              {% endif %}
              <span class="small">（累計 {{ item.articles }}）</span>
            </li>
          {% endfor %}
        </ul>
      {% else %}
        <div class="small">該当なし</div>
      {% endif %}
    </div>

    {% if topics_by_cat.get(cat.id) %}
      <ul style="list-style:none;padding:0">
        {% for t in topics_by_cat[cat.id] %}
           <li id="topic-{{ t.id }}" class="topic-row"
              data-title="{{ t.title|e }}"
              data-summary="{{ (t.summary or '')|e }}"
              data-imp="{{ t.importance or 0 }}"
              data-recent="{{ t.recent or 0 }}"
              data-date="{{ t.date }}"
              data-tags="{{ t.tags|default([])|join(',') }}">
            <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:6px">
              {% if t.url and t.url != "#" %}
                <a href="{{ t.url }}" target="_blank" rel="noopener" style="font-weight:500">{{ t.title }}</a>
              {% else %}
                <span style="font-weight:500">{{ t.title }}</span>
              {% endif %}
              {% if t.date %}
                <span class="date">{{ fmt_date(t.date) }}</span>
              {% endif %}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
              {% if t.importance is not none %}
                <span class="badge imp">重要度 {{ t.importance }}</span>
              {% endif %}
              {% if t.recent > 0 %}
                <span class="badge recent {% if (t.recent or 0) >= 5 %}hot{% endif %}">
                  48h +{{ t.recent }}
                </span>
              {% endif %}
              {% if t.tags and t.tags|length>0 %}
                {% for tg in t.tags %}
                  <span class="badge">{{ tg }}</span>
                {% endfor %}
              {% endif %}
              <a class="badge" href="/daily-tech-trend/topic/{{ t.id }}/" title="このトピックの記事を時系列で見る">📈 経緯</a>
            </div>

            {% if t.summary %}
              <div class="summary-preview">{{ t.summary[:100] }}{% if t.summary|length > 100 %}…{% endif %}</div>
            {% endif %}
            {% if t.source %}<div class="mini">{{ t.source }}</div>{% endif %}

            {% if t.summary or (t.key_points and t.key_points|length>0) or (t.perspectives) or (t.perspective_digest) or (t.evidence_urls and t.evidence_urls|length>0) %}
              <details class="insight" role="group">
                <summary>要約・解説を表示</summary>

                {% if t.summary %}
                  <div style="font-size:13px;line-height:1.6"><strong>要約</strong>：{{ t.summary }}</div>
                {% endif %}

                {% if t.key_points and t.key_points|length>0 %}
                  <ul class="kps">
                    {% set shown = namespace(n=0, limited=0) %}
                    {% set seen = namespace(items=[]) %}
                    {% for kp in t.key_points %}
                      {% set k = (kp or "") %}
                      {# 既存の「短文テンプレ」は1回に畳む #}
                      {% if "本文中の明確な事実は限定的" in k or "本文が短く" in k %}
                        {% if shown.limited == 0 %}
                          <li>推測：本文情報が限られるため、影響範囲・当事者・時系列をリンク先で要確認</li>
                          {% set shown.limited = 1 %}
                          {% set shown.n = shown.n + 1 %}
                        {% endif %}
                      {% else %}
                        {# 「推測: ...」が重複する場合は1回だけ出す #}
                        {% if k.startswith("推測") %}
                          {% if k not in seen.items %}
                            <li>{{ k }}</li>
                            {% set seen.items = seen.items + [k] %}
                            {% set shown.n = shown.n + 1 %}
                          {% endif %}
                        {% else %}
                          <li>{{ k }}</li>
                          {% set shown.n = shown.n + 1 %}
                        {% endif %}
                      {% endif %}
                    {% endfor %}
                    {% if shown.n == 0 %}
                      <li>推測：リンク先の本文確認が必要</li>
                    {% endif %}
                  </ul>
                {% endif %}

                {% if t.perspectives %}
                <div class="perspectives">
                  {% if t.perspectives.engineer %}<div><b>技術者目線</b>: {{ t.perspectives.engineer }}</div>{% endif %}
                  {% if t.perspectives.management %}<div><b>経営者目線</b>: {{ t.perspectives.management }}</div>{% endif %}
                  {% if t.perspectives.consumer %}<div><b>消費者目線</b>: {{ t.perspectives.consumer }}</div>{% endif %}
                </div>
                {% endif %}

                {% if t.perspective_digest %}
                <div class="perspective-digest">
                  <div style="font-size:12px;color:#666;margin-bottom:2px">立場別くわしい解説</div>
                  {% if t.perspective_digest.engineer %}<div><b>技術者目線</b>: {{ t.perspective_digest.engineer }}</div>{% endif %}
                  {% if t.perspective_digest.management %}<div><b>経営者目線</b>: {{ t.perspective_digest.management }}</div>{% endif %}
                  {% if t.perspective_digest.consumer %}<div><b>消費者目線</b>: {{ t.perspective_digest.consumer }}</div>{% endif %}
                </div>
                {% endif %}

                {% if t.next_actions and t.next_actions|length>0 %}
                  <div style="margin-top:10px;font-size:13px"><strong>次アクション</strong></div>
                  <ul class="nas">
                    {% for na in t.next_actions %}
                      {% if na is mapping %}
                        <li>
                          <div><strong>{{ na.action }}</strong>
                            {% if na.priority %}<span class="badge">{{ na.priority }}</span>{% endif %}
                          </div>
                          {% if na.expected_outcome %}
                            <div class="small">→ {{ na.expected_outcome }}</div>
                          {% endif %}
                        </li>
                      {% else %}
                        <li>{{ na }}</li>
                      {% endif %}
                    {% endfor %}
                  </ul>
                {% endif %}

                {% if t.evidence_urls and t.evidence_urls|length>0 %}
                  <div class="evidence-urls">
                    <strong>根拠</strong>：
                    {% for u in t.evidence_urls %}
                      <a href="{{ u }}" target="_blank" rel="noopener">{{ u|truncate(60, True) }}</a>{% if not loop.last %} | {% endif %}
                    {% endfor %}
                  </div>
                {% endif %}
              </details>
            {% endif %}

          </li>
        {% endfor %}
      </ul>
    {% else %}
      <div class="meta">該当なし</div>
    {% endif %}
      </div>
  </section>
  {% endfor %}
    </div>
  </div>
<script src="{{ common_js_src }}" defer></script>
<script>
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

function forceTopIfNoHash(){
  if (!location.hash) window.scrollTo(0, 0);
}

window.addEventListener('pageshow', forceTopIfNoHash);
window.addEventListener('load', () => {
  setTimeout(() => {
    forceTopIfNoHash();
    if (!location.hash) toggleAllCats();
  }, 0);
});

document.addEventListener('DOMContentLoaded', function(){ if (window.DTTCommon) window.DTTCommon.setupCommon('topic'); });
</script>

</body>
</html>
"""


NAME_MAP = {
    "system": "システム",
    "manufacturing": "製造",
    "blast_furnace": "高炉",
    "eaf": "電炉",
    "rolling": "圧延",
    "quality": "品質",
    "maintenance": "保全",
    "market": "市況",
    "security": "セキュリティ",
    "ai": "AI",
    "dev": "開発",
    "other": "その他",
}
from typing import Any, List

def _safe_json_list(s: str | None) -> List[str]:
    """list[str] を想定（key_points / evidence_urls 用）"""
    if not s:
        return []
    try:
        v = clean_json_like(json.loads(s))
        if isinstance(v, list):
            out = []
            for x in v:
                if x is None:
                    continue
                out.append(clean_for_html(str(x)))
            return out
    except Exception as e:
        _log_render_error("safe_json_list.parse", e, level="debug")
    return []


OPS_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>運用ダッシュボード | Daily Tech Trend</title>
  <meta name="description" content="パイプライン稼働状況・記事収集トレンド・フィード健全性を確認する運用ダッシュボード。">
  <link rel="canonical" href="/daily-tech-trend/ops/">
  <link rel="alternate" type="application/rss+xml" title="Daily Tech Trend RSS" href="/daily-tech-trend/feed.xml">
  <link rel="stylesheet" href="{{ common_css_href }}">
  <style>
    .ops-section{margin:16px 0;padding:14px 16px;background:var(--panel);border:1px solid var(--border);border-radius:12px}
    .ops-section h2{margin:0 0 10px;font-size:16px}
    .bar-chart{display:flex;align-items:flex-end;gap:3px;height:140px;padding:0 0 28px}
    .bar-col{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;flex:1;min-width:0;height:100%;position:relative}
    .bar-col .bar{background:var(--accent);border-radius:3px 3px 0 0;width:100%;transition:height .3s}
    .bar-col .bar-label{font-size:10px;color:var(--text-sub);position:absolute;bottom:-22px;white-space:nowrap}
    .bar-col .bar-val{font-size:10px;color:var(--text-main);font-weight:600;margin-bottom:2px}
    .hbar-list{display:flex;flex-direction:column;gap:4px}
    .hbar-row{display:grid;grid-template-columns:160px 1fr 100px;align-items:center;gap:8px;font-size:13px}
    .hbar-row .hbar-label{color:var(--text-sub);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .hbar-row .hbar-track{height:18px;background:var(--bg);border-radius:4px;overflow:hidden;border:1px solid var(--border)}
    .hbar-row .hbar-fill{height:100%;background:var(--accent);border-radius:4px 0 0 4px;min-width:2px}
    .hbar-row .hbar-nums{font-size:12px;color:var(--text-sub);white-space:nowrap}
    .feed-ok{color:#16a34a;font-weight:600}
    .feed-warn{color:#dc2626}
    .status-chip{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
    .status-chip.ok{background:#dcfce7;color:#16a34a}
    .status-chip.warn{background:#fee2e2;color:#dc2626}
    .status-chip.na{background:#f3f4f6;color:#9ca3af}
    .table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -12px;padding:0 12px}
    .source-table{width:100%;border-collapse:collapse;font-size:13px;table-layout:auto}
    .source-table th,.source-table td{white-space:normal;word-break:break-word}
    .source-table .url-cell{max-width:40vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    @media(max-width:640px){
      .ops-section{padding:10px 8px}
      .ops-section h2{font-size:14px}
      .bar-chart{height:110px;gap:1px;padding:0 0 24px}
      .bar-col .bar-label{font-size:8px;bottom:-18px}
      .bar-col .bar-val{font-size:8px}
      .hbar-row{grid-template-columns:1fr 2fr 70px;gap:4px;font-size:12px}
      .hbar-row .hbar-label{font-size:11px;white-space:normal;word-break:break-all;text-align:left;line-height:1.3}
      .hbar-row .hbar-nums{font-size:10px}
      .summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
      .source-table{font-size:11px}
      .source-table th,.source-table td{padding:4px 5px}
      .source-table .url-cell{max-width:35vw;font-size:10px}
    }
  </style>
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","name":"運用ダッシュボード","description":"パイプライン稼働状況・記事収集トレンド・フィード健全性を確認する運用ダッシュボード。","url":"/daily-tech-trend/ops/","isPartOf":{"@type":"WebSite","name":"Daily Tech Trend","url":"/daily-tech-trend/"}}</script>
</head>
<body>
  <h1>運用ダッシュボード</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/forecast/hits/" class="{{ 'active' if page=='forecast_hits' else '' }}">予想的中</a>
    <a href="/daily-tech-trend/diff/" class="">差分</a>
    <a href="/daily-tech-trend/entity/" class="">企業別</a>
    <a href="/daily-tech-trend/exec/" class="">エグゼクティブ</a>
    <a href="/daily-tech-trend/search.html" class="">🔍 検索</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
    <a href="/daily-tech-trend/feed.xml" class="" title="RSSフィード">RSS</a>
  </div>

  <!-- セクション1: パイプライン概況 -->
  <div class="summary-card">
    <div class="summary-title">パイプライン概況</div>
    <div class="summary-grid">
      <div class="summary-item"><div class="k">最終更新</div><div class="v">{{ meta.generated_at_jst }}</div></div>
      <div class="summary-item"><div class="k">記事総数</div><div class="v">{{ ops.article_total }}</div></div>
      <div class="summary-item"><div class="k">直近7日</div><div class="v">+{{ ops.article_week }}</div></div>
      <div class="summary-item"><div class="k">直近48h</div><div class="v">+{{ ops.article_48h }}</div></div>
      <div class="summary-item"><div class="k">トピック数</div><div class="v">{{ ops.topic_total }}</div></div>
      <div class="summary-item"><div class="k">LLM分析済み</div><div class="v">{{ ops.insight_count }}</div></div>
      <div class="summary-item"><div class="k">分析未生成</div><div class="v">{{ ops.insight_pending }}</div></div>
      <div class="summary-item"><div class="k">RSSソース</div><div class="v">{{ meta.rss_sources }}</div></div>
    </div>
  </div>

  <!-- セクション2: 記事収集トレンド（14日） -->
  <div class="ops-section">
    <h2>記事収集トレンド（直近14日）</h2>
    {% if daily_trend and daily_trend|length > 0 %}
    <div class="bar-chart">
      {% for d in daily_trend %}
      <div class="bar-col">
        <div class="bar-val">{{ d.cnt }}</div>
        <div class="bar" style="height:{{ d.px }}px"></div>
        <div class="bar-label">{{ d.label }}</div>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <div class="meta">データなし</div>
    {% endif %}
  </div>

  <!-- セクション3: カテゴリ別記事分布 -->
  <div class="ops-section">
    <h2>カテゴリ別記事数</h2>
    {% if category_dist and category_dist|length > 0 %}
    <div class="hbar-list">
      {% for c in category_dist %}
      <div class="hbar-row">
        <div class="hbar-label" title="{{ c.name }}">{{ c.name }}</div>
        <div class="hbar-track"><div class="hbar-fill" style="width:{{ c.pct }}%"></div></div>
        <div class="hbar-nums">{{ c.total }} <span class="small">(7d +{{ c.week }})</span></div>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <div class="meta">データなし</div>
    {% endif %}
  </div>

  <!-- セクション4: ソース別記事数TOP15 -->
  <div class="ops-section">
    <h2>ソース別記事数 TOP15</h2>
    {% if source_exposure and source_exposure|length > 0 %}
      <div class="table-wrap">
      <table class="source-table">
        <thead><tr><th>ソース</th><th class="num">全期間</th><th class="num">7日</th><th class="num">48h</th><th>主カテゴリ</th></tr></thead>
        <tbody>
        {% for s in source_exposure %}
          <tr><td>{{ s.source }}</td><td class="num">{{ s.total }}</td><td class="num">{{ s.recent7d }}</td><td class="num">{{ s.recent48 }}</td><td>{{ s.categories }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
    {% else %}
      <div class="meta">該当ソースなし</div>
    {% endif %}
  </div>

  <!-- セクション5: フィード健全性 -->
  <div class="ops-section">
    <h2>フィード健全性</h2>
    {% if feed_issues and feed_issues|length > 0 %}
      <div class="small" style="margin-bottom:8px">障害が発生しているフィード（failure_count > 0）</div>
      <div class="table-wrap">
      <table class="source-table">
        <thead><tr><th>フィードURL</th><th class="num">障害回数</th><th>最終成功</th><th>エラー内容</th></tr></thead>
        <tbody>
        {% for f in feed_issues %}
          <tr>
            <td class="url-cell" title="{{ f.url }}">{{ f.url_short }}</td>
            <td class="num"><span class="feed-warn">{{ f.failure_count }}</span></td>
            <td class="small">{{ f.last_success or '-' }}</td>
            <td class="small">{{ f.reason or '-' }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      </div>
    {% else %}
      <div class="feed-ok" style="padding:12px 0">全フィード正常稼働中</div>
    {% endif %}
  </div>

  <!-- セクション6: フィード品質スコア -->
  {% if feed_quality and feed_quality|length > 0 %}
  <div class="ops-section">
    <h2>フィード品質スコア <span class="small" style="font-weight:400;color:var(--text-sub)">(0-100, 小さい順に表示)</span></h2>
    <div class="small" style="margin-bottom:8px">失敗率×50% + 鮮度×30% + 一次情報比率×20% の加重平均。スコアが低いフィードから優先的に見直す。</div>
    <div class="table-wrap">
    <table class="source-table">
      <thead><tr>
        <th>フィードURL</th><th class="num">スコア</th><th class="num">失敗</th>
        <th>最終成功</th><th class="num">一次情報率</th><th class="num">記事数</th>
      </tr></thead>
      <tbody>
      {% for q in feed_quality[:30] %}
        <tr>
          <td class="url-cell small" title="{{ q.url }}">{{ q.url[:60] }}{% if q.url|length > 60 %}...{% endif %}</td>
          <td class="num">
            <span style="display:inline-block;padding:2px 8px;border-radius:4px;color:#fff;font-weight:700;background:{% if q.score >= 70 %}#16a34a{% elif q.score >= 40 %}#d97706{% else %}#dc2626{% endif %}">{{ q.score }}</span>
          </td>
          <td class="num">{{ q.failure_count }}</td>
          <td class="small">{{ q.last_success_at or '-' }}</td>
          <td class="num small">{{ q.primary_ratio }}%</td>
          <td class="num small">{{ q.article_count }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>
  {% endif %}


  <script src="{{ common_js_src }}" defer></script>
</body>
</html>
"""

def load_categories_from_yaml() -> List[Dict[str, str]]:
    try:
        with open("src/sources.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cats = cfg.get("categories")
        if isinstance(cats, list):
            out = []
            for c in cats:
                if isinstance(c, dict) and "id" in c and "name" in c:
                    out.append({"id": str(c["id"]), "name": str(c["name"])})
            return out
    except Exception as e:
        _log_render_error("load_categories_from_yaml", e, level="warning")
        return []
    return []

def _safe_json_obj(s: str | None) -> Dict[str, Any]:
    if not s:
        return {}
    try:
        v = clean_json_like(json.loads(s))
        return v if isinstance(v, dict) else {}
    except Exception as e:
        _log_render_error("safe_json_obj.parse", e, level="debug")
        return {}



def _news_importance_basis_simple(importance: int, dt: str, category: str, tags: List[str]) -> str:
    imp = int(importance or 0)
    freshness = "通常"
    try:
        now = datetime.now(timezone.utc)
        d = datetime.fromisoformat((dt or "").replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (now - d).total_seconds() / 3600.0)
        if age_h <= 6:
            freshness = "高"
        elif age_h <= 24:
            freshness = "中"
        else:
            freshness = "低"
    except Exception as e:
        _log_render_error("news_importance_basis.freshness", e, level="debug")

    cat_weight = {
        "security": "高",
        "policy": "中",
        "market": "中",
        "industry": "中",
        "company": "低",
        "news": "低",
    }.get((category or "").lower(), "低")
    related = len(tags or [])
    return f"importance={imp} / 速報性:{freshness} / カテゴリ重み:{cat_weight} / 関連:{related}タグ"


def build_categories_fallback(cur) -> List[Dict[str, str]]:
    """
    YAMLが無い場合でも表示が空にならないよう、DBからカテゴリを推定する。
    """
    cur.execute("SELECT DISTINCT category FROM topics WHERE category IS NOT NULL AND category != ''")
    cats = [r[0] for r in cur.fetchall()]
    if not cats:
        cur.execute("SELECT DISTINCT category FROM articles WHERE category IS NOT NULL AND category != ''")
        cats = [r[0] for r in cur.fetchall()]
    if not cats:
        cats = ["other"]
    return [{"id": c, "name": NAME_MAP.get(c, c)} for c in cats]


def ensure_category_coverage(cur, categories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    YAMLのカテゴリに存在しないカテゴリがDBにある場合でも、表示対象に追加する。
    """
    ids = {c["id"] for c in categories}
    cur.execute("SELECT DISTINCT category FROM topics WHERE category IS NOT NULL AND category != ''")
    db_cats = [r[0] for r in cur.fetchall()]
    for c in db_cats:
        if c not in ids:
            categories.append({"id": c, "name": NAME_MAP.get(c, c)})
            ids.add(c)
    if not categories:
        categories = [{"id": "other", "name": NAME_MAP["other"]}]
    return categories


def _extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception as e:
        _log_render_error("extract_domain", e, level="debug")
        return ""


def render_news_pages(out_dir: Path, generated_at: str, cur) -> None:
    news_dir = out_dir / "news"
    news_dir.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    cutoff_48h_str = (now - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")


    # 1) Japan / Global はカテゴリ見出しで分割
    jp_limit_each = NEWS_REGION_LIMIT_EACH.get("jp", 30)
    gl_limit_each = NEWS_REGION_LIMIT_EACH.get("global", 30)
    sections_jp = render_news_region_page(
        cur,
        "jp",
        limit_each=jp_limit_each,
        cutoff_dt=cutoff_48h_str,
        min_per_category=NEWS_MIN_PER_CATEGORY.get("jp", 0),
    )
    sections_gl = render_news_region_page(
        cur,
        "global",
        limit_each=gl_limit_each,
        cutoff_dt=cutoff_48h_str,
        min_per_category=NEWS_MIN_PER_CATEGORY.get("global", 0),
    )

    # Tag list（source中心 + category/regionも混ぜる）
    tag_count = {}
    def add_tags_from_sections(sections, region_label):
        for sec in sections:
            cat = sec.get("anchor") or "other"
            for it in sec.get("rows", []):
                src = it.get("source") or ""
                tags = [region_label, cat]
                if src:
                    tags.append(src)
                for tg in tags:
                    tag_count[tg] = tag_count.get(tg, 0) + 1

    add_tags_from_sections(sections_jp, "jp")
    add_tags_from_sections(sections_gl, "global")
    tag_list_news = sorted(tag_count.items(), key=lambda x: (-x[1], x[0]))[:50]

    # meta（summary-cardに表示する）
    news_total = sum(s["count"] for s in sections_jp) + sum(s["count"] for s in sections_gl)
    news_new48 = sum(s.get("recent48", 0) for s in sections_jp) + sum(s.get("recent48", 0) for s in sections_gl)
    meta_news = {
        "generated_at_jst": generated_at,
        "total_articles": news_total,
        "new_articles_48h": news_new48,
        "jp_count": sum(s["count"] for s in sections_jp),
        "global_count": sum(s["count"] for s in sections_gl),
    }


    # 2) 総合は「全国」「世界」の2セクションにしてまず成立させる（最小）
    #    ※将来、カテゴリ横断にしたくなったらここを拡張
    def flatten(sections, limit=999):
        out = []
        for sec in sections:
            out.extend(sec.get("rows", []))   # ★ rows
        return out[:limit]


    sections_all = [
        {
            "anchor": "jp",
            "title": "🇯🇵 国内ニュース",
            "count": sum(s["count"] for s in sections_jp),
            "recent48": sum(s.get("recent48", 0) for s in sections_jp),
            "rows": flatten(sections_jp, 999),
        },
        {
            "anchor": "global",
            "title": "🌍 世界ニュース",
            "count": sum(s["count"] for s in sections_gl),
            "recent48": sum(s.get("recent48", 0) for s in sections_gl),
            "rows": flatten(sections_gl, 999),
        },
    ]
    # --- ここから差し替え ---

    # # sections_jp / sections_gl は「NEWS_SECTIONS順の配列」なので
    # # そのまま “カテゴリ別セクション” として使う（総合ページ用に地域プレフィックスだけ付ける）
    # def with_prefix(sections, prefix, anchor_prefix):
    #     out = []
    #     for sec in sections:
    #         out.append({
    #             "anchor": f"{anchor_prefix}-{sec['anchor']}",         # 例: jp-manufacturing
    #             "title": f"{prefix} {sec['title']}",                  # 例: 🇯🇵 製造業・鉄鋼...
    #             "count": sec["count"],
    #             "recent48": sec.get("recent48", 0),
    #             "rows": sec.get("rows", []),
    #         })
    #     return out

    # sections_all = (
    #     with_prefix(sections_jp, "🇯🇵", "jp")
    #     + with_prefix(sections_gl, "🌍", "global")
    # )

    # --- ここまで差し替え ---


    pages = [
        ("news",   "ニュースダイジェスト", "ニュースダイジェスト", sections_all, "index.html"),
    ]

    news_assets = build_asset_paths()

    for page, title, heading, sections, filename in pages:
        (news_dir / filename).write_text(
            _jinja_env.get_template("news.html").render(
                common_css_href=news_assets["common_css_href"],
                common_js_src=news_assets["common_js_src"],

                page=page,
                nav_prefix=news_assets["nav_prefix"], 
                title=title,
                heading=heading,
                generated_at=generated_at,

                meta=meta_news,
                tag_list=tag_list_news,

                sections=sections,
            ),

            encoding="utf-8",
        )

    # 立場別意見ページは廃止済み（未来予測ページに統合）

NEWS_SECTIONS = [
    ("news",          "一般ニュース（未分類）"),
    ("manufacturing", "製造業・鉄鋼（現場/プラント）"),
    ("policy",        "政策・制度・規制"),
    ("security",      "セキュリティ/事故"),
    ("industry",      "産業・市況・サプライチェーン"),
    ("company",       "企業動向（提携/投資/決算）"),
    ("other",         "その他"),
]

NEWS_SECTION_POINTS = {
    "news": "社会・産業全体の動き。技術導入や投資判断の背景として確認。",
    "manufacturing": "現場改善・省人化・品質保証に直結。設備更新やDX提案の根拠。",
    "policy": "制度変更・規制強化の兆し。中長期のIT投資・対応計画に影響。",
    "security": "事業継続・リスク管理の観点。対策投資の説明材料。",
    "industry": "市況・サプライチェーン変化。需要予測やシステム刷新の背景。",
    "company": "競合・先行事例。顧客への『他社事例』として利用可能。",
    "other": "個別要因。将来の技術動向と結び付けて整理。",
}

NEWS_REGION_LIMIT_EACH = {
    "jp": 50,
    "global": 30,
}

NEWS_MIN_PER_CATEGORY = {
    "jp": 8,
    "global": 0,
}

def render_news_region_page(cur, region, limit_each=30, cutoff_dt=None, min_per_category=0):
    sections = []
    for cat, title in NEWS_SECTIONS:
        fetch_limit = max(limit_each, min_per_category or 0)
        rows = fetch_news_articles_by_category(cur, region, cat, fetch_limit)

        # 国内不足時はカテゴリ内の最小件数を満たすまで追加取得する
        while (
            min_per_category
            and len(rows) < min_per_category
            and len(rows) >= fetch_limit
            and fetch_limit < 200
        ):
            fetch_limit += max(limit_each, min_per_category)
            rows = fetch_news_articles_by_category(cur, region, cat, fetch_limit)
        items = []
        for r in rows:
            # fetch_news_articles_by_category() のSELECT順に合わせる
            # （現実装: 代表フラグあり=17列 / 旧互換=16列）
            if len(r) >= 17:
                (
                    article_id, title, url, source, category, published_at, fetched_at, dt,
                    importance, typ, summary, key_points, perspectives, perspective_digest, tags, evidence_urls,
                    is_representative,
                ) = r
            else:
                (
                    article_id, title, url, source, category, published_at, fetched_at, dt,
                    importance, typ, summary, key_points, perspectives, perspective_digest, tags, evidence_urls,
                ) = r
                is_representative = 0

            # フィルタ/検索向けのタグは LLM tags を優先し、無い場合はフォールバック
            llm_tags = _safe_json_list(tags)
            if not llm_tags:
                llm_tags = [region, (category or cat or "other")]
                if source:
                    llm_tags.append(source)

            items.append({
                "id": int(article_id),
                "title": clean_for_html(title),
                "url": clean_for_html(url),
                "source": clean_for_html(source),
                "category": clean_for_html(category or cat or "other"),  # ←追加
                "dt": clean_for_html(dt),                                # ←追加（data-date用）
                "dt_jst": fmt_date(dt),
                "published_at": clean_for_html(published_at),
                "published_at_jst": fmt_date(published_at),
                "fetched_at": clean_for_html(fetched_at),
                "fetched_at_jst": fmt_date(fetched_at),

                # LLM結果
                "importance": int(importance) if importance is not None else 0,
                "type": clean_for_html(typ or ""),
                "summary": clean_for_html(summary or ""),
                "key_points": _safe_json_list(key_points),
                "perspectives": _safe_json_obj(perspectives),
                "perspective_digest": _safe_json_obj(perspective_digest),
                "tags": llm_tags,
                "evidence_urls": _safe_json_list(evidence_urls),
                "is_representative": int(is_representative or 0),
                "importance_basis": _news_importance_basis_simple(
                    int(importance) if importance is not None else 0,
                    dt,
                    category or cat or "other",
                    llm_tags,
                ),
            })

        # 重要度0（LLM未分析）の記事を除外
        items = [it for it in items if it.get("importance", 0) > 0]

        items.sort(key=lambda x: (x.get("is_representative", 0), x.get("dt") or "", x.get("id", 0)), reverse=True)
        representative_items = [it for it in items if it.get("is_representative", 0) == 1]
        other_items = [it for it in items if it.get("is_representative", 0) != 1]

        recent48 = 0
        if cutoff_dt:
            recent48 = count_news_recent_48h(cur, region, cat, cutoff_dt)

        TECH_LINK_MAP = {
            "manufacturing": ("manufacturing", "製造業・現場DX"),
            "security": ("security", "セキュリティ"),
            "policy": ("system", "制度・ガバナンス"),
            "industry": ("system", "基幹・業務システム"),
            "company": ("dev", "開発・内製化"),
        }

        tech_link = TECH_LINK_MAP.get(cat)

        sections.append({
            "title": clean_for_html(title),
            "count": len(items),
            "rep_count": len(representative_items),
            "recent48": recent48,
            "point": NEWS_SECTION_POINTS.get(cat, ""),
            "rows": representative_items,
            "other_rows": other_items,
            "anchor": cat,
            "tech_link": tech_link[0] if tech_link else None,
            "tech_label": tech_link[1] if tech_link else None,
        })

    return sections


def fetch_news_articles(cur, region: str, limit: int = 60):
    if region:
        cur.execute(
            """
            SELECT
              articles.id AS article_id,
              COALESCE(NULLIF(title_ja,''), NULLIF(title,''), url) AS title,
              url,
              COALESCE(NULLIF(source,''), '') AS source,
              COALESCE(NULLIF(category,''), '') AS category,
              COALESCE(NULLIF(published_at,''), fetched_at) AS dt,

              (
                SELECT i.importance
                FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC
                LIMIT 1
              ) AS importance,
              (
                SELECT i.tags
                FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC
                LIMIT 1
              ) AS tags,
              (
                SELECT i.summary
                FROM topic_articles ta
                JOIN topic_insights i ON i.topic_id = ta.topic_id
                WHERE ta.article_id = articles.id
                ORDER BY i.importance DESC, ta.topic_id DESC
                LIMIT 1
              ) AS summary

            FROM articles
            WHERE kind='news' AND region=?
            ORDER BY
              COALESCE(importance, 0) DESC,
              datetime(
                substr(
                  replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),
                  1, 19
                )
              ) DESC,
              id DESC
            LIMIT ?
            """,
            (region, limit),
        )
    else:
        cur.execute(
            """
            SELECT
              COALESCE(NULLIF(title_ja,''), NULLIF(title,''), url) AS title,
              url,
              COALESCE(NULLIF(source,''), '') AS source,
              COALESCE(NULLIF(category,''), '') AS category,
              COALESCE(NULLIF(region,''), '') AS region,
              COALESCE(NULLIF(published_at,''), fetched_at) AS dt
            FROM articles
            WHERE kind='news'
            ORDER BY
              datetime(
                substr(
                  replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),
                  1, 19
                )
              ) DESC,
              id DESC
            LIMIT ?
            """,
            (limit,),
        )

    return cur.fetchall()

def fetch_news_articles_by_category(cur, region: str, category: str, limit: int = 40):
    cur.execute(
        """
        SELECT
          a.id AS article_id,
          COALESCE(NULLIF(a.title_ja,''), NULLIF(a.title,''), a.url) AS title,
          a.url,
          COALESCE(NULLIF(a.source,''), '') AS source,
          COALESCE(NULLIF(a.category,''), '') AS category,
          COALESCE(NULLIF(a.published_at,''), '') AS published_at,
          COALESCE(NULLIF(a.fetched_at,''), '') AS fetched_at,
          COALESCE(NULLIF(a.published_at,''), a.fetched_at) AS dt,

          -- 代表insight（importanceが高いtopicを採用）
          (
            SELECT i.importance
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS importance,
          (
            SELECT i.type
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS type,
          (
            SELECT i.summary
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS summary,
          (
            SELECT i.key_points
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS key_points,
          (
            SELECT i.perspectives
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS perspectives,
          (
            SELECT i.perspective_digest
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS perspective_digest,
          (
            SELECT i.tags
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS tags,
          (
            SELECT i.evidence_urls
            FROM topic_articles ta
            JOIN topic_insights i ON i.topic_id = ta.topic_id
            WHERE ta.article_id = a.id
            ORDER BY i.importance DESC, ta.topic_id DESC
            LIMIT 1
          ) AS evidence_urls,
          CASE
            WHEN EXISTS (
              SELECT 1
              FROM topic_articles ta
              WHERE ta.article_id = a.id
                AND COALESCE(ta.is_representative, 0) = 1
            ) THEN 1
            ELSE 0
          END AS is_representative

        FROM articles a
        WHERE a.kind='news'
          AND a.region=?
          AND COALESCE(NULLIF(a.category,''), 'other')=?
        ORDER BY
          datetime(
            substr(
              replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),
              1, 19
            )
          ) DESC,
          a.id DESC
        LIMIT ?

        """,
        (region, category, limit),
    )
    return cur.fetchall()

def count_news_recent_48h(cur, region: str, category: str, cutoff_dt: str) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM articles
        WHERE kind='news'
          AND region=?
          AND COALESCE(NULLIF(category,''), 'other')=?
          AND datetime(
                substr(
                  replace(replace(COALESCE(NULLIF(published_at,''), fetched_at),'T',' '),'+00:00',''),
                  1, 19
                )
              ) >= datetime(?)
        """,
        (region, category, cutoff_dt),
    )
    return int(cur.fetchone()[0] or 0)


# ---------------------------------------------------------------------------
# 未来予測ページ
# ---------------------------------------------------------------------------

FORECAST_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>未来予測レポート | Daily Tech Trend</title>
  <meta name="description" content="直近ニュースに基づくAI未来予測レポート。3つの時間軸と技術者・経営者・消費者の3視点で分析。">
  <link rel="canonical" href="/daily-tech-trend/forecast/">
  <link rel="alternate" type="application/rss+xml" title="Daily Tech Trend RSS" href="/daily-tech-trend/feed.xml">

  <meta property="og:title" content="未来予測レポート | Daily Tech Trend">
  <meta property="og:description" content="直近ニュースに基づくAI未来予測レポート。3つの時間軸と技術者・経営者・消費者の3視点で分析。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="/daily-tech-trend/forecast/">
  <meta property="og:site_name" content="Daily Tech Trend">
  <meta property="og:locale" content="ja_JP">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="未来予測レポート | Daily Tech Trend">
  <meta name="twitter:description" content="直近ニュースに基づくAI未来予測レポート。3つの時間軸と技術者・経営者・消費者の3視点で分析。">
  <link rel="stylesheet" href="{{ common_css_href }}">
  <style>
    /* タブ */
    .forecast-tabs{display:flex;gap:4px;margin:12px 0 0;flex-wrap:wrap}
    .forecast-tabs button{padding:6px 14px;border:1px solid var(--border);border-radius:6px 6px 0 0;
      background:var(--panel);cursor:pointer;font-size:.85rem;color:var(--text-sub);line-height:1.4}
    .forecast-tabs button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
    /* パネル */
    .forecast-panel{display:none;padding:16px;border:1px solid var(--border);border-radius:0 8px 8px 8px;
      background:var(--panel);margin-bottom:20px;overflow-x:auto;word-wrap:break-word;overflow-wrap:break-word}
    /* 予測カード */
    .pred-card{background:var(--bg);border:1px solid var(--border);border-left:4px solid var(--border);
      border-radius:10px;padding:14px 16px;margin-bottom:12px;transition:box-shadow .2s}
    .pred-card:hover{box-shadow:0 2px 12px rgba(0,0,0,.06)}
    .pred-card.highlight{border-left-color:#dc2626;background:linear-gradient(135deg,#fff,#fef2f2)}
    .pred-card.mid{border-left-color:#d97706;background:linear-gradient(135deg,#fff,#fffbeb)}
    .pred-card-header{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
    .pred-badge{display:inline-block;padding:3px 12px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.3px}
    .pred-badge.impact-大{background:#dc2626;color:#fff}
    .pred-badge.impact-中{background:#d97706;color:#fff}
    .pred-badge.impact-小{background:#e0f2fe;color:#0284c7}
    .pred-badge.conf-高{background:#16a34a;color:#fff}
    .pred-badge.conf-中{background:#fef3c7;color:#92400e}
    .pred-badge.conf-低{background:#f3f4f6;color:#6b7280}
    .accuracy-badge{display:inline-block;background:#e0f2fe;color:#0369a1;font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;margin-left:4px;vertical-align:middle}
    .pred-card-title{font-weight:800;font-size:15px;margin-bottom:8px;line-height:1.5;color:var(--text-main)}
    .highlight .pred-card-title{font-size:16px;color:#991b1b}
    .pred-card-body{font-size:14px;line-height:1.7;color:var(--text-main)}
    .pred-card-body p{margin:6px 0}
    .pred-card-body ul,.pred-card-body ol{margin:6px 0;padding-left:20px}
    .pred-card-body blockquote{border-left:3px solid var(--accent);margin:10px 0;padding:8px 14px;
      background:rgba(0,0,0,.03);border-radius:0 6px 6px 0;font-size:13px;color:var(--text-sub)}
    .forecast-panel.active{display:block}
    .forecast-panel h2,.forecast-panel h3{margin-top:20px;margin-bottom:8px;font-size:1.05rem;font-weight:700;
      color:var(--accent);border-bottom:2px solid var(--accent);padding-bottom:4px}
    .forecast-panel h2:first-child,.forecast-panel h3:first-child{margin-top:0}
    .forecast-panel p{line-height:1.7;margin:8px 0}
    .forecast-panel ul,.forecast-panel ol{margin:8px 0;padding-left:20px;line-height:1.7}
    .forecast-panel hr{border:none;border-top:1px solid var(--border);margin:16px 0}
    .forecast-panel strong{color:var(--text-main)}
    /* テーブル */
    .forecast-panel table{border-collapse:collapse;width:100%;margin:8px 0;display:block;overflow-x:auto}
    .forecast-panel th,.forecast-panel td{border:1px solid var(--border);padding:6px 10px;text-align:left;font-size:.85rem;white-space:normal}
    .forecast-panel th{background:var(--panel)}
    /* サマリー */
    .exec-summary{background:linear-gradient(135deg,#1e3a5f,#1a365d);color:#fff;
      border-radius:12px;padding:20px 24px;margin:16px 0;box-shadow:0 4px 16px rgba(0,0,0,.12)}
    .exec-summary h2{color:#fff;margin:0 0 12px;font-size:18px}
    .exec-summary ol{margin:0;padding:0;list-style:none;counter-reset:ep}
    .exec-summary li{counter-increment:ep;padding:12px 14px;margin-bottom:8px;
      background:rgba(255,255,255,.1);border-radius:8px;border-left:3px solid #f59e0b;position:relative;padding-left:40px}
    .exec-summary li::before{content:counter(ep);position:absolute;left:12px;top:12px;
      width:22px;height:22px;background:#f59e0b;color:#1a365d;border-radius:50%;
      font-size:13px;font-weight:800;display:flex;align-items:center;justify-content:center}
    .exec-summary li p{margin:2px 0;color:rgba(255,255,255,.92);line-height:1.6}
    .exec-summary li strong{color:#fbbf24}
    .exec-summary li em{color:rgba(255,255,255,.7);font-style:normal;font-size:13px}
    .exec-summary hr{display:none}
    /* 付録 */
    details.appendix{margin:12px 0}
    details.appendix summary{cursor:pointer;font-weight:600;color:var(--accent);padding:8px 0}
    details.appendix .forecast-panel{border-radius:8px}
    .no-report{text-align:center;color:var(--text-sub);padding:60px 20px}
    /* 過去レポート */
    .past-reports{margin-top:30px;border-top:1px solid var(--border);padding-top:16px}
    .past-reports h3{margin:0 0 12px;font-size:1rem;font-weight:700;color:var(--text-main)}
    .past-reports details.past-month{margin-bottom:8px;border:1px solid var(--border);
      border-radius:8px;background:var(--panel)}
    .past-reports details.past-month > summary{cursor:pointer;font-weight:600;color:var(--text-main);
      padding:10px 14px;list-style:none;display:flex;align-items:center;gap:8px}
    .past-reports details.past-month > summary::-webkit-details-marker{display:none}
    .past-reports details.past-month > summary::before{content:"\25B6";display:inline-block;
      font-size:.7em;color:var(--accent);transition:transform .15s}
    .past-reports details.past-month[open] > summary::before{transform:rotate(90deg)}
    .past-reports details.past-month > summary .month-count{margin-left:auto;font-size:.8rem;
      font-weight:500;color:var(--text-sub)}
    .past-reports ul{list-style:none;margin:0;padding:0 14px 12px;display:flex;flex-wrap:wrap;gap:8px}
    .past-reports li a{display:inline-block;padding:4px 12px;border:1px solid var(--border);
      border-radius:6px;font-size:.85rem;text-decoration:none;color:var(--text-main);background:var(--bg)}
    .past-reports li a:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
    /* === モバイル (640px以下) === */
    @media(max-width:640px){
      .forecast-tabs{gap:3px}
      .forecast-tabs button{padding:8px 14px;font-size:.85rem;min-height:44px}
      .forecast-panel{padding:10px;border-radius:0 6px 6px 6px}
      .forecast-panel table{font-size:.78rem}
      .forecast-panel th,.forecast-panel td{padding:4px 6px}
      .exec-summary{padding:14px 16px;border-radius:10px;margin:10px 0}
      .exec-summary li{padding:10px 12px 10px 36px}
      .exec-summary li::before{left:8px;top:10px;width:20px;height:20px;font-size:12px}
      .exec-summary h2{font-size:16px}
      details.appendix summary{font-size:.9rem;padding:6px 0}
    }
  </style>
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","name":"未来予測レポート","description":"直近ニュースに基づくAI未来予測レポート。3つの時間軸と技術者・経営者・消費者の3視点で分析。","url":"/daily-tech-trend/forecast/","isPartOf":{"@type":"WebSite","name":"Daily Tech Trend","url":"/daily-tech-trend/"}}</script>
</head>
<body>
  <h1>未来予測レポート</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/forecast/hits/" class="{{ 'active' if page=='forecast_hits' else '' }}">予想的中</a>
    <a href="/daily-tech-trend/diff/" class="">差分</a>
    <a href="/daily-tech-trend/entity/" class="">企業別</a>
    <a href="/daily-tech-trend/exec/" class="">エグゼクティブ</a>
    <a href="/daily-tech-trend/search.html" class="">🔍 検索</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
    <a href="/daily-tech-trend/feed.xml" class="" title="RSSフィード">RSS</a>
  </div>

  <div class="summary-card" style="margin:16px 0">
    <div class="summary-grid">
      <div class="summary-item"><div class="k">Generated (JST)</div><div class="v">{{ generated_at }}</div></div>
      <div class="summary-item"><div class="k">レポート日付</div><div class="v">{{ report_date }}</div></div>
      {% if accuracy_score is not none and accuracy_score != "" %}
      <div class="summary-item"><div class="k">このレポートの的中率</div><div class="v">{{ accuracy_score }}%</div></div>
      {% endif %}
      {% if avg_accuracy is not none and avg_accuracy != "" %}
      <div class="summary-item"><div class="k">過去平均的中率</div><div class="v">{{ avg_accuracy }}%</div></div>
      {% endif %}
    </div>
  </div>

  {% if has_report %}

  <!-- エグゼクティブサマリー -->
  <div class="exec-summary">
    <h2 style="margin:0 0 8px">今週の最重要ポイント</h2>
    {{ executive_summary_html }}
  </div>

  <!-- 未来予測（時間軸タブ） -->
  <h2>未来予測</h2>
  <div class="forecast-tabs" id="pred-tabs">
    {% for horizon in prediction_keys %}
    <button onclick="switchTab('pred', '{{ loop.index0 }}')" class="{{ 'active' if loop.first else '' }}"
            id="pred-tab-{{ loop.index0 }}">{{ horizon }}{% if horizon_accuracy.get(horizon) is not none %} <span class="accuracy-badge">{{ horizon_accuracy[horizon] }}%</span>{% endif %}</button>
    {% endfor %}
  </div>
  {% for horizon in prediction_keys %}
  <div class="forecast-panel {{ 'active' if loop.first else '' }}" id="pred-panel-{{ loop.index0 }}">
    {% if not prediction_items[horizon] %}
    <p class="pred-empty-note" style="color:var(--text-sub);padding:16px;text-align:center;border:1px dashed var(--border);border-radius:8px;">
      ※ この時間軸の予測は今回生成されませんでした（LLM応答の解析に失敗した可能性があります）。
    </p>
    {% else %}
    {% for item in prediction_items[horizon] %}
    <div class="pred-card{{ ' highlight' if item.impact=='大' and item.confidence=='高' else ' mid' if item.impact=='大' or item.confidence=='高' else '' }}">
      <div class="pred-card-header">
        {% if item.impact %}<span class="pred-badge impact-{{ item.impact }}">影響度: {{ item.impact }}</span>{% endif %}
        {% if item.confidence %}<span class="pred-badge conf-{{ item.confidence }}">確信度: {{ item.confidence }}</span>{% endif %}
      </div>
      {% if item.title %}<div class="pred-card-title">{{ item.title }}</div>{% endif %}
      <div class="pred-card-body">{{ item.body_html }}</div>
    </div>
    {% endfor %}
    {% endif %}
  </div>
  {% endfor %}

  <!-- 検証済み予測レポート -->
  {% if checked_report_html %}
  <details class="appendix">
    <summary>検証済み予測レポート（ファクトチェック反映版）</summary>
    <div class="forecast-panel active">{{ checked_report_html }}</div>
  </details>
  {% endif %}

  <!-- 3視点分析（タブ） -->
  <h2>3視点分析</h2>
  <div class="forecast-tabs" id="persp-tabs">
    {% for name in perspective_keys %}
    <button onclick="switchTab('persp', '{{ loop.index0 }}')" class="{{ 'active' if loop.first else '' }}"
            id="persp-tab-{{ loop.index0 }}">{{ name }}視点</button>
    {% endfor %}
  </div>
  {% for name in perspective_keys %}
  <div class="forecast-panel {{ 'active' if loop.first else '' }}" id="persp-panel-{{ loop.index0 }}">
    {{ perspective_htmls[name] }}
  </div>
  {% endfor %}

  <!-- 付録 -->
  {% if appendix_fc_html %}
  <details class="appendix">
    <summary>付録A: ファクトチェック詳細</summary>
    <div class="forecast-panel active">{{ appendix_fc_html }}</div>
  </details>
  {% endif %}
  {% if appendix_news_html %}
  <details class="appendix">
    <summary>付録B: 収集ニュース一覧</summary>
    <div class="forecast-panel active">{{ appendix_news_html }}</div>
  </details>
  {% endif %}

  <!-- 過去レポート一覧（月別折りたたみ） -->
  {% if past_reports_grouped %}
  <div class="past-reports">
    <h3>過去のレポート</h3>
    {% for grp in past_reports_grouped %}
    <details class="past-month"{% if loop.first %} open{% endif %}>
      <summary>{{ grp.label }}<span class="month-count">{{ grp.entries|length }}件</span></summary>
      <ul>
        {% for pr in grp.entries %}
        <li><a href="{{ link_prefix }}{{ pr.date }}/">{{ pr.date }}</a></li>
        {% endfor %}
      </ul>
    </details>
    {% endfor %}
  </div>
  {% endif %}

  {% else %}
  <div class="no-report">
    <p style="font-size:1.2rem">未来予測レポートはまだ生成されていません</p>
    <p>ローカル環境で未来予測パイプラインを実行し、<br>
       <code>python src/forecast_import.py &lt;レポート.md&gt;</code> でインポートしてください。</p>
  </div>
  {% endif %}

  <script src="{{ common_js_src }}" defer></script>
  <script>
    // タブ状態は URL クエリで共有可能にする:
    //   ?pred=1  → 予測タブ の 2番目 (0-indexed)
    //   ?persp=engineer|manager|consumer → 3視点タブ
    //   ?persp=0|1|2 も互換扱い
    var PERSP_NAMES = ['engineer','manager','consumer'];
    var PERSP_LABELS = ['技術者','経営者','消費者'];

    function switchTab(group, idx, opts) {
      idx = parseInt(idx, 10);
      document.querySelectorAll('#' + group + '-tabs button').forEach(function(b, i) {
        b.classList.toggle('active', i == idx);
      });
      document.querySelectorAll('[id^="' + group + '-panel-"]').forEach(function(p, i) {
        p.classList.toggle('active', i == idx);
      });
      // URL 同期（history.replaceState で余分な履歴を残さない）
      if (!opts || opts.updateUrl !== false) {
        try {
          var url = new URL(window.location.href);
          var val = idx;
          if (group === 'persp' && PERSP_NAMES[idx]) val = PERSP_NAMES[idx];
          url.searchParams.set(group, val);
          window.history.replaceState(null, '', url.toString());
        } catch (e) { /* noop */ }
      }
    }

    function _initTabFromUrl(group) {
      try {
        var url = new URL(window.location.href);
        var v = url.searchParams.get(group);
        if (v === null) return;
        var idx = parseInt(v, 10);
        if (group === 'persp' && isNaN(idx)) {
          idx = PERSP_NAMES.indexOf(v);
          if (idx < 0) idx = PERSP_LABELS.indexOf(v);
        }
        if (!isNaN(idx) && idx >= 0) switchTab(group, idx, {updateUrl: false});
      } catch (e) { /* noop */ }
    }

    document.addEventListener('DOMContentLoaded', function(){
      if (window.DTTCommon) window.DTTCommon.setupCommon('forecast');
      _initTabFromUrl('pred');
      _initTabFromUrl('persp');
    });
  </script>
</body>
</html>
"""


def _group_past_reports_by_month(reports):
    """過去レポートを年月単位でグルーピングして降順リストを返す。

    入力: [{"date": "2026-05-04"}, ...] (日付降順を想定)
    出力: [{"ym": "2026-05", "label": "2026年5月", "entries": [...]}, ...]
    ※ Jinja2 で dict.items メソッドと衝突するため、キー名は entries にする。
    """
    from collections import OrderedDict
    groups = OrderedDict()
    for r in reports:
        date_str = r.get("date") or ""
        if len(date_str) < 7:
            continue
        ym = date_str[:7]
        groups.setdefault(ym, []).append(r)
    out = []
    for ym, entries in groups.items():
        try:
            year = int(ym[:4])
            month = int(ym[5:7])
            label = f"{year}年{month}月"
        except ValueError:
            label = ym
        out.append({"ym": ym, "label": label, "entries": entries})
    return out


def render_forecast_page(out_dir, generated_at, cur):
    """未来予測ページを生成する"""
    from pathlib import Path
    from forecast_parser import parse_forecast_markdown, ForecastReport

    def _fix_markdown_tables(text):
        """テーブル行間の空行を除去し、ヘッダー区切り行がなければ挿入する"""
        lines = text.split("\n")
        out = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                # テーブルブロックの開始 — 連続するテーブル行を収集
                table_lines = [stripped]
                i += 1
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith("|") and s.endswith("|"):
                        table_lines.append(s)
                        i += 1
                    elif s == "":
                        # 空行の次がテーブル行ならスキップして継続
                        if i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
                            i += 1
                            continue
                        break
                    else:
                        break
                # 区切り行チェック（2行目が | --- | --- | 形式か）
                has_sep = len(table_lines) > 1 and all(
                    c in "-| :" for c in table_lines[1]
                )
                if not has_sep and len(table_lines) >= 1:
                    # 1行目の列数に合わせて区切り行を挿入
                    ncols = table_lines[0].count("|") - 1
                    sep = "| " + " | ".join(["---"] * max(ncols, 1)) + " |"
                    table_lines.insert(1, sep)
                out.extend(table_lines)
                out.append("")
            else:
                out.append(line)
                i += 1
        return "\n".join(out)

    try:
        import mistune
        _md_renderer = mistune.create_markdown(plugins=["table"])
        def md_to_html(text):
            return _md_renderer(_fix_markdown_tables(text))
    except ImportError:
        import html as _html

        def md_to_html(text):
            """mistune未インストール時の簡易Markdown→HTML変換"""
            text = _fix_markdown_tables(text)
            lines = _html.escape(text).split("\n")
            out = []
            in_list = False
            in_table = False
            for line in lines:
                stripped = line.strip()
                # 空行
                if not stripped:
                    if in_list:
                        out.append("</ul>")
                        in_list = False
                    if in_table:
                        out.append("</tbody></table>")
                        in_table = False
                    out.append("")
                    continue
                # 見出し
                if stripped.startswith("### "):
                    out.append(f"<h3>{stripped[4:]}</h3>")
                    continue
                if stripped.startswith("## "):
                    out.append(f"<h2>{stripped[3:]}</h2>")
                    continue
                if stripped.startswith("# "):
                    out.append(f"<h1>{stripped[2:]}</h1>")
                    continue
                # 水平線
                if stripped in ("---", "***", "___"):
                    out.append("<hr>")
                    continue
                # テーブル区切り行
                if stripped.startswith("|") and set(stripped.replace("|", "").replace("-", "").replace(" ", "")) == set():
                    continue
                # テーブル行
                if stripped.startswith("|") and stripped.endswith("|"):
                    cells = [c.strip() for c in stripped.strip("|").split("|")]
                    if not in_table:
                        in_table = True
                        out.append('<table class="source-table"><tbody>')
                    out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
                    continue
                # 引用ブロック
                if stripped.startswith("&gt; "):
                    content = stripped[5:]
                    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
                    out.append(f"<blockquote>{content}</blockquote>")
                    continue
                # リスト
                if stripped.startswith("- ") or stripped.startswith("* "):
                    if not in_list:
                        in_list = True
                        out.append("<ul>")
                    content = stripped[2:]
                    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
                    out.append(f"<li>{content}</li>")
                    continue
                # 番号付きリスト
                m_ol = re.match(r"^(\d+)\.\s+(.+)", stripped)
                if m_ol:
                    content = m_ol.group(2)
                    content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                    content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
                    out.append(f"<p>{m_ol.group(1)}. {content}</p>")
                    continue
                # 通常段落（太字・斜体変換）
                if in_list:
                    out.append("</ul>")
                    in_list = False
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False
                p = stripped
                p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
                p = re.sub(r"\*(.+?)\*", r"<em>\1</em>", p)
                out.append(f"<p>{p}</p>")
            if in_list:
                out.append("</ul>")
            if in_table:
                out.append("</tbody></table>")
            return "\n".join(out)

    # 最新レポートを取得
    cur.execute("""
        SELECT report_date, file_path, executive_summary, accuracy_score
        FROM forecast_reports
        ORDER BY report_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    # 過去平均精度スコア
    cur.execute("""
        SELECT AVG(accuracy_score) FROM forecast_reports
        WHERE accuracy_score IS NOT NULL
    """)
    avg_row = cur.fetchone()
    avg_accuracy = round(avg_row[0] * 100, 1) if avg_row and avg_row[0] is not None else ""

    # 時間軸別の的中率（最新レポートの最新ラウンド）
    horizon_accuracy = {}
    try:
        cur.execute("""
            SELECT fv.horizon, fv.accuracy_score
            FROM forecast_verifications fv
            INNER JOIN (
                SELECT report_date, horizon, MAX(verification_round) AS max_round
                FROM forecast_verifications
                WHERE report_date = (SELECT report_date FROM forecast_reports ORDER BY report_date DESC LIMIT 1)
                GROUP BY report_date, horizon
            ) latest
            ON fv.report_date = latest.report_date
               AND fv.horizon = latest.horizon
               AND fv.verification_round = latest.max_round
        """)
        for h, score in cur.fetchall():
            horizon_accuracy[h] = round(score * 100, 1) if score is not None else None
    except Exception as e:
        _log_render_error("forecast.horizon_accuracy_query", e, level="warning")

    # 過去レポート一覧
    cur.execute("""
        SELECT report_date FROM forecast_reports
        ORDER BY report_date DESC
    """)
    past_reports = [{"date": r[0]} for r in cur.fetchall()]

    has_report = False
    report = ForecastReport()
    report_date = "-"
    accuracy_score = ""

    if row:
        report_date = row[0]
        file_path = Path(row[1])
        if row[3] is not None:
            accuracy_score = round(row[3] * 100, 1)
        if file_path.exists():
            md_text = file_path.read_text(encoding="utf-8")
            report = parse_forecast_markdown(md_text)
            has_report = True

    # Markdown → HTML 変換
    executive_summary_html = md_to_html(report.executive_summary) if report.executive_summary else ""
    checked_report_html = md_to_html(report.checked_report) if report.checked_report else ""
    appendix_fc_html = md_to_html(report.appendix_factcheck) if report.appendix_factcheck else ""
    appendix_news_html = md_to_html(report.appendix_news) if report.appendix_news else ""

    from forecast_parser import parse_prediction_items

    prediction_keys = list(report.predictions.keys())
    impact_order = {"大": 0, "中": 1, "小": 2}
    conf_order = {"高": 0, "中": 1, "低": 2}

    # バッジで表示済みの影響度・確信度行を本文から除去するパターン
    _dup_badge_re = re.compile(
        r"\*{0,2}影響度[:：]\s*\S+\s*[/／]\s*確信度[:：]\s*\S+\*{0,2}\s*\n?"
    )

    # 空殻プレースホルダ（"### 1. 予測1" 見出し + 中身空 "- **予測内容**：" と "> **根拠**:"）を
    # 既存レポートで救済するための判定関数。title が "予測N" のデフォルト名かつ body から
    # バッジ・空の定型行・水平線を除くと実内容が残らない場合は、empty-horizon 扱いへ寄せる。
    _empty_body_re = re.compile(r"-\s*\*{0,2}予測内容\*{0,2}[:：]\s*$|>\s*\*{0,2}根拠\*{0,2}[:：]\s*$", re.MULTILINE)
    # Markdown の水平線（--- / *** / ___）やファイル末尾に付く区切りも除去対象にする
    _hr_line_re = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
    _placeholder_title_re = re.compile(r"^予測\d+$")

    def _is_empty_placeholder(item, body_after_strip):
        """生成失敗時に残る "### 1. 予測1" 空殻を検出する。"""
        if not _placeholder_title_re.match((item.title or "").strip()):
            return False
        residual = _empty_body_re.sub("", body_after_strip)
        residual = _hr_line_re.sub("", residual).strip()
        return residual == ""

    prediction_items = {}
    for k, v in report.predictions.items():
        items = parse_prediction_items(v)
        rendered = []
        for item in items:
            body = _dup_badge_re.sub("", item.body).strip()
            if _is_empty_placeholder(item, body):
                # 空殻アイテムは描画せずスキップ → 結果として horizon が空なら
                # Jinja テンプレート側のフォールバック注記が表示される。
                continue
            rendered.append({
                "impact": item.impact,
                "confidence": item.confidence,
                "title": item.title,
                "body_html": md_to_html(body),
            })
        rendered.sort(key=lambda x: (impact_order.get(x["impact"], 2),
                                      conf_order.get(x["confidence"], 2)))
        prediction_items[k] = rendered

    perspective_keys = list(report.perspectives.keys())
    perspective_htmls = {k: md_to_html(v) for k, v in report.perspectives.items()}

    assets = build_asset_paths()
    forecast_html = Template(FORECAST_HTML).render(
        page="forecast",
        common_css_href=assets["common_css_href"],
        common_js_src=assets["common_js_src"],
        generated_at=generated_at,
        report_date=report_date,
        has_report=has_report,
        executive_summary_html=executive_summary_html,
        prediction_keys=prediction_keys,
        prediction_items=prediction_items,
        checked_report_html=checked_report_html,
        perspective_keys=perspective_keys,
        perspective_htmls=perspective_htmls,
        appendix_fc_html=appendix_fc_html,
        appendix_news_html=appendix_news_html,
        past_reports_grouped=_group_past_reports_by_month(
            past_reports[1:] if len(past_reports) > 1 else []
        ),
        link_prefix="./",
        accuracy_score=accuracy_score,
        avg_accuracy=avg_accuracy,
        horizon_accuracy=horizon_accuracy,
    )

    forecast_dir = Path(out_dir) / "forecast"
    forecast_dir.mkdir(exist_ok=True)
    (forecast_dir / "index.html").write_text(forecast_html, encoding="utf-8")
    print(f"  forecast page: {forecast_dir / 'index.html'}")

    # 過去レポートの個別HTML生成（最新を除く全件）
    past_to_render = past_reports[1:] if len(past_reports) > 1 else []
    for pr in past_to_render:
        pr_date = pr["date"]
        cur.execute("""
            SELECT report_date, file_path, executive_summary, accuracy_score
            FROM forecast_reports WHERE report_date = ?
        """, (pr_date,))
        pr_row = cur.fetchone()
        if not pr_row:
            continue
        pr_file = Path(pr_row[1])
        if not pr_file.exists():
            continue
        pr_md = pr_file.read_text(encoding="utf-8")
        pr_report = parse_forecast_markdown(pr_md)
        pr_acc = round(pr_row[3] * 100, 1) if pr_row[3] is not None else ""

        pr_exec_html = md_to_html(pr_report.executive_summary) if pr_report.executive_summary else ""
        pr_checked_html = md_to_html(pr_report.checked_report) if pr_report.checked_report else ""
        pr_appx_fc = md_to_html(pr_report.appendix_factcheck) if pr_report.appendix_factcheck else ""
        pr_appx_news = md_to_html(pr_report.appendix_news) if pr_report.appendix_news else ""

        pr_pred_keys = list(pr_report.predictions.keys())
        pr_pred_items = {}
        for k, v in pr_report.predictions.items():
            pitems = parse_prediction_items(v)
            pr_rendered = []
            for pi in pitems:
                body = _dup_badge_re.sub("", pi.body).strip()
                # 現在レポートと同じく空殻プレースホルダはスキップ
                if _is_empty_placeholder(pi, body):
                    continue
                pr_rendered.append({
                    "impact": pi.impact, "confidence": pi.confidence,
                    "title": pi.title, "body_html": md_to_html(body),
                })
            pr_rendered.sort(key=lambda x: (impact_order.get(x["impact"], 2),
                                             conf_order.get(x["confidence"], 2)))
            pr_pred_items[k] = pr_rendered

        pr_persp_keys = list(pr_report.perspectives.keys())
        pr_persp_htmls = {k: md_to_html(v) for k, v in pr_report.perspectives.items()}

        # 過去レポートのリンクは現在と同じ一覧を使う
        other_past = [p for p in past_reports if p["date"] != pr_date]
        pr_html = Template(FORECAST_HTML).render(
            page="forecast",
            common_css_href=assets["common_css_href"],
            common_js_src=assets["common_js_src"],
            generated_at=generated_at,
            report_date=pr_date,
            has_report=True,
            executive_summary_html=pr_exec_html,
            prediction_keys=pr_pred_keys,
            prediction_items=pr_pred_items,
            checked_report_html=pr_checked_html,
            perspective_keys=pr_persp_keys,
            perspective_htmls=pr_persp_htmls,
            appendix_fc_html=pr_appx_fc,
            appendix_news_html=pr_appx_news,
            past_reports_grouped=_group_past_reports_by_month(other_past),
            link_prefix="../",
            accuracy_score=pr_acc,
            avg_accuracy=avg_accuracy,
            # 過去レポートでは時間軸別的中率を表示しない（現在レポート用の集計）。
            # 未渡しだと Jinja の `horizon_accuracy.get()` で UndefinedError になるため空を渡す。
            horizon_accuracy={},
        )
        pr_dir = forecast_dir / pr_date
        pr_dir.mkdir(exist_ok=True)
        (pr_dir / "index.html").write_text(pr_html, encoding="utf-8")
    if past_to_render:
        print(f"  forecast past pages: {len(past_to_render)}件生成")


FORECAST_HITS_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>予想的中 | Daily Tech Trend</title>
  <meta name="description" content="過去の未来予測のうち、後日のニュースで的中が確認された予測をまとめたページ。">
  <link rel="canonical" href="/daily-tech-trend/forecast/hits/">
  <link rel="alternate" type="application/rss+xml" title="Daily Tech Trend RSS" href="/daily-tech-trend/feed.xml">
  <meta property="og:title" content="予想的中 | Daily Tech Trend">
  <meta property="og:description" content="過去の未来予測のうち、後日のニュースで的中が確認された予測をまとめたページ。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="/daily-tech-trend/forecast/hits/">
  <meta property="og:site_name" content="Daily Tech Trend">
  <meta property="og:locale" content="ja_JP">
  <meta name="twitter:card" content="summary">
  <link rel="stylesheet" href="{{ common_css_href }}">
  <style>
    .hit-summary{margin:16px 0;padding:12px 16px;border:1px solid var(--border);border-radius:8px;background:var(--panel)}
    .hit-summary .summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
    .hit-summary .k{font-size:.78rem;color:var(--text-sub)}
    .hit-summary .v{font-size:1.1rem;font-weight:700;color:var(--accent)}
    .hit-horizon-section{margin:24px 0}
    .hit-horizon-section > h2{margin:0 0 10px;font-size:1.1rem;padding-bottom:4px;border-bottom:2px solid var(--accent)}
    .hit-card{border:1px solid var(--border);border-left:4px solid #2ea043;border-radius:6px;
              padding:10px 14px;margin:8px 0;background:var(--panel)}
    .hit-card.partial{border-left-color:#d29922}
    .hit-card-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:4px;font-size:.78rem;color:var(--text-sub)}
    .hit-card-head .badge{background:#2ea043;color:#fff;padding:2px 8px;border-radius:10px;font-weight:700}
    .hit-card-head .badge.partial{background:#d29922}
    .hit-card-head .acc{color:#2ea043;font-weight:700}
    .hit-card.partial .hit-card-head .acc{color:#d29922}
    .hit-card-title{font-weight:700;font-size:.98rem;margin:4px 0}
    .hit-card-reason{font-size:.88rem;line-height:1.6;color:var(--text-main)}
    .hit-empty{padding:24px;text-align:center;color:var(--text-sub)}
  </style>
  <script src="{{ common_js_src }}" defer></script>
</head>
<body>
  <h1>予想的中</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/forecast/hits/" class="{{ 'active' if page=='forecast_hits' else '' }}">予想的中</a>
    <a href="/daily-tech-trend/diff/" class="">差分</a>
    <a href="/daily-tech-trend/entity/" class="">企業別</a>
    <a href="/daily-tech-trend/exec/" class="">エグゼクティブ</a>
    <a href="/daily-tech-trend/search.html" class="">🔍 検索</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
    <a href="/daily-tech-trend/feed.xml" class="" title="RSSフィード">RSS</a>
  </div>

  <div class="hit-summary">
    <div class="summary-grid">
      <div><div class="k">Generated (JST)</div><div class="v" style="font-size:.9rem;color:var(--text-main)">{{ generated_at }}</div></div>
      <div><div class="k">的中した予測数</div><div class="v">{{ total_hits }}</div></div>
      <div><div class="k">検証対象レポート数</div><div class="v">{{ report_count }}</div></div>
    </div>
    <p style="margin:10px 0 0;font-size:.82rem;color:var(--text-sub)">
      過去の未来予測をその後のニュースで照合し、LLMが「的中」または「部分的中」（的中度 &gt; 0）と判定した項目を抽出しています。
      各項目にはレポート日・時間軸・的中度スコアを表示します。
    </p>
  </div>

  {% if total_hits == 0 %}
  <div class="hit-empty">まだ的中と判定された予測はありません。</div>
  {% else %}
    {% for horizon, hits in hits_by_horizon.items() %}
    <section class="hit-horizon-section">
      <h2>{{ horizon }}（{{ hits|length }}件）</h2>
      {% for h in hits %}
      <div class="hit-card{% if h.label == '部分的中' %} partial{% endif %}">
        <div class="hit-card-head">
          <span class="badge{% if h.label == '部分的中' %} partial{% endif %}">{{ h.label }}</span>
          <span>レポート日: {{ h.report_date }}</span>
          {% if h.accuracy is not none %}<span class="acc">的中度: {{ h.accuracy }}</span>{% endif %}
          <span>検証日: {{ h.verified_at }}</span>
        </div>
        <div class="hit-card-title">{{ h.title }}</div>
        {% if h.reason %}<div class="hit-card-reason">{{ h.reason }}</div>{% endif %}
        {% if h.evidence_title %}<div class="hit-evidence" style="margin-top:6px;font-size:.85rem;color:var(--text-sub)">根拠記事: <b>{{ h.evidence_title }}</b>{% if h.evidence_source %} <span style="color:#6b7280">({{ h.evidence_source }})</span>{% endif %}</div>{% endif %}
      </div>
      {% endfor %}
    </section>
    {% endfor %}
  {% endif %}
</body>
</html>
"""


def render_forecast_hits_page(out_dir, generated_at, cur):
    """的中と判定された予測のみを集約したページを生成"""
    from pathlib import Path

    # 各(report_date, horizon)の最新ラウンドのみ参照
    cur.execute("""
        SELECT fv.report_date, fv.horizon, fv.verdict_json, fv.verified_at
        FROM forecast_verifications fv
        INNER JOIN (
            SELECT report_date, horizon, MAX(verification_round) AS max_round
            FROM forecast_verifications
            GROUP BY report_date, horizon
        ) latest
        ON fv.report_date = latest.report_date
           AND fv.horizon = latest.horizon
           AND fv.verification_round = latest.max_round
        ORDER BY fv.report_date DESC
    """)
    rows = cur.fetchall()

    # 時間軸の表示順
    horizon_order = ["1週間後", "1〜6ヶ月後", "1年後"]
    hits_by_horizon = {h: [] for h in horizon_order}
    report_dates_with_hits = set()
    total_hits = 0

    for report_date, horizon, verdict_json, verified_at in rows:
        if not verdict_json:
            continue
        try:
            verdicts = json.loads(verdict_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(verdicts, list):
            continue
        for v in verdicts:
            if not isinstance(v, dict):
                continue
            raw_verdict = v.get("verdict")
            acc = v.get("accuracy")
            try:
                acc_num = float(acc) if acc is not None else None
            except (TypeError, ValueError):
                acc_num = None
            # 的中判定: verdict が "的中"/"部分的中"、または accuracy が 0 超
            # （LLMが verdict="未確定" でも accuracy=0.5 を返すケースを救済）
            is_hit = raw_verdict in ("的中", "部分的中")
            if not is_hit and acc_num is not None and acc_num > 0:
                is_hit = True
            if not is_hit:
                continue
            # 表示用ラベル: accuracy に応じて自動判定
            if acc_num is not None and acc_num >= 1.0:
                label = "的中"
            elif acc_num is not None and acc_num > 0:
                label = "部分的中"
            else:
                label = raw_verdict or "的中"
            acc_disp = round(acc_num, 2) if acc_num is not None else None
            verified_disp = (verified_at or "")[:10]
            entry = {
                "title": v.get("title", "(タイトル不明)"),
                "reason": v.get("reason", ""),
                "accuracy": acc_disp,
                "label": label,
                "report_date": report_date,
                "verified_at": verified_disp,
                # 検証時に LLM が抽出した的中根拠（新機能）。古い検証結果には無いため optional。
                "evidence_title": v.get("evidence_title", "") or "",
                "evidence_source": v.get("evidence_source", "") or "",
            }
            hits_by_horizon.setdefault(horizon, []).append(entry)
            report_dates_with_hits.add(report_date)
            total_hits += 1

    # 空の時間軸を除外し、表示順を確定
    ordered = {}
    for h in horizon_order:
        if hits_by_horizon.get(h):
            ordered[h] = hits_by_horizon[h]
    for h, lst in hits_by_horizon.items():
        if h not in ordered and lst:
            ordered[h] = lst

    assets = build_asset_paths()
    html = Template(FORECAST_HITS_HTML).render(
        page="forecast_hits",
        common_css_href=assets["common_css_href"],
        common_js_src=assets["common_js_src"],
        generated_at=generated_at,
        total_hits=total_hits,
        report_count=len(report_dates_with_hits),
        hits_by_horizon=ordered,
    )

    hits_dir = Path(out_dir) / "forecast" / "hits"
    hits_dir.mkdir(parents=True, exist_ok=True)
    (hits_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  forecast hits page: {hits_dir / 'index.html'} ({total_hits}件)")


# --- RSS / 検索ページは render_feeds.py に分離。後方互換のため再エクスポート ---
from render_feeds import (
    FEED_DESCRIPTION,
    FEED_SITE_URL,
    FEED_TITLE,
    SEARCH_HTML,
    _rss_escape,
    _rss_rfc822,
    render_rss_feed as _render_rss_feed_impl,
    render_search_page as _render_search_page_impl,
    render_sitemap as _render_sitemap_impl,
    render_json_api as _render_json_api_impl,
)


def render_sitemap(out_dir: Path, cur) -> None:
    """互換ラッパー: render_feeds.render_sitemap へ委譲。"""
    return _render_sitemap_impl(out_dir, cur)


def render_json_api(out_dir: Path, cur) -> None:
    """互換ラッパー: render_feeds.render_json_api へ委譲。"""
    return _render_json_api_impl(out_dir, cur)


def render_rss_feed(out_dir: Path, generated_at: str, cur, limit: int = 30) -> None:
    """互換ラッパー: render_feeds.render_rss_feed へ委譲。"""
    return _render_rss_feed_impl(out_dir, generated_at, cur, limit=limit)


def render_search_page(out_dir: Path, generated_at: str, cur, limit: int = 3000) -> None:
    """互換ラッパー: render_feeds.render_search_page へ委譲。"""
    assets = build_asset_paths()
    return _render_search_page_impl(
        out_dir,
        generated_at,
        cur,
        limit=limit,
        common_css_href=assets["common_css_href"],
        nav_prefix=assets["nav_prefix"],
    )


def main():
    t0 = _now_sec()
    print("[TIME] step=render start")

    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)

    conn = connect()
    cur = conn.cursor()
    # categories: YAML -> DB -> other
    categories = load_categories_from_yaml()
    if not categories:
        categories = build_categories_fallback(cur)
    categories = ensure_category_coverage(cur, categories)

    category_order = [
        "system",
        "manufacturing",
        "smart_factory",
        "market",
        "environment",
        "quality",
        "maintenance",
        "policy",
        "decarbonization_ops",
        "security",
        "standards",
        "ai",
        "dev",
        "other",
    ]
    order_index = {cat_id: idx for idx, cat_id in enumerate(category_order)}
    # YAML定義から削除されたカテゴリ（DBに残存データがあっても非表示）
    allowed_cats = set(category_order)
    categories = [c for c in categories if c["id"] in allowed_cats]
    categories = sorted(
        categories,
        key=lambda c: (order_index.get(c["id"], len(category_order)), c["id"]),
    )

    TECH_EXCLUDE = {"news"}
    tech_categories = [c for c in categories if c["id"] not in TECH_EXCLUDE]

    # tech側で使うのは tech_categories
    cat_name = {c["id"]: c["name"] for c in tech_categories}

    topics_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    hot_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    # 48h cutoff（UTCでSQLite互換の "YYYY-MM-DD HH:MM:SS"）
    cutoff_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")

    LIMIT_PER_CAT = 15
    HOT_TOP_N = 5

    for cat in tech_categories:
        cat_id = cat["id"]

        # (A) 注目TOP5（48h増分、published_atベース）
        if cat_id == "other":
            cur.execute(
                """
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS ttitle,
                  COUNT(ta.article_id) AS total_count,
                  SUM(
                    CASE
                      WHEN datetime(
                        substr(
                          replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),
                          1, 19
                        )
                      ) >= datetime(?) THEN 1
                      ELSE 0
                    END
                  ) AS recent_count,
                  MAX(
                    datetime(
                      substr(
                        replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),
                        1, 19
                      )
                    )
                  ) AS article_date
                FROM topics t
                JOIN topic_articles ta ON ta.topic_id = t.id
                JOIN articles a ON a.id = ta.article_id
                WHERE (t.category IS NULL OR t.category = '')
                  AND COALESCE(t.category,'') <> 'news'
                  AND COALESCE(a.kind,'') <> 'news'
                GROUP BY t.id
                HAVING recent_count > 0
                ORDER BY recent_count DESC, total_count DESC, t.id DESC
                LIMIT ?
                """,
                (cutoff_48h, HOT_TOP_N),
            )


        else:
            cur.execute(
                """
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS ttitle,
                  COUNT(ta.article_id) AS total_count,
                  SUM(
                    CASE
                      WHEN datetime(
                        substr(
                          replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),
                          1, 19
                        )
                      ) >= datetime(?) THEN 1
                      ELSE 0
                    END
                  ) AS recent_count,
                  MAX(
                    datetime(
                      substr(
                        replace(replace(COALESCE(NULLIF(a.published_at,''), a.fetched_at),'T',' '),'+00:00',''),
                        1, 19
                      )
                    )
                  ) AS article_date
                FROM topics t
                JOIN topic_articles ta ON ta.topic_id = t.id
                JOIN articles a ON a.id = ta.article_id
                WHERE t.category = ?
                  AND COALESCE(t.category,'') <> 'news'
                  AND COALESCE(a.kind,'') <> 'news'
                GROUP BY t.id
                HAVING recent_count > 0
                ORDER BY recent_count DESC, total_count DESC, t.id DESC
                LIMIT ?
                """,
                (cutoff_48h, cat_id, HOT_TOP_N),
            )


        rows = cur.fetchall()
        hot_by_cat[cat_id] = [
            {"id": tid, "title": clean_for_html(title), "articles": int(total), "recent": int(recent),"date": article_date or ""}
            for (tid, title, total, recent, article_date) in rows
        ]

        # ★ 注目TOP5の並びも完全決定（揺れ防止）
        hot_by_cat[cat_id] = sorted(
            hot_by_cat[cat_id],
            key=lambda x: (-x["recent"], -x["articles"], x["id"]),
        )

        # (B) 一覧（topics + insights + 代表URL + 48h増分）
        if cat_id == "other":
            cur.execute(
                """
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS title,
                  (
                      SELECT a2.url
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE
                            WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                            ELSE 1
                          END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                        LIMIT 1

                    ) AS url,
                    (
                      SELECT COALESCE(
                        NULLIF(a2.published_at,''),
                        a2.fetched_at
                      )
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                        CASE
                          WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                          ELSE 1
                        END,
                        datetime(a2.fetched_at) DESC,
                        datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                        a2.url ASC
                      LIMIT 1
                    ) AS article_date,
                  (
                      SELECT COALESCE(SUM(
                        CASE
                          WHEN datetime(
                            substr(
                              replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                              1, 19
                            )
                          ) >= datetime(?) THEN 1
                          ELSE 0
                        END
                      ), 0)
                      FROM topic_articles ta3
                      JOIN articles a3 ON a3.id = ta3.article_id
                      WHERE ta3.topic_id = t.id
                    ) AS recent,
                  (
                      SELECT a2.source
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0 ELSE 1 END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                      LIMIT 1
                    ) AS source,
                  i.importance,
                  i.summary,
                  i.key_points,
                  i.evidence_urls,
                  i.tags,
                  i.perspectives,
                  i.perspective_digest
                FROM topics t
                LEFT JOIN topic_insights i ON i.topic_id = t.id
                WHERE (t.category IS NULL OR t.category = '')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM topic_articles ta4
                    JOIN articles a4 ON a4.id = ta4.article_id
                    WHERE ta4.topic_id = t.id
                      AND COALESCE(a4.kind,'') = 'news'
                  )
                ORDER BY
                  COALESCE(i.importance, 0) DESC,
                  COALESCE(recent, 0) DESC,
                  t.id DESC
                LIMIT ?
                """,
                (cutoff_48h, LIMIT_PER_CAT),
            )
        else:
            cur.execute(
                """
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS title,
                  (
                      SELECT a2.url
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE
                            WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                            ELSE 1
                          END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                        LIMIT 1
                    ) AS url,
                    (
                      SELECT COALESCE(
                        NULLIF(a2.published_at,''),
                        a2.fetched_at
                      )
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                        CASE
                          WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                          ELSE 1
                        END,
                        datetime(a2.fetched_at) DESC,
                        datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                        a2.url ASC
                      LIMIT 1
                    ) AS article_date,
                  (
                      SELECT COALESCE(SUM(
                        CASE
                          WHEN datetime(
                            substr(
                              replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                              1, 19
                            )
                          ) >= datetime(?) THEN 1
                          ELSE 0
                        END
                      ), 0)
                      FROM topic_articles ta3
                      JOIN articles a3 ON a3.id = ta3.article_id
                      WHERE ta3.topic_id = t.id
                    ) AS recent,
                  (
                      SELECT a2.source
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0 ELSE 1 END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                      LIMIT 1
                    ) AS source,

                  i.importance,
                  i.summary,
                  i.key_points,
                  i.evidence_urls,
                  i.tags,
                  i.perspectives,
                  i.perspective_digest
                FROM topics t
                LEFT JOIN topic_insights i ON i.topic_id = t.id
                WHERE t.category = ?
                  AND COALESCE(t.category,'') <> 'news'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM topic_articles ta4
                    JOIN articles a4 ON a4.id = ta4.article_id
                    WHERE ta4.topic_id = t.id
                      AND COALESCE(a4.kind,'') = 'news'
                  )
                ORDER BY
                  COALESCE(i.importance, 0) DESC,
                  COALESCE(recent, 0) DESC,
                  t.id DESC
                LIMIT ?
                """,
                (cutoff_48h, cat_id, LIMIT_PER_CAT),
            )


        rows = cur.fetchall()
        items: List[Dict[str, Any]] = []
        for r in rows:
            tid, title, url, article_date, recent, source, importance, summary, key_points, evidence_urls, tags, perspectives, perspective_digest = r
            items.append(
                {
                    "id": tid,
                    "title": clean_for_html(title),  # ← ここはSQLで title_ja 優先済み
                    "url": url or "#",
                    "date": article_date or "",
                    "recent": int(recent or 0),
                    "source": source or "",
                    "importance": int(importance) if importance is not None else None,
                    "summary": summary or "",
                    "key_points": _safe_json_list(key_points),
                    "evidence_urls": _safe_json_list(evidence_urls),
                    "tags": _safe_json_list(tags),
                    "perspectives": _safe_json_obj(perspectives),
                    "perspective_digest": _safe_json_obj(perspective_digest),
                }
            )

        # トピック順を完全決定（最後の揺れ防止）
        items = sorted(
            items,
            key=lambda x: (
                -(x["importance"] or 0),
                -(x["recent"] or 0),
                x["id"]
            )
        )

        # ===== A: 確実対応：注目TOP5を詳細リストにも必ず混ぜる =====
        hot_ids = [x["id"] for x in hot_by_cat.get(cat_id, [])]
        item_ids = {x["id"] for x in items}
        missing_ids = [tid for tid in hot_ids if tid not in item_ids]

        if missing_ids:
            # IN句プレースホルダを生成
            placeholders = ",".join(["?"] * len(missing_ids))

            if cat_id == "other":
                sql_missing = f"""
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS title,
                  (
                      SELECT a2.url
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE
                            WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                            ELSE 1
                          END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                        LIMIT 1
                    ) AS url,
                    (
                      SELECT COALESCE(
                        NULLIF(a2.published_at,''),
                        a2.fetched_at
                      )
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                        CASE
                          WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                          ELSE 1
                        END,
                        datetime(a2.fetched_at) DESC,
                        datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                        a2.url ASC
                      LIMIT 1
                    ) AS article_date,
                  (
                      SELECT COALESCE(SUM(
                        CASE
                          WHEN datetime(
                            substr(
                              replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                              1, 19
                            )
                          ) >= datetime(?) THEN 1
                          ELSE 0
                        END
                      ), 0)
                      FROM topic_articles ta3
                      JOIN articles a3 ON a3.id = ta3.article_id
                      WHERE ta3.topic_id = t.id
                    ) AS recent,
                  (
                      SELECT a2.source
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0 ELSE 1 END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                      LIMIT 1
                    ) AS source,
                  i.importance,
                  i.summary,
                  i.key_points,
                  i.evidence_urls,
                  i.tags,
                  i.perspectives,
                  i.perspective_digest
                FROM topics t
                LEFT JOIN topic_insights i ON i.topic_id = t.id
                WHERE (t.category IS NULL OR t.category = '')
                  AND COALESCE(NULLIF(t.category,''), 'other') NOT IN ('news', 'market')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM topic_articles ta4
                    JOIN articles a4 ON a4.id = ta4.article_id
                    WHERE ta4.topic_id = t.id
                      AND COALESCE(a4.kind,'') = 'news'
                  )
                  AND t.id IN ({placeholders})
                """
                params = [cutoff_48h, *missing_ids]
            else:
                sql_missing = f"""
                SELECT
                  t.id,
                  COALESCE(t.title_ja, t.title) AS title,
                  (
                      SELECT a2.url
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE
                            WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                            ELSE 1
                          END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                        LIMIT 1
                    ) AS url,
                    (
                      SELECT COALESCE(
                        NULLIF(a2.published_at,''),
                        a2.fetched_at
                      )
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                        CASE
                          WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                          ELSE 1
                        END,
                        datetime(a2.fetched_at) DESC,
                        datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                        a2.url ASC
                      LIMIT 1
                    ) AS article_date,
                  (
                      SELECT COALESCE(SUM(
                        CASE
                          WHEN datetime(
                            substr(
                              replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                              1, 19
                            )
                          ) >= datetime(?) THEN 1
                          ELSE 0
                        END
                      ), 0)
                      FROM topic_articles ta3
                      JOIN articles a3 ON a3.id = ta3.article_id
                      WHERE ta3.topic_id = t.id
                    ) AS recent,
                  (
                      SELECT a2.source
                      FROM topic_articles ta2
                      JOIN articles a2 ON a2.id = ta2.article_id
                      WHERE ta2.topic_id = t.id
                      ORDER BY
                          CASE WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0 ELSE 1 END,
                          datetime(a2.fetched_at) DESC,
                          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
                          a2.url ASC
                      LIMIT 1
                    ) AS source,
                  i.importance,
                  i.summary,
                  i.key_points,
                  i.evidence_urls,
                  i.tags,
                  i.perspectives,
                  i.perspective_digest
                FROM topics t
                LEFT JOIN topic_insights i ON i.topic_id = t.id
                WHERE t.category = ?
                  AND COALESCE(NULLIF(t.category,''), 'other') <> 'news'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM topic_articles ta4
                    JOIN articles a4 ON a4.id = ta4.article_id
                    WHERE ta4.topic_id = t.id
                      AND COALESCE(a4.kind,'') = 'news'
                  )
                  AND t.id IN ({placeholders})
                """
                params = [cutoff_48h, cat_id, *missing_ids]

            cur.execute(sql_missing, params)
            for r in cur.fetchall():
                tid, title, url, article_date, recent, source, importance, summary, key_points, evidence_urls, tags, perspectives, perspective_digest = r
                items.append(
                    {
                        "id": tid,
                        "title": clean_for_html(title),
                        "url": url or "#",
                        "date": article_date or "",
                        "recent": int(recent or 0),
                        "source": source or "",
                        "importance": int(importance) if importance is not None else None,
                        "summary": summary or "",
                        "key_points": _safe_json_list(key_points),
                        "evidence_urls": _safe_json_list(evidence_urls),
                        "tags": _safe_json_list(tags),
                        "perspectives": _safe_json_obj(perspectives),
                        "perspective_digest": _safe_json_obj(perspective_digest),
                    }
                )

            # 再ソート（表示順の規則を維持）
            items = sorted(
                items,
                key=lambda x: (
                    -(x["importance"] or 0),
                    -(x["recent"] or 0),
                    x["id"]
                )
            )

            # 表示件数を LIMIT_PER_CAT に戻す（ただし注目TOP5は落とさない）
            hot_set = set(hot_ids)
            kept = []
            for it in items:
                if len(kept) >= LIMIT_PER_CAT and it["id"] not in hot_set:
                    continue
                kept.append(it)
            items = kept
        # ===== A: 確実対応ここまで =====


        # 改善3: importance が None かつ recent=0 の記事を除外（ファイルサイズ最適化）
        hot_set_for_filter = {x["id"] for x in hot_by_cat.get(cat_id, [])}
        items = [
            it for it in items
            if it["importance"] is not None or it["recent"] > 0 or it["id"] in hot_set_for_filter
        ]

        topics_by_cat[cat_id] = items

    all_tags = {}
    for cat_id, items in topics_by_cat.items():
        for t in items:
            for tg in (t.get("tags") or []):
                all_tags[tg] = all_tags.get(tg, 0) + 1
    tag_list = sorted(all_tags.items(), key=lambda x: (-x[1], x[0]))[:50]  # 上位50など

    # 改善4: タグをグループに分類
    TAG_GROUPS = {
        "技術": {"ai", "ml", "llm", "cloud", "api", "docker", "kubernetes", "devops", "cicd",
                 "database", "network", "linux", "python", "rust", "go", "java", "typescript",
                 "frontend", "backend", "performance", "compute", "gpu", "semiconductor", "hardware"},
        "セキュリティ": {"security", "vulnerability", "patch", "patch_window", "ransomware",
                         "authentication", "encryption", "privacy", "zero-day", "malware", "firewall"},
        "ビジネス": {"market", "investment", "regulation", "supply_chain", "price", "earnings",
                     "partnership", "strategy", "governance", "compliance"},
    }
    tag_dict = dict(tag_list)
    grouped: dict = {g: [] for g in TAG_GROUPS}
    grouped["その他"] = []
    for tg, cnt in tag_list:
        placed = False
        for g, members in TAG_GROUPS.items():
            if tg in members:
                grouped[g].append((tg, cnt))
                placed = True
                break
        if not placed:
            grouped["その他"].append((tg, cnt))
    tag_groups = [(g, tags) for g, tags in grouped.items() if tags]
    # --- UX改善①: 上部サマリー用meta ---
    runtime_sec = int(os.environ.get("RUNTIME_SEC", "0") or "0")

    # 記事総数（最終採用＝articlesテーブル件数）
    cur.execute("SELECT COUNT(*) FROM articles")
    total_articles = int(cur.fetchone()[0] or 0)

    # 新規記事数（48h）
    cur.execute(
        """
        SELECT COUNT(*)
        FROM articles
        WHERE datetime(COALESCE(NULLIF(published_at,''), fetched_at)) >= datetime(?)
        """,
        (cutoff_48h,),
    )
    new_articles_48h = int(cur.fetchone()[0] or 0)

    # --- ops用データ取得 ---
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # 記事統計
    cur.execute("""
        SELECT COUNT(*) as total,
          SUM(CASE WHEN datetime(fetched_at) >= datetime(?) THEN 1 ELSE 0 END) as week,
          SUM(CASE WHEN datetime(fetched_at) >= datetime(?) THEN 1 ELSE 0 END) as h48
        FROM articles
    """, (cutoff_7d, cutoff_48h))
    row = cur.fetchone()
    ops_stats = {
        "article_total": int(row[0] or 0),
        "article_week": int(row[1] or 0),
        "article_48h": int(row[2] or 0),
    }

    # トピック・インサイト統計
    cur.execute("SELECT COUNT(*) FROM topics")
    ops_stats["topic_total"] = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM topic_insights")
    ops_stats["insight_count"] = int(cur.fetchone()[0] or 0)
    ops_stats["insight_pending"] = max(0, ops_stats["topic_total"] - ops_stats["insight_count"])

    # 日別収集トレンド（14日）
    cur.execute("""
        SELECT DATE(fetched_at) as d, COUNT(*) as cnt
        FROM articles
        WHERE datetime(fetched_at) >= datetime('now','-14 days')
        GROUP BY DATE(fetched_at)
        ORDER BY d
    """)
    daily_raw = cur.fetchall()
    daily_max = max((r[1] for r in daily_raw), default=1)
    daily_trend = []
    bar_max_px = 100  # バーの最大高さ(px)
    for d, cnt in daily_raw:
        px = max(2, round(cnt / daily_max * bar_max_px)) if daily_max else 2
        label = d[5:] if d else ""  # MM-DD
        daily_trend.append({"d": d, "cnt": cnt, "px": px, "label": label})

    # カテゴリ別（全期間+7日）
    cur.execute("""
        SELECT COALESCE(NULLIF(category,''), 'other') as cat, COUNT(*) as total,
          SUM(CASE WHEN datetime(fetched_at) >= datetime(?) THEN 1 ELSE 0 END) as week
        FROM articles
        GROUP BY cat
        ORDER BY total DESC
    """, (cutoff_7d,))
    cat_raw = cur.fetchall()
    cat_max = max((r[1] for r in cat_raw), default=1)
    category_dist = []
    for cat, total, week in cat_raw:
        pct = round(total / cat_max * 100) if cat_max else 0
        category_dist.append({
            "name": cat_name.get(cat, cat),
            "total": int(total or 0),
            "week": int(week or 0),
            "pct": pct,
        })

    # ソース別記事数TOP15（7日列追加）
    cur.execute("""
        SELECT
          COALESCE(NULLIF(source,''), '') AS source,
          COUNT(*) AS total,
          SUM(CASE WHEN datetime(COALESCE(NULLIF(published_at,''), fetched_at)) >= datetime(?) THEN 1 ELSE 0 END) AS recent7d,
          SUM(CASE WHEN datetime(COALESCE(NULLIF(published_at,''), fetched_at)) >= datetime(?) THEN 1 ELSE 0 END) AS recent48,
          GROUP_CONCAT(DISTINCT COALESCE(NULLIF(category,''), 'other')) AS categories
        FROM articles
        WHERE COALESCE(NULLIF(source,''), '') != ''
        GROUP BY source
        ORDER BY total DESC, recent48 DESC, source ASC
        LIMIT 15
    """, (cutoff_7d, cutoff_48h))
    source_exposure = []
    for source, total, recent7d, recent48, categories_str in cur.fetchall():
        cat_ids = [c for c in (categories_str or "").split(",") if c]
        category_labels = [cat_name.get(c, c) for c in cat_ids[:3]]
        source_exposure.append({
            "source": clean_for_html(source),
            "total": int(total or 0),
            "recent7d": int(recent7d or 0),
            "recent48": int(recent48 or 0),
            "categories": " / ".join(category_labels) if category_labels else "-",
        })

    # フィード健全性
    feed_issues = []
    try:
        cur.execute("""
            SELECT feed_url, failure_count, last_success_at, last_failure_reason
            FROM feed_health
            WHERE failure_count > 0
            ORDER BY failure_count DESC
        """)
        for url, fc, last_ok, reason in cur.fetchall():
            url_short = url if len(url) <= 50 else url[:47] + "..."
            feed_issues.append({
                "url": url,
                "url_short": url_short,
                "failure_count": int(fc or 0),
                "last_success": (last_ok or "")[:16],
                "reason": clean_for_html(reason or ""),
            })
    except Exception as e:
        # feed_healthテーブルが未作成のDBも許容するため debug レベル
        _log_render_error("ops.feed_health_query", e, level="debug")

    # 一次情報比率（kind制限なし）
    primary_ratio_threshold = float(os.environ.get("PRIMARY_RATIO_THRESHOLD", "0.5") or "0.5")
    cur.execute("""
        SELECT
          COALESCE(NULLIF(category,''), 'other') AS category,
          COUNT(*) AS total_count,
          SUM(CASE WHEN source_tier = 'primary' THEN 1 ELSE 0 END) AS primary_count,
          SUM(CASE WHEN source_tier IS NOT NULL AND source_tier != '' THEN 1 ELSE 0 END) AS tier_set_count
        FROM articles
        GROUP BY COALESCE(NULLIF(category,''), 'other')
        ORDER BY total_count DESC, category ASC
    """)
    primary_ratio_by_category = []
    for category, total_count, primary_count, tier_set_count in cur.fetchall():
        total_count = int(total_count or 0)
        primary_count = int(primary_count or 0)
        tier_set_count = int(tier_set_count or 0)
        if tier_set_count == 0:
            primary_ratio_by_category.append({
                "category": category, "total_count": total_count,
                "primary_count": 0, "ratio_pct": "-",
                "status": "na", "warn_reason": "",
            })
        else:
            ratio = (primary_count / total_count) if total_count else 0.0
            status = "ok" if ratio >= primary_ratio_threshold else "warn"
            primary_ratio_by_category.append({
                "category": category, "total_count": total_count,
                "primary_count": primary_count,
                "ratio_pct": round(ratio * 100, 1),
                "status": status,
                "warn_reason": "閾値未達" if status == "warn" else "",
            })

    # RSS数（sources.yamlから拾える範囲でカウント。取れなければ0）
    rss_sources = 0
    try:
        with open("src/sources.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cats = cfg.get("categories") or []
        if isinstance(cats, list):
            for c in cats:
                if isinstance(c, dict):
                    srcs = c.get("sources") or c.get("feeds") or []
                    if isinstance(srcs, list):
                        for s in srcs:
                            if isinstance(s, str) and s.startswith("http"):
                                rss_sources += 1
                            elif isinstance(s, dict) and isinstance(s.get("url"), str):
                                rss_sources += 1
        # fallback: top-level sources
        if rss_sources == 0:
            srcs = cfg.get("sources") or cfg.get("feeds") or []
            if isinstance(srcs, list):
                for s in srcs:
                    if isinstance(s, str) and s.startswith("http"):
                        rss_sources += 1
                    elif isinstance(s, dict) and isinstance(s.get("url"), str):
                        rss_sources += 1
    except Exception as e:
        _log_render_error("ops.rss_sources_count", e, level="warning")
        rss_sources = 0

    meta = {
        "generated_at_jst": None,  # 後で入れる
        "runtime_sec": runtime_sec,
        "total_articles": total_articles,
        "new_articles_48h": new_articles_48h,
        "rss_sources": rss_sources,
    }

    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(NULLIF(t.category,''), 'other') AS category,
          (
            SELECT a2.url
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY a2.id DESC
            LIMIT 1
          ) AS url,
          (
            SELECT COALESCE(
              NULLIF(a2.published_at,''),
              a2.fetched_at
            )
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY
              CASE
                WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                ELSE 1
              END,
              datetime(a2.fetched_at) DESC,
              datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
              a2.url ASC
            LIMIT 1
          ) AS article_date,
          (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
              AND COALESCE(NULLIF(a3.region, ''), 'global') = 'jp'
          ) AS recent,
          i.importance,
          i.summary,
          i.tags,
          i.perspectives,
          i.perspective_digest
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE COALESCE(NULLIF(t.category,''), 'other') NOT IN ('news', 'market')
          AND NOT EXISTS (
            SELECT 1
            FROM topic_articles ta4
            JOIN articles a4 ON a4.id = ta4.article_id
            WHERE ta4.topic_id = t.id
              AND COALESCE(a4.kind,'') = 'news'
          )
          AND EXISTS (
            SELECT 1
            FROM topic_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.topic_id = t.id
              AND COALESCE(NULLIF(a.region, ''), 'global') = 'jp'
          )
        ORDER BY COALESCE(i.importance,0) DESC, COALESCE(recent,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h,),
    )
    jp_priority_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        jp_priority_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",
            "date": article_date or "",
        })

    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(NULLIF(t.category,''), 'other') AS category,
          (
            SELECT a2.url
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY a2.id DESC
            LIMIT 1
          ) AS url,
          (
            SELECT COALESCE(
              NULLIF(a2.published_at,''),
              a2.fetched_at
            )
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY
              CASE
                WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                ELSE 1
              END,
              datetime(a2.fetched_at) DESC,
              datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
              a2.url ASC
            LIMIT 1
          ) AS article_date,
          (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
              AND COALESCE(NULLIF(a3.region, ''), 'global') = 'jp'
          ) AS recent,
          i.importance,
          i.summary,
          i.tags,
          i.perspectives,
          i.perspective_digest
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE COALESCE(NULLIF(t.category,''), 'other') NOT IN ('news', 'market')
          AND NOT EXISTS (
            SELECT 1
            FROM topic_articles ta4
            JOIN articles a4 ON a4.id = ta4.article_id
            WHERE ta4.topic_id = t.id
              AND COALESCE(a4.kind,'') = 'news'
          )
          AND (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
              AND COALESCE(NULLIF(a3.region, ''), 'global') = 'jp'
          ) > 0
        ORDER BY COALESCE(recent,0) DESC, COALESCE(i.importance,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h, cutoff_48h),
    )
    jp_priority_trending_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        jp_priority_trending_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",
            "date": article_date or "",
        })

    # --- UX改善①: カテゴリ横断TOP ---
    # Global Top 10: importance desc, recent desc, id asc（完全決定）
    TECH_CATS = {"ai", "dev", "security", "system", "manufacturing", "cloud", "data"}  # 必要に応じて調整
    tech_cat_ids = [c["id"] for c in tech_categories if c.get("id") in TECH_CATS]
    if not tech_cat_ids:
        tech_cat_ids = [c["id"] for c in tech_categories if c.get("id") and c.get("id") != "other"]

    ph = ",".join(["?"] * len(tech_cat_ids))
    cur.execute(
    f"""
    SELECT
      t.id,
      COALESCE(t.title_ja, t.title) AS title,
      COALESCE(NULLIF(t.category,''), 'other') AS category,
      (
        SELECT a2.url
        FROM topic_articles ta2
        JOIN articles a2 ON a2.id = ta2.article_id
        WHERE ta2.topic_id = t.id
        ORDER BY a2.id DESC
        LIMIT 1
      ) AS url,
      (
        SELECT COALESCE(
          NULLIF(a2.published_at,''),
          a2.fetched_at
        )
        FROM topic_articles ta2
        JOIN articles a2 ON a2.id = ta2.article_id
        WHERE ta2.topic_id = t.id
        ORDER BY
          CASE
            WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
            ELSE 1
          END,
          datetime(a2.fetched_at) DESC,
          datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
          a2.url ASC
        LIMIT 1
      ) AS article_date,
      (
        SELECT COALESCE(SUM(
          CASE
            WHEN datetime(
              substr(
                replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                1, 19
              )
            ) >= datetime(?) THEN 1
            ELSE 0
          END
        ), 0)
        FROM topic_articles ta3
        JOIN articles a3 ON a3.id = ta3.article_id
        WHERE ta3.topic_id = t.id
      ) AS recent,
      i.importance,
      i.summary,
      i.tags,
      i.perspectives,
      i.perspective_digest
    FROM topics t
    LEFT JOIN topic_insights i ON i.topic_id = t.id
    WHERE COALESCE(NULLIF(t.category,''), 'other') NOT IN ('news', 'market')
      AND NOT EXISTS (
        SELECT 1
        FROM topic_articles ta4
        JOIN articles a4 ON a4.id = ta4.article_id
        WHERE ta4.topic_id = t.id
          AND COALESCE(a4.kind,'') = 'news'
      )
    ORDER BY
      CASE
        WHEN COALESCE(NULLIF(t.category,''), 'other') IN ({ph}) THEN 1
        ELSE 0
      END DESC,
      COALESCE(i.importance,0) DESC,
      COALESCE(recent,0) DESC,
      t.id ASC
    LIMIT 10
    """,
    (cutoff_48h, *tech_cat_ids),
)

    global_top = []
    for tid, title, category, url, article_date,recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        global_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,   # ★追加
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",  # 今は空でOK（後で短文化したければ追加）
            "date": article_date or "",
        })

    # Trending Top 10: recent desc, importance desc, id asc（完全決定）
    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(NULLIF(t.category,''), 'other') AS category,
          (
            SELECT a2.url
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY a2.id DESC
            LIMIT 1
          ) AS url,
          (
            SELECT COALESCE(
              NULLIF(a2.published_at,''),
              a2.fetched_at
            )
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY
              CASE
                WHEN COALESCE(NULLIF(a2.content,''), '') != '' THEN 0
                ELSE 1
              END,
              datetime(a2.fetched_at) DESC,
              datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC,
              a2.url ASC
            LIMIT 1
          ) AS article_date,
          (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
          ) AS recent,
          i.importance,
          i.summary,
          i.tags,
          i.perspectives,
          i.perspective_digest
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE (
          SELECT COALESCE(SUM(
            CASE
              WHEN datetime(
                substr(
                  replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                  1, 19
                )
              ) >= datetime(?) THEN 1
              ELSE 0
            END
          ), 0)
          FROM topic_articles ta3
          JOIN articles a3 ON a3.id = ta3.article_id
          WHERE ta3.topic_id = t.id
        ) > 0
          AND COALESCE(NULLIF(t.category,''), 'other') NOT IN ('news', 'market')
          AND NOT EXISTS (
            SELECT 1
            FROM topic_articles ta4
            JOIN articles a4 ON a4.id = ta4.article_id
            WHERE ta4.topic_id = t.id
              AND COALESCE(a4.kind,'') = 'news'
          )
        ORDER BY COALESCE(recent,0) DESC, COALESCE(i.importance,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h, cutoff_48h),
    )
    trending_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        trending_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,   # ★追加
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",
            "date": article_date or "",
        })

    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(NULLIF(t.category,''), 'other') AS category,
          (
            SELECT a2.url
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY a2.id DESC
            LIMIT 1
          ) AS url,
          (
            SELECT COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC
            LIMIT 1
          ) AS article_date,
          (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
          ) AS recent,
          i.importance,
          i.summary,
          i.tags,
          i.perspectives,
          i.perspective_digest
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE COALESCE(NULLIF(t.category,''), 'other') = 'market'
        ORDER BY COALESCE(i.importance,0) DESC, COALESCE(recent,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h,),
    )
    market_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        market_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",
            "date": article_date or "",
        })

    cur.execute(
        """
        SELECT
          t.id,
          COALESCE(t.title_ja, t.title) AS title,
          COALESCE(NULLIF(t.category,''), 'other') AS category,
          (
            SELECT a2.url
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY a2.id DESC
            LIMIT 1
          ) AS url,
          (
            SELECT COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)
            FROM topic_articles ta2
            JOIN articles a2 ON a2.id = ta2.article_id
            WHERE ta2.topic_id = t.id
            ORDER BY datetime(COALESCE(NULLIF(a2.published_at,''), a2.fetched_at)) DESC
            LIMIT 1
          ) AS article_date,
          (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
          ) AS recent,
          i.importance,
          i.summary,
          i.tags,
          i.perspectives,
          i.perspective_digest
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE COALESCE(NULLIF(t.category,''), 'other') = 'market'
          AND (
            SELECT COALESCE(SUM(
              CASE
                WHEN datetime(
                  substr(
                    replace(replace(COALESCE(NULLIF(a3.published_at,''), a3.fetched_at),'T',' '),'+00:00',''),
                    1, 19
                  )
                ) >= datetime(?) THEN 1
                ELSE 0
              END
            ), 0)
            FROM topic_articles ta3
            JOIN articles a3 ON a3.id = ta3.article_id
            WHERE ta3.topic_id = t.id
          ) > 0
        ORDER BY COALESCE(recent,0) DESC, COALESCE(i.importance,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h, cutoff_48h),
    )
    market_trending_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives, perspective_digest in cur.fetchall():
        market_trending_top.append({
            "id": tid,
            "title": clean_for_html(title),
            "category": category,
            "url": url or "#",
            "recent": int(recent or 0),
            "importance": int(importance) if importance is not None else 0,
            "summary": summary or "",
            "tags": _safe_json_list(tags),
            "perspectives": _safe_json_obj(perspectives),
            "perspective_digest": _safe_json_obj(perspective_digest),
            "one_liner": "",
            "date": article_date or "",
        })

    # 改善5: テック→ニュース相互リンク用マップ
    NEWS_LINK_MAP = {
        "manufacturing": ("manufacturing", "製造業ニュース"),
        "security": ("security", "セキュリティニュース"),
        "system": ("policy", "政策・規制ニュース"),
        "dev": ("company", "企業動向ニュース"),
    }

    # 生成日時（JST）
    generated_at = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S JST")
    meta["generated_at_jst"] = generated_at

    tech_dir = out_dir / "tech"
    tech_dir.mkdir(exist_ok=True)

    tech_sub_assets = build_asset_paths()
    tech_root_assets = build_asset_paths()

    tech_html_sub = Template(HTML).render(
        common_css_href=tech_sub_assets["common_css_href"],
        common_js_src=tech_sub_assets["common_js_src"],
        page="tech",
        nav_prefix=tech_sub_assets["nav_prefix"],
        categories=tech_categories,
        cat_name=cat_name,
        topics_by_cat=topics_by_cat,
        hot_by_cat=hot_by_cat,
        generated_at=generated_at,
        meta=meta,
        jp_priority_top=jp_priority_top,
        jp_priority_trending_top=jp_priority_trending_top,
        global_top=global_top,
        trending_top=trending_top,
        market_top=market_top,
        market_trending_top=market_trending_top,
        tag_list=tag_list,
        tag_groups=tag_groups,
        news_link_map=NEWS_LINK_MAP,
        source_exposure=source_exposure,
        primary_ratio_by_category=primary_ratio_by_category,
        primary_ratio_threshold=primary_ratio_threshold,
        fmt_date=fmt_date,
    )

    tech_html_root = Template(HTML).render(
        common_css_href=tech_root_assets["common_css_href"],
        common_js_src=tech_root_assets["common_js_src"],
        page="tech",
        nav_prefix=tech_root_assets["nav_prefix"],
        categories=tech_categories,
        cat_name=cat_name,
        topics_by_cat=topics_by_cat,
        hot_by_cat=hot_by_cat,
        generated_at=generated_at,
        meta=meta,
        jp_priority_top=jp_priority_top,
        jp_priority_trending_top=jp_priority_trending_top,
        global_top=global_top,
        trending_top=trending_top,
        market_top=market_top,
        market_trending_top=market_trending_top,
        tag_list=tag_list,
        tag_groups=tag_groups,
        news_link_map=NEWS_LINK_MAP,
        source_exposure=source_exposure,
        primary_ratio_by_category=primary_ratio_by_category,
        primary_ratio_threshold=primary_ratio_threshold,
        fmt_date=fmt_date,
    )

    # グローバル _render_errors を利用（モジュール先頭で定義）。
    # main() 呼び出しの冪等性のため、ここでクリアする。
    _render_errors.clear()

    try:
        (tech_dir / "index.html").write_text(tech_html_sub, encoding="utf-8")
        (out_dir / "index.html").write_text(tech_html_root, encoding="utf-8")
    except Exception as e:
        _log_render_error("tech.write_html", e, level="error")

    try:
        ops_dir = out_dir / "ops"
        ops_dir.mkdir(exist_ok=True)
        ops_assets = build_asset_paths()
        # フィード品質スコア（feed_quality モジュール）
        try:
            from feed_quality import compute_feed_quality
            feed_quality = compute_feed_quality(cur)
        except Exception as _fqe:
            _log_render_error("ops.feed_quality", _fqe, level="warning")
            feed_quality = []
        ops_html = Template(OPS_HTML).render(
            common_css_href=ops_assets["common_css_href"],
            common_js_src=ops_assets["common_js_src"],
            page="ops",
            nav_prefix=ops_assets["nav_prefix"],
            meta=meta,
            cat_name=cat_name,
            ops=ops_stats,
            daily_trend=daily_trend,
            category_dist=category_dist,
            source_exposure=source_exposure,
            feed_issues=feed_issues,
            feed_quality=feed_quality,
            primary_ratio_by_category=primary_ratio_by_category,
            primary_ratio_threshold=primary_ratio_threshold,
        )
        (ops_dir / "index.html").write_text(ops_html, encoding="utf-8")
    except Exception as e:
        _log_render_error("ops.render", e, level="error")

    try:
        render_news_pages(out_dir, generated_at, cur)
    except Exception as e:
        _log_render_error("news.render", e, level="error")

    try:
        render_forecast_page(out_dir, generated_at, cur)
    except Exception as e:
        _log_render_error("forecast.render", e, level="error")

    try:
        render_forecast_hits_page(out_dir, generated_at, cur)
    except Exception as e:
        _log_render_error("forecast_hits.render", e, level="error")

    try:
        render_rss_feed(out_dir, generated_at, cur)
    except Exception as e:
        _log_render_error("feed.render", e, level="error")

    try:
        render_search_page(out_dir, generated_at, cur)
    except Exception as e:
        _log_render_error("search.render", e, level="error")

    try:
        # Diff ビュー生成（スナップショット保存→差分描画）
        from diff_view import save_today_snapshot, render_diff_page
        save_today_snapshot(conn)
        render_diff_page(out_dir, conn)
    except Exception as e:
        _log_render_error("diff.render", e, level="error")

    try:
        # トピックタイムライン。生成済みメインページが 📈 経緯リンクで参照している
        # トピック ID をすべて含める（リンク切れ防止のため HTML から実リンクを回収）
        import re as _re
        from topic_timeline import render_topic_timelines
        linked_ids: set[int] = set()
        for _page in ("index.html", "tech/index.html", "news/index.html"):
            _p = out_dir / _page
            if _p.exists():
                linked_ids |= {
                    int(m) for m in _re.findall(
                        r'href="/daily-tech-trend/topic/(\d+)/"', _p.read_text(encoding="utf-8")
                    )
                }
        render_topic_timelines(out_dir, top_n=50, include_ids=linked_ids, conn=conn)
    except Exception as e:
        _log_render_error("topic_timeline.render", e, level="error")

    try:
        # エンティティ抽出＋企業別ページ（辞書マッチ）
        from entities import extract_entities_by_dict, render_entity_pages
        extract_entities_by_dict(conn)
        render_entity_pages(out_dir, conn=conn, top_n=30)
    except Exception as e:
        _log_render_error("entities.render", e, level="error")

    try:
        # sitemap は diff ページ生成後に作成（リンクを含めるため）
        render_sitemap(out_dir, cur)
    except Exception as e:
        _log_render_error("sitemap.render", e, level="error")

    try:
        render_json_api(out_dir, cur)
    except Exception as e:
        _log_render_error("api.render", e, level="error")

    conn.close()

    if _render_errors:
        _logger.warning(
            "render completed with %d error(s): %s",
            len(_render_errors),
            _render_errors,
        )
    print(f"[TIME] step=render end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
