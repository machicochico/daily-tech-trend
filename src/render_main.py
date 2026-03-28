# src/render.py
from __future__ import annotations
import os
import re

import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml
from jinja2 import Template
from datetime import datetime, timedelta, timezone

from db import connect
from text_clean import clean_for_html, clean_json_like

from typing import Any, List
import time

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

PORTAL_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Tech Trend</title>
  <link rel="stylesheet" href="{{ common_css_href }}">
</head>
<body>
  <h1>Daily Tech Trend</h1>
   <div class="small">Generated: {{ generated_at }}</div>

  <div class="card">
    <h2 style="margin:0 0 6px">技術動向ダイジェスト</h2>
    <div class="small">技術トピックの整理（カテゴリ別・注目・解説）</div>
    <a class="btn" href="./tech/index.html">技術動向を見る →</a>
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px">ニュースダイジェスト</h2>
    <div class="small">提案の背景となる国内/世界ニュース</div>
    <a class="btn" href="./news/index.html">ニュースを見る →</a>
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px">未来予測レポート</h2>
    <div class="small">多視点ニュース分析に基づく未来予測（1週間〜1年）</div>
    <a class="btn" href="./forecast/index.html">未来予測を見る →</a>
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px">運用メトリクス</h2>
    <div class="small">Source露出（競合比較）とカテゴリ別 一次情報比率を確認</div>
    <a class="btn" href="./ops/index.html">運用ページを見る →</a>
  </div>

  <script src="{{ common_js_src }}"></script>
  <script>
    if (location.hash && location.hash.startsWith("#topic-")) {
      location.replace("./tech/index.html" + location.hash);
    }
  </script>
</body>
</html>
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
</head>
<body data-filter-total="1">
  <h1>技術動向ダイジェスト</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
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
            </div>

            {% if t.summary %}
              <div class="summary-preview">{{ t.summary[:100] }}{% if t.summary|length > 100 %}…{% endif %}</div>
            {% endif %}
            {% if t.source %}<div class="mini">{{ t.source }}</div>{% endif %}

            {% if t.summary or (t.key_points and t.key_points|length>0) or (t.perspectives) or (t.evidence_urls and t.evidence_urls|length>0) %}
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
<script src="{{ common_js_src }}"></script>
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

window.DTTCommon.setupCommon('topic');
</script>

</body>
</html>
"""
NEWS_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <meta name="description" content="国内・世界ニュースを技術活用の背景として整理し、新着と重要トピックを素早く把握できるニュースダイジェスト。">
  <link rel="canonical" href="/daily-tech-trend/news/">

  <meta property="og:title" content="ニュースダイジェスト">
  <meta property="og:description" content="国内・世界ニュースを技術活用の背景として整理し、新着と重要トピックを素早く把握できるニュースダイジェスト。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="/daily-tech-trend/news/">
  <meta property="og:site_name" content="Daily Tech Trend">
  <meta property="og:locale" content="ja_JP">

  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="ニュースダイジェスト">
  <meta name="twitter:description" content="国内・世界ニュースを技術活用の背景として整理し、新着と重要トピックを素早く把握できるニュースダイジェスト。">
  <link rel="stylesheet" href="{{ common_css_href }}">
</head>
<body data-filter-total="0">
  <h1>{{ heading }}</h1>

  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
  </div>


  <!-- techと同じ：今日の要点 -->
  <div class="summary-card">
    <div class="summary-title">今日の要点（ニュース）</div>

    <div class="summary-grid">
      <div class="summary-item">
        <div class="k">Generated (JST)</div>
        <div class="v">{{ meta.generated_at_jst }}</div>
      </div>
      <div class="summary-item">
        <div class="k">News</div>
        <div class="v">{{ meta.total_articles }} <span class="small">(new48h {{ meta.new_articles_48h }})</span></div>
      </div>
      <div class="summary-item">
        <div class="k">Japan</div>
        <div class="v">{{ meta.jp_count }}</div>
      </div>
      <div class="summary-item">
        <div class="k">Global</div>
        <div class="v">{{ meta.global_count }}</div>
      </div>
    </div>

    <!-- techと同じ：タグバー -->
    <div class="small" style="margin-top:10px">
      <span class="badge">Tags</span>
      <div id="tagBar" class="tag-bar collapsed" role="toolbar" aria-label="タグフィルタ" style="margin-top:6px">
        <button class="btn btn-reset" type="button" onclick="clearTagFilter()">🔄 リセット</button>
        <label class="small tag-mode">
          <input type="checkbox" id="tagModeOr"> OR（どれか）
        </label>
        {% for tg, cnt in tag_list %}
          <button class="btn" type="button" data-tag-btn="{{ tg }}" onclick="toggleTag('{{ tg }}')">
            {{ tg }} ({{ cnt }})
          </button>
        {% endfor %}
      </div>
      <button id="tagMore" class="btn btn-more" type="button" style="margin-top:6px">＋ よく使うタグ以外も表示</button>
    </div>

    <div id="tag-active" class="small" style="margin-top:6px; display:none;"></div>

    <!-- techと同じ：検索（imp/recentはnewsでは使わないので固定） -->
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

  <!-- techと同じ：カテゴリ（折りたたみ） -->
 {% for sec in sections %}
  <section class="category-section" id="cat-{{ sec.anchor }}" role="region" aria-label="{{ sec.title }}">
    <div class="category-header">
      <h2>
        {{ sec.title }}
        <span class="badge">{{ sec.count }}</span>
        {% if sec.recent48 is defined %}
          <span class="badge">+{{ sec.recent48 }}/48h</span>
        {% endif %}
      </h2>
      <button class="btn" type="button" onclick="toggleCat('{{ sec.anchor }}')">表示切替</button>
    </div>

    <div class="category-body">
      <ul style="list-style:none;padding:0">
        {% for it in sec.rows %}
          <li id="news-{{ it.id }}" class="topic-row"
            data-title="{{ it.title|e }}"
            data-summary="{{ (it.summary or '')|e }}"
            data-imp="{{ it.importance or 0 }}"
            data-date="{{ it.dt }}"
            data-tags="{{ it.tags|default([])|join(',') }}">

           <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:6px">
            {% if it.is_representative %}<span class="badge">代表記事</span>{% endif %}
            <a class="topic-link" href="{{ it.url }}" target="_blank" rel="noopener" style="font-weight:500">{{ it.title }}</a>
            <span class="date">{{ it.dt_jst }}</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
            <span class="badge imp">重要度 {{ it.importance or 0 }}</span>
            {% if it.tags and it.tags|length>0 %}
              {% for tg in it.tags %}
                <span class="badge">{{ tg }}</span>
              {% endfor %}
            {% endif %}
          </div>

          {% if it.summary %}
            <div class="summary-preview">{{ it.summary[:100] }}{% if it.summary|length > 100 %}…{% endif %}</div>
          {% endif %}
          {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}

           {% if it.importance_basis or it.summary or (it.key_points and it.key_points|length>0) or (it.perspectives and (it.perspectives.engineer or it.perspectives.management or it.perspectives.consumer)) %}
              <details class="insight" role="group">
                <summary>要約・解説を表示</summary>
                <div class="small" style="margin-top:6px;"><strong>算出根拠（簡易）</strong>：{{ it.importance_basis }}</div>

                {% if it.summary %}<div><strong>要約</strong>：{{ it.summary }}</div>{% endif %}

                {% if it.key_points and it.key_points|length>0 %}
                  <ul class="kps">
                    {% set shown = namespace(has_real=0, has_guess=0) %}
                    {% for kp in it.key_points %}
                      {% if "推測" in kp or "本文確認" in kp %}
                        {% if shown.has_guess == 0 %}
                          <li>{{ kp }}</li>
                          {% set shown.has_guess = 1 %}
                        {% endif %}
                      {% else %}
                        <li>{{ kp }}</li>
                        {% set shown.has_real = 1 %}
                      {% endif %}
                    {% endfor %}

                    {% if shown.has_real == 0 and shown.has_guess == 0 %}
                      <li>推測：記事情報が限定的なため、リンク先の本文確認が必要</li>
                    {% endif %}
                  </ul>
                {% endif %}

                {% if it.perspectives %}
                  <div class="perspectives">
                    {% if it.perspectives.engineer %}<div><b>技術者目線</b>: {{ it.perspectives.engineer }}</div>{% endif %}
                    {% if it.perspectives.management %}<div><b>経営者目線</b>: {{ it.perspectives.management }}</div>{% endif %}
                    {% if it.perspectives.consumer %}<div><b>消費者目線</b>: {{ it.perspectives.consumer }}</div>{% endif %}
                  </div>
                {% endif %}
                {% if it.evidence_urls and it.evidence_urls|length>0 %}
                  <div class="evidence-urls">
                    <strong>根拠</strong>：
                    {% for u in it.evidence_urls %}
                      <a href="{{ u }}" target="_blank" rel="noopener">{{ u|truncate(60, True) }}</a>{% if not loop.last %} | {% endif %}
                    {% endfor %}
                  </div>
                {% endif %}

              </details>
          {% endif %}

          </li>

        {% endfor %}
        {% if sec.other_rows and sec.other_rows|length > 0 %}
          <li class="topic-row">
            <details class="insight">
              <summary class="small">その他 {{ sec.other_rows|length }} 件を表示</summary>
              <ul>
                {% for it in sec.other_rows %}
                  <li id="news-{{ it.id }}" class="topic-row"
                    data-title="{{ it.title|e }}"
                    data-summary="{{ (it.summary or '')|e }}"
                    data-imp="{{ it.importance or 0 }}"
                    data-date="{{ it.dt }}"
                    data-tags="{{ it.tags|default([])|join(',') }}">
                    <div>
                      <span class="badge imp">重要度 {{ it.importance or 0 }}</span>
                      <a class="topic-link" href="{{ it.url }}" target="_blank" rel="noopener">{{ it.title }}</a>
                      <span class="date">{{ it.dt_jst }}</span>
                      {% if it.summary %}
                        <div class="summary-preview">{{ it.summary[:80] }}{% if it.summary|length > 80 %}…{% endif %}</div>
                      {% endif %}
                      <details class="insight" role="group">
                        <summary class="small">要約・解説を表示</summary>
                        {% if it.summary %}<div><strong>要約</strong>：{{ it.summary }}</div>{% endif %}
                        <div class="small" style="margin-top:6px;"><strong>算出根拠（簡易）</strong>：{{ it.importance_basis }}</div>
                      </details>
                    </div>
                    {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}
                  </li>
                {% endfor %}
              </ul>
            </details>
          </li>
        {% endif %}
      </ul>
    </div>
  </section>
  {% endfor %}


<script src="{{ common_js_src }}"></script>
<script>
window.addEventListener('load', () => {
  setTimeout(() => {
    if (!location.hash) window.scrollTo(0, 0);
  }, 0);
});

window.DTTCommon.setupCommon('news');
</script>

</body>
</html>
"""

OPINION_HTML = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>立場別意見 | Daily Tech Trend</title>
  <meta name="description" content="技術者・経営者・消費者の3つの立場で、直近記事を分析し意見として整理したページ。">
  <link rel="canonical" href="/daily-tech-trend/opinion/">
  <meta property="og:title" content="立場別意見 | Daily Tech Trend">
  <meta property="og:description" content="技術者・経営者・消費者の3つの立場で、直近記事を分析し意見として整理したページ。">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://dachshund-github.github.io/daily-tech-trend/opinion/">
  <meta property="og:site_name" content="Daily Tech Trend">
  <meta property="og:locale" content="ja_JP">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="立場別意見 | Daily Tech Trend">
  <meta name="twitter:description" content="技術者・経営者・消費者の3つの立場で、直近記事を分析し意見として整理したページ。">
  <link rel="stylesheet" href="{{ common_css_href }}">
  <style>
    .view-mode-switch{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
    .mode-btn{padding:8px 12px;border:1px solid var(--border);border-radius:999px;background:var(--bg);cursor:pointer;font-size:13px}
    .mode-btn.active{border-color:var(--accent);color:var(--accent);font-weight:700;background:var(--accent-soft)}
    .comparison-only{display:none}
    .role-vertical{display:block}
    body[data-view-mode="comparison"] .comparison-only{display:block}
    body[data-view-mode="comparison"] .role-vertical{display:none}

    .comparison-layout{margin:8px 0 16px}
    .comparison-grid{display:none;gap:12px}
    .comparison-card{background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:12px}
    .comparison-card h3{margin:0 0 8px;font-size:16px}
    .comparison-item{margin:10px 0}
    .comparison-item h4{margin:0 0 4px;font-size:13px}

    .comparison-tabs{display:block}
    .tab-buttons{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
    .tab-btn{padding:7px 10px;border:1px solid var(--border);border-radius:999px;background:var(--bg);cursor:pointer;font-size:13px}
    .tab-btn.active{border-color:var(--accent);color:var(--accent);font-weight:700;background:var(--accent-soft)}
    .tab-panel{display:none}
    .tab-panel.active{display:block}

    @media (min-width: 821px){
      .comparison-grid{display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));}
      .comparison-tabs{display:none}
    }

    .opinion-toc{margin:8px 0 16px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--panel)}
    .opinion-toc strong{font-size:13px}
    .opinion-toc ul{margin:8px 0 0;padding-left:18px;display:flex;gap:10px;flex-wrap:wrap}
    .opinion-toc a{font-size:13px}
    .exec-brief{margin:8px 0 16px;padding:12px;border:1px solid var(--border);border-radius:10px;background:var(--panel)}
    .exec-brief h2{margin:0 0 10px;font-size:18px}
    .exec-brief .exec-grid{display:grid;gap:12px}
    .exec-brief .exec-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:10px}
    .exec-brief .exec-card h3{margin:0 0 8px;font-size:14px}
    .exec-brief ul{margin:0;padding-left:18px}
    .exec-brief li{margin:6px 0}
    .role-vertical h2{margin:0 0 14px}
    .role-vertical .section-heading{margin:22px 0 10px;font-size:18px;font-weight:800}
    .role-vertical .news-source-list{margin:0;padding-left:20px}
    .role-vertical .news-source-list li{margin:14px 0}
    .role-vertical .opinion-body{margin-top:10px;line-height:1.8;color:var(--text-main);font-size:15px}
    .role-vertical .opinion-paragraph{margin:12px 0;padding:10px 12px;border-left:3px solid var(--accent-soft);background:var(--panel);border-radius:8px}
    .role-vertical .opinion-label{display:inline-block;margin-bottom:4px;font-size:12px;font-weight:700;color:var(--accent)}
    .role-vertical .opinion-text{display:block;line-height:1.9;color:var(--text-main)}
    .role-discussion{margin:12px 0 8px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--panel)}
    .role-discussion ul{margin:8px 0 0;padding-left:18px}
    .role-discussion li{margin:8px 0}
    .role-vertical details.insight[open]{padding:10px 14px}
    .role-vertical details.insight[open] > *:not(summary){margin-top:10px}
    .role-vertical details.insight[open] .opinion-body + .section-heading{margin-top:18px}
    .imp-badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;line-height:1.4}
    .imp-high{background:#fee2e2;color:#dc2626;border:1px solid #fca5a5}
    .imp-mid{background:#fef3c7;color:#b45309;border:1px solid #fcd34d}
    .imp-low{background:#e0e7ff;color:#4338ca;border:1px solid #a5b4fc}
    .sticky-mini-nav{position:fixed;right:12px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:20}
    .sticky-mini-nav a,.sticky-mini-nav button{padding:8px 10px;border-radius:999px;border:1px solid var(--border);background:var(--bg);font-size:12px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.08)}
    .sticky-mini-nav .mini-toc{display:none}
    .role-nav-fixed{display:none}
    @media (max-width: 640px){
      .role-vertical{line-height:1.75}
      .role-vertical .small{line-height:1.8}
      .role-vertical p,.role-vertical li{margin-top:14px;margin-bottom:14px}
      .role-vertical details.insight[open]{padding:12px 16px}
      .role-vertical .opinion-body{padding:0 2px;line-height:1.9}
      .role-vertical .news-source-list li{margin:16px 0}
      .role-vertical .section-heading{margin:20px 0 10px}
      .role-nav-fixed{display:flex;position:fixed;bottom:0;left:0;right:0;z-index:30;background:var(--bg);border-top:1px solid var(--border);padding:8px;gap:6px;justify-content:center}
      .role-nav-fixed a{padding:8px 14px;border:1px solid var(--border);border-radius:999px;font-size:12px;text-decoration:none;color:var(--text-main)}
      .role-nav-fixed a.active{border-color:var(--accent);color:var(--accent);font-weight:700}
      .sticky-mini-nav{bottom:60px}
    }
    @media (min-width: 821px){
      .exec-brief .exec-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
      .sticky-mini-nav .mini-toc{display:inline-block}
    }
  </style>
</head>
<body id="top">
  <h1>立場別意見</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
  </div>

  <div class="summary-card">
    <div class="summary-title">今日の要点（立場別意見）</div>
    <div class="summary-grid">
      <div class="summary-item"><div class="k">Generated (JST)</div><div class="v">{{ generated_at }}</div></div>
      <div class="summary-item"><div class="k">対象記事数</div><div class="v">{{ source_item_count }}</div></div>
      <div class="summary-item"><div class="k">文字数目標</div><div class="v">各立場 260〜420文字</div></div>
      <div class="summary-item"><div class="k">立場</div><div class="v">技術者 / 経営者 / 消費者</div></div>
    </div>
  </div>

  <p class="small" style="margin:6px 0 10px;">各立場の詳細を縦スクロールで確認し、結論だけを比較したい場合は「比較表示」に切り替えてご覧ください。</p>

  {% if exec_brief and exec_brief.gaps %}
  <section class="exec-brief" aria-label="経営者向けクイック確認">
    <h2>経営者向け: 不足情報と是正ポイント</h2>
    <div class="small" style="margin-bottom:10px;">
      経営者視点の結論「{{ exec_brief.summary }}」を意思決定に必要な粒度へ補強するためのチェックです。
      {% if exec_brief.categories %}
      <br>本日の主要カテゴリ: {{ exec_brief.categories | join(', ') }}
      {% endif %}
    </div>
    <div class="exec-grid">
      <article class="exec-card">
        <h3>不足しがちな情報</h3>
        <ul class="small">
          {% for gap in exec_brief.gaps %}
          <li>{{ gap }}</li>
          {% endfor %}
        </ul>
      </article>
      <article class="exec-card">
        <h3>是正アクション</h3>
        <ul class="small">
          {% for action in exec_brief.actions %}
          <li>{{ action }}</li>
          {% endfor %}
          {% if exec_brief.recommendation %}
          <li>推奨:「{{ exec_brief.recommendation }}」に担当部門と期限を付与する。</li>
          {% endif %}
        </ul>
      </article>
    </div>
  </section>
  {% endif %}

  <nav class="opinion-toc" aria-label="立場別目次">
    <strong>目次</strong>
    <ul>
      {% for role in role_sections %}
      <li><a href="#{{ role.anchor_id }}">{{ role.label }}視点</a></li>
      {% endfor %}
    </ul>
  </nav>

  <div class="view-mode-switch" role="group" aria-label="表示モード切替">
    <button class="mode-btn active" type="button" data-view-mode="vertical">縦スクロール表示</button>
    <button class="mode-btn" type="button" data-view-mode="comparison">比較表示（タブ/3カラム）</button>
  </div>

  <section class="top-col" style="margin:8px 0 16px;">
    <h2>立場別の結論サマリ</h2>
    <ul>
      {% for role in role_sections %}
      <li>
        <strong>{{ role.label }}視点</strong>: {{ role.summary }}
        {% if role.top_evidence_tags %}
        <div class="small" style="margin-top:4px; display:flex; gap:6px; flex-wrap:wrap;">
          {% for tag in role.top_evidence_tags %}
          <span class="badge">根拠 {{ loop.index }}: {{ tag }}</span>
          {% endfor %}
        </div>
        {% endif %}
      </li>
      {% endfor %}
    </ul>
  </section>

  <section class="top-col comparison-only comparison-layout">
    <h2>立場別の結論サマリ（比較表示）</h2>
    <div class="comparison-grid">
      {% for role in role_sections %}
      <article class="comparison-card">
        <h3>{{ role.label }}視点</h3>
        <div class="comparison-item">
          <h4>結論</h4>
          <div class="small">{{ role.summary }}</div>
        </div>
        <div class="comparison-item">
          <h4>主要根拠</h4>
          <div class="small">{{ role.primary_evidence }}</div>
        </div>
        <div class="comparison-item">
          <h4>推奨アクション</h4>
          <div class="small">{{ role.recommendation }}</div>
        </div>
      </article>
      {% endfor %}
    </div>

    <div class="comparison-tabs">
      <div class="tab-buttons" role="tablist" aria-label="比較表示タブ">
        {% for role in role_sections %}
        <button type="button" class="tab-btn{% if loop.first %} active{% endif %}" data-tab="{{ role.role }}" role="tab" aria-selected="{{ 'true' if loop.first else 'false' }}">{{ role.label }}視点</button>
        {% endfor %}
      </div>
      {% for role in role_sections %}
      <article class="comparison-card tab-panel{% if loop.first %} active{% endif %}" data-panel="{{ role.role }}" role="tabpanel">
        <h3>{{ role.label }}視点</h3>
        <div class="comparison-item">
          <h4>結論</h4>
          <div class="small">{{ role.summary }}</div>
        </div>
        <div class="comparison-item">
          <h4>主要根拠</h4>
          <div class="small">{{ role.primary_evidence }}</div>
        </div>
        <div class="comparison-item">
          <h4>推奨アクション</h4>
          <div class="small">{{ role.recommendation }}</div>
        </div>
      </article>
      {% endfor %}
    </div>
  </section>

  {% for role in role_sections %}
  <section id="{{ role.anchor_id }}" class="top-col role-vertical" style="margin:8px 0 16px; scroll-margin-top: 20px;">
    <h2>{{ role.label }}視点</h2>
    <div class="small"><strong>結論</strong>: {{ role.summary }}</div>
    <div class="small" style="margin:6px 0"><strong>要約</strong></div>
    <ul class="small" style="margin:4px 0 8px;">
      {% for line in role.preview_lines %}
      <li>{{ line }}</li>
      {% endfor %}
    </ul>
    <div class="small"><strong>主要根拠</strong>: {{ role.primary_evidence }}</div>
    <div class="small"><strong>推奨アクション</strong>: {{ role.recommendation }}</div>
    {% if role.discussion_pairs %}
    <div class="role-discussion">
      <div class="small"><strong>他の立場からの問いかけ</strong></div>
      {% for pair in role.discussion_pairs %}
      {% if pair.type == 'question' %}
      <div class="small disc-q" style="margin:10px 0 2px;"><strong>{{ pair.from }}からの質問:</strong> {{ pair.text }}</div>
      {% else %}
      <div class="small disc-a" style="margin:2px 0 10px; padding-left:16px; border-left:2px solid var(--accent-soft);"><strong>{{ pair.from }}の回答:</strong> {{ pair.text }}</div>
      {% endif %}
      {% endfor %}
    </div>
    {% endif %}
    {% if role.selection_note %}
    <div class="small" style="color:#b45309; margin-top:6px;">{{ role.selection_note }}</div>
    {% endif %}
    <details class="insight" open>
      <summary class="small">意見本文とニュースソース（{{ role.label }}の意見約{{ role.full_text_len }}文字）</summary>
      <h3 class="section-heading">意見本文</h3>
      <div class="opinion-body">
        {% for block in role.full_text_sections %}
        <p class="opinion-paragraph"><span class="opinion-label">{{ block.label }}</span><span class="opinion-text">{{ block.text }}</span></p>
        {% endfor %}
      </div>
      <h3 class="section-heading">ニュースソース</h3>
      <ul class="news-source-list">
        {% for art in role.articles %}
        <li>
          <a href="{{ art.url }}" target="_blank" rel="noopener">{{ art.title }}</a>
          <div class="small" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0;">
            {{ art.source }}
            {% set imp = art.importance|default(0)|int %}
            {% if imp >= 60 %}
            <span class="imp-badge imp-high">重要度 {{ imp }}</span>
            {% elif imp >= 30 %}
            <span class="imp-badge imp-mid">重要度 {{ imp }}</span>
            {% else %}
            <span class="imp-badge imp-low">重要度 {{ imp }}</span>
            {% endif %}
          </div>
          <div class="small">{{ fmt_date(art.published_at or art.get('dt','')) or '日時不明' }}</div>
        </li>
        {% endfor %}
      </ul>
      {% if not role.articles %}
      <div class="small">本日は該当する記事が少ないため、無関係なニュースは採用していません。</div>
      {% endif %}
    </details>
    {% if not loop.last %}
    <div style="text-align:center;margin:12px 0;">
      <a href="#{{ role_sections[loop.index].anchor_id }}" class="small" style="color:var(--accent);">次の立場（{{ role_sections[loop.index].label }}視点）へ</a>
    </div>
    {% endif %}
  </section>
  {% endfor %}

  <nav class="role-nav-fixed" aria-label="立場ナビ">
    {% for role in role_sections %}
    <a href="#{{ role.anchor_id }}">{{ role.label }}</a>
    {% endfor %}
  </nav>

  <div class="sticky-mini-nav" aria-label="スクロール補助">
    <a class="mini-toc" href="#top">目次へ戻る</a>
    <button type="button" class="back-to-top">先頭へ戻る</button>
  </div>

  <script src="{{ common_js_src }}"></script>
  <script>
    window.DTTCommon.setupCommon('opinion');
    (function(){
      const modeButtons = [...document.querySelectorAll('.mode-btn')];
      const setMode = (mode) => {
        document.body.dataset.viewMode = mode;
        modeButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.viewMode === mode));
      };
      modeButtons.forEach(btn => btn.addEventListener('click', () => setMode(btn.dataset.viewMode)));

      const tabButtons = [...document.querySelectorAll('.tab-btn')];
      const tabPanels = [...document.querySelectorAll('.tab-panel')];
      const setTab = (role) => {
        tabButtons.forEach(btn => {
          const active = btn.dataset.tab === role;
          btn.classList.toggle('active', active);
          btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        tabPanels.forEach(panel => panel.classList.toggle('active', panel.dataset.panel === role));
      };
      tabButtons.forEach(btn => btn.addEventListener('click', () => setTab(btn.dataset.tab)));

      const backToTopButton = document.querySelector('.back-to-top');
      if (backToTopButton) {
        backToTopButton.addEventListener('click', () => {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
      }

      /* モバイル固定タブのアクティブ状態をスクロールで更新 */
      const fixedNav = document.querySelector('.role-nav-fixed');
      if (fixedNav) {
        const sections = [...document.querySelectorAll('.role-vertical[id]')];
        const navLinks = [...fixedNav.querySelectorAll('a')];
        let ticking = false;
        const updateActive = () => {
          let current = '';
          for (const sec of sections) {
            if (sec.getBoundingClientRect().top <= 100) current = sec.id;
          }
          navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + current));
          ticking = false;
        };
        window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(updateActive); } }, {passive:true});
      }
    })();
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
    except Exception:
        pass
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
    @media(max-width:640px){
      .ops-section{padding:10px 12px}
      .bar-chart{height:130px;gap:2px}
      .hbar-row{grid-template-columns:100px 1fr 80px}
      .hbar-row .hbar-label{font-size:11px}
      .hbar-row .hbar-nums{font-size:11px}
      .summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
    }
  </style>
</head>
<body>
  <h1>運用ダッシュボード</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
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
      <table class="source-table">
        <thead><tr><th>ソース</th><th class="num">全期間</th><th class="num">7日</th><th class="num">48h</th><th>主カテゴリ</th></tr></thead>
        <tbody>
        {% for s in source_exposure %}
          <tr><td>{{ s.source }}</td><td class="num">{{ s.total }}</td><td class="num">{{ s.recent7d }}</td><td class="num">{{ s.recent48 }}</td><td>{{ s.categories }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="meta">該当ソースなし</div>
    {% endif %}
  </div>

  <!-- セクション5: フィード健全性 -->
  <div class="ops-section">
    <h2>フィード健全性</h2>
    {% if feed_issues and feed_issues|length > 0 %}
      <div class="small" style="margin-bottom:8px">障害が発生しているフィード（failure_count > 0）</div>
      <table class="source-table">
        <thead><tr><th>フィードURL</th><th class="num">障害回数</th><th>最終成功</th><th>エラー内容</th></tr></thead>
        <tbody>
        {% for f in feed_issues %}
          <tr>
            <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ f.url }}">{{ f.url_short }}</td>
            <td class="num"><span class="feed-warn">{{ f.failure_count }}</span></td>
            <td class="small">{{ f.last_success or '-' }}</td>
            <td class="small">{{ f.reason or '-' }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="feed-ok" style="padding:12px 0">全フィード正常稼働中</div>
    {% endif %}
  </div>


  <script src="{{ common_js_src }}"></script>
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
    except Exception:
        return []
    return []

def _safe_json_obj(s: str | None) -> Dict[str, Any]:
    if not s:
        return {}
    try:
        v = clean_json_like(json.loads(s))
        return v if isinstance(v, dict) else {}
    except Exception:
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
    except Exception:
        pass

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


def _fit_text_length(text: str, target: int = 400, min_len: int = 360, max_len: int = 440) -> str:
    body = " ".join((text or "").split())

    def _trim_at_sentence_boundary(src: str, limit: int) -> str:
        clipped = src[:limit]
        boundary = max(clipped.rfind("。"), clipped.rfind("！"), clipped.rfind("？"))
        if boundary >= 0:
            return clipped[: boundary + 1].strip()
        boundary = max(clipped.rfind("、"), clipped.rfind(" "))
        if boundary >= 0:
            return clipped[:boundary].rstrip("、。 ") + "。"
        return clipped.rstrip("、。 ") + "。"

    if len(body) > max_len:
        return _trim_at_sentence_boundary(body, max_len)

    filler = " なお、情報が不足する場合は一次情報と公式発表を確認し、前提を共有して誤解を防ぐ。"
    while len(body) < min_len:
        body += filler

    if len(body) > target + 20:
        body = _trim_at_sentence_boundary(body, target + 20)

    if not body.endswith(("。", "！", "？")):
        body = body.rstrip("、。 ") + "。"
    return body


ROLE_PROFILES = {
    "engineer": {
        "keywords": ["ai", "security", "cloud", "半導体", "開発", "障害", "データ", "api", "モデル", "ソフト", "運用", "品質"],
        "categories": {"security": 12, "manufacturing": 8, "company": 3},
        "opinion_focus": "実装難易度・運用品質・セキュリティの両立",
    },
    "management": {
        "keywords": ["market", "policy", "industry", "企業", "投資", "業績", "提携", "戦略", "価格", "規制", "ガバナンス", "収益"],
        "categories": {"industry": 10, "policy": 10, "company": 9},
        "opinion_focus": "投資対効果・事業継続・意思決定速度",
    },
    "consumer": {
        "keywords": ["consumer", "サービス", "料金", "privacy", "アプリ", "ユーザー", "生活", "販売", "端末", "サポート", "安全", "利便"],
        "categories": {"news": 8, "policy": 6, "other": 5},
        "opinion_focus": "体験価値・負担増・情報の分かりやすさ",
    },
}

CATEGORY_CLAIM_TEMPLATES = {
    "engineer": {
        "security": "脆弱性の影響範囲特定と緩和策の即時適用を最優先すべきだ",
        "ai": "モデル精度の検証環境と本番切替のロールバック手順を先に整備すべきだ",
        "dev": "CI/CDパイプラインの安定性と依存ライブラリの互換性検証を先行すべきだ",
        "manufacturing": "制御系ソフトウェアの変更管理と設備連携テストの自動化を先に確立すべきだ",
        "system": "システム可用性のSLO定義と障害検知閾値の先行固定を優先すべきだ",
        "quality": "品質基準の定量化と自動回帰テストのカバレッジ拡大を先に進めるべきだ",
        "maintenance": "保守手順の標準化と予防保全データの収集基盤を先に構築すべきだ",
        "cloud": "マルチクラウド環境の権限境界と通信経路の可視化を先に設計すべきだ",
        "_default": "機能拡張よりも先に監視指標と切り戻し手順を前提にした仕様確定を優先すべきだ",
    },
    "management": {
        "security": "セキュリティ投資のROIと事業継続計画への影響を定量評価すべきだ",
        "ai": "POC段階でのKPI設定と撤退基準の事前合意を経営判断に組み込むべきだ",
        "industry": "市場構造の変化に対応した事業ポートフォリオの再評価を四半期内に実施すべきだ",
        "policy": "規制変更の事業インパクトを法務・経営で共同評価し対応優先度を決定すべきだ",
        "company": "競合動向と自社ポジションのギャップ分析を意思決定に反映すべきだ",
        "manufacturing": "生産ラインの投資回収期間と需給変動リスクを同時に評価すべきだ",
        "_default": "投資対効果と事業継続リスクを同じ判断基準で評価し、短期の話題性より実行可能性を優先すべきだ",
    },
    "consumer": {
        "security": "対象サービスのパスワード変更と二段階認証の設定状況を確認すべきだ",
        "ai": "AI生成コンテンツの信頼性を自分で検証する習慣を身につけるべきだ",
        "policy": "規制変更による料金・契約条件の変化を事前に把握し備えるべきだ",
        "news": "報道の一次情報源を確認し、自分の生活への影響範囲を具体的に見極めるべきだ",
        "company": "サービス提供元の方針変更が利用条件に与える影響を確認すべきだ",
        "_default": "価格・使い勝手・個人情報の条件を比較して、自分の利用環境を見直すべきだ",
    },
}

CATEGORY_EVIDENCE_AXES = {
    "security": ["脅威の影響範囲と攻撃経路", "パッチ適用と依存ライブラリの更新状況", "インシデント検知と復旧手順の整備"],
    "ai": ["モデル精度と推論コストのトレードオフ", "学習データの品質とバイアス管理", "本番環境での監視指標と異常検知"],
    "dev": ["ビルド・デプロイの安定性と速度", "コードレビューとテストカバレッジ", "依存関係の更新頻度と互換性"],
    "manufacturing": ["設備稼働率と予防保全の効果", "品質管理プロセスの自動化度", "サプライチェーンの可視性と応答速度"],
    "system": ["可用性SLOと障害検知の閾値設定", "外部連携の責務分離と認可境界", "運用手順の自動化と整合性検証"],
    "cloud": ["マルチクラウドの権限管理と通信経路", "コスト最適化とリソース自動スケーリング", "データ配置とレイテンシ要件"],
    "quality": ["品質基準の定量化と計測方法", "回帰テストの自動化と網羅性", "不具合の根本原因分析プロセス"],
    "maintenance": ["保守手順の標準化と属人性排除", "予防保全データの収集と活用", "緊急対応の手順と連絡体制"],
    "_default": ["可観測性とSLO設計の妥当性", "依存関係と権限境界の整理", "運用品質とデータ整合性の確保"],
}

CATEGORY_ACTION_TEMPLATES = {
    "engineer": {
        "security": "脆弱性の影響範囲を即日トリアージし、パッチ適用とWAFルール更新の実行計画を24時間以内に確定する。",
        "ai": "モデル切替のカナリアリリース手順とロールバック条件を今スプリントで実装計画に落とし込む。",
        "dev": "CI/CDパイプラインの失敗率を計測し、不安定テストの修正を次スプリントの最優先タスクに設定する。",
        "manufacturing": "設備連携テストの自動化スクリプトを整備し、変更管理プロセスに組み込む。",
        "system": "SLO・更新手順・ロールバック条件を明文化し、設計レビューで可観測性と障害波及範囲を重点確認する。",
        "_default": "影響範囲をサービス別に切り分け、次スプリントで監視指標と切り戻し条件を実装計画へ落とし込む。",
    },
    "management": {
        "security": "セキュリティ対策費用の追加予算を緊急稟議し、事業継続計画の更新を1週間以内に完了する。",
        "ai": "AI導入PoCの成功基準を数値化し、撤退ラインを含めた判断フレームワークを経営会議で合意する。",
        "industry": "競合ベンチマークと市場シェア推移を更新し、四半期事業計画の修正を即日判断する。",
        "policy": "法規制変更の影響評価を法務と共同で実施し、コンプライアンス対応の優先順位を確定する。",
        "_default": "投資優先順位・規制対応・供給リスクを同じ会議体で決裁し、四半期計画の修正を即日判断する。",
    },
    "consumer": {
        "security": "対象サービスのパスワード変更と二段階認証の設定状況を今週中に確認・更新する。",
        "ai": "AI生成情報を鵜呑みにせず、公式発表と照合してから判断・行動する習慣を今日から実践する。",
        "policy": "規制変更に伴う料金改定や契約条件の変化を調べ、必要に応じてプラン変更を今月中に完了する。",
        "news": "報道内容の一次情報を確認し、自分の生活への影響有無を具体的に判断して必要な手続きを進める。",
        "_default": "価格・使い勝手・個人情報の条件を比較して、契約見直しや利用設定の変更を今週中に実行する。",
    },
}

ROLE_SOURCE_RULES = {
    "engineer": {
        "allow_categories": {"ai", "dev", "security", "manufacturing", "system", "quality", "maintenance", "industry"},
        "allow_keywords": ["ai", "ソフト", "開発", "インフラ", "運用", "セキュリティ", "障害", "データ", "クラウド", "api", "半導体", "品質"],
        "allow_domains": ["github.com", "techcrunch", "zdnet", "itmedia", "aws.amazon", "cloud", "security", "developer"],
        "override_keywords": [],
    },
    "management": {
        "allow_categories": {"industry", "policy", "company", "manufacturing", "security"},
        "allow_keywords": ["市場", "投資", "規制", "ガバナンス", "業績", "提携", "サプライ", "人材", "価格", "収益", "事業", "調達", "決算", "戦略"],
        "allow_domains": ["reuters.com", "nikkei.com", "bloomberg", "wsj.com", "ft.com", "経済", "business"],
        "override_keywords": ["価格", "規制", "供給", "投資", "決算", "インフレ"],
    },
    "consumer": {
        "allow_categories": {"news", "policy", "company", "other", "security"},
        "allow_keywords": ["料金", "値上げ", "ux", "ユーザー", "privacy", "個人情報", "サービス", "サポート", "アプリ", "生活", "使い", "安全", "品質", "インフレ"],
        "allow_domains": ["cnet", "engadget", "lifehacker", "yahoo", "itmedia", "consumer", "support"],
        "override_keywords": ["料金", "値上げ", "インフレ", "補助金", "規制", "電気代", "通信料", "保険料"],
    },
}

DEFAULT_EXCLUDE_KEYWORDS = [
    "天気", "大雨", "台風", "地震速報", "積雪", "熱中症", "洪水",
    "殺人", "逮捕", "強盗", "刺傷", "暴行", "窃盗", "詐欺事件", "放火",
    "芸能", "ゴシップ", "結婚発表", "熱愛", "スポーツ", "勝敗", "ドラフト",
    "野球", "サッカー", "テニス", "ゴルフ", "相撲", "甲子園",
    "Jリーグ", "プロ野球", "五輪", "優勝", "決勝", "試合結果",
]


def _normalize_blob(item: dict) -> str:
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            " ".join([str(k) for k in (item.get("key_points") or [])]),
            " ".join([str(t) for t in (item.get("tags") or [])]),
            str(item.get("source") or ""),
        ]
    ).lower()


def _extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _is_excluded_topic(item: dict, role: str) -> bool:
    blob = _normalize_blob(item)
    rules = ROLE_SOURCE_RULES.get(role, {})
    if any(kw.lower() in blob for kw in rules.get("override_keywords", [])):
        return False
    return any(kw.lower() in blob for kw in DEFAULT_EXCLUDE_KEYWORDS)


def _is_role_compatible(item: dict, role: str, relaxed: bool = False) -> bool:
    if _is_excluded_topic(item, role):
        return False

    rules = ROLE_SOURCE_RULES.get(role, {})
    blob = _normalize_blob(item)
    category = str(item.get("category") or "").lower()
    domain = _extract_domain(str(item.get("url") or ""))

    category_hit = category in rules.get("allow_categories", set())
    keyword_hit = any(kw.lower() in blob for kw in rules.get("allow_keywords", []))
    domain_hit = any(d.lower() in domain for d in rules.get("allow_domains", []))

    if relaxed:
        return category_hit or keyword_hit
    return category_hit or keyword_hit or domain_hit


def _filter_role_candidates(items: list[dict], role: str, relaxed: bool = False) -> list[dict]:
    return [it for it in items if _is_role_compatible(it, role, relaxed=relaxed)]


def _score_item_for_role(item: dict, role: str) -> int:
    profile = ROLE_PROFILES.get(role, {})
    score = int(item.get("importance") or 0) * 10
    text_blob = " ".join([
        str(item.get("title") or "").lower(),
        str(item.get("summary") or "").lower(),
        " ".join([str(k).lower() for k in item.get("key_points") or []]),
        " ".join([str(t).lower() for t in item.get("tags") or []]),
    ])

    for kw in profile.get("keywords", []):
        if kw in text_blob:
            score += 4

    category = str(item.get("category") or "").lower()
    score += int(profile.get("categories", {}).get(category, 0))

    perspectives = item.get("perspectives") or {}
    perspective_text = (perspectives.get(role) or "").strip()
    if perspective_text:
        score += 15

    # 立場に関連しないperspectiveだけ埋まっている記事は過剰評価しない
    other_roles = [r for r in ["engineer", "management", "consumer"] if r != role]
    if not perspective_text and any((perspectives.get(r) or "").strip() for r in other_roles):
        score -= 4
    return score


def _pick_role_articles(items: list[dict], role: str, max_items: int = 3, blocked_ids: set[int] | None = None) -> list[dict]:
    blocked_ids = blocked_ids or set()
    ranked = sorted(items, key=lambda it: (_score_item_for_role(it, role), it.get("dt") or ""), reverse=True)
    picked = []
    for it in ranked:
        item_id = int(it.get("id") or 0)
        if item_id in blocked_ids:
            continue
        picked.append(it)
        if len(picked) >= max_items:
            break
    return picked


def _select_role_articles(items: list[dict], roles: list[str], max_items: int = 3) -> dict[str, list[dict]]:
    selected: dict[str, list[dict]] = {r: [] for r in roles}

    role_candidates = {role: _filter_role_candidates(items, role, relaxed=False) for role in roles}

    # 1周目は立場適合 + 役割間の重複を避ける
    globally_used: set[int] = set()
    for role in roles:
        picked = _pick_role_articles(role_candidates[role], role, max_items=max_items, blocked_ids=globally_used)
        selected[role] = picked
        ids = {int(it.get("id") or 0) for it in picked}
        globally_used.update(ids)

    # 不足分は「同立場の条件を満たす記事」から重複を許容して補完
    for role in roles:
        if len(selected[role]) >= max_items:
            continue
        existing_ids = {int(it.get("id") or 0) for it in selected[role]}
        refill = _pick_role_articles(role_candidates[role], role, max_items=max_items)
        for it in refill:
            item_id = int(it.get("id") or 0)
            if item_id in existing_ids:
                continue
            selected[role].append(it)
            existing_ids.add(item_id)
            if len(selected[role]) >= max_items:
                break

    # それでも不足する場合だけ、少し緩い条件で追加する
    for role in roles:
        if len(selected[role]) >= max_items:
            continue
        relaxed_pool = _filter_role_candidates(items, role, relaxed=True)
        existing_ids = {int(it.get("id") or 0) for it in selected[role]}
        refill = _pick_role_articles(relaxed_pool, role, max_items=max_items)
        for it in refill:
            item_id = int(it.get("id") or 0)
            if item_id in existing_ids:
                continue
            selected[role].append(it)
            existing_ids.add(item_id)
            if len(selected[role]) >= max_items:
                break
    return selected


def _dominant_category(picked_articles: list[dict]) -> str:
    """picked記事の最頻カテゴリを返す。テンプレート選択のキーに使用。"""
    counts: dict[str, int] = {}
    for a in picked_articles:
        cat = str(a.get("category") or "").strip().lower()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    if not counts:
        return "_default"
    return max(counts, key=lambda c: counts[c])


def _extract_role_perspective(article: dict, role: str, max_len: int = 60) -> str:
    """記事のperspectives[role]を優先的に取得。fallback: key_points[0] → _extract_clear_point(title)。"""
    perspectives = article.get("perspectives") or {}
    text = str(perspectives.get(role) or "").strip()
    # 「推測:」プレフィックスを除去
    if text.startswith("推測:"):
        text = text[len("推測:"):].strip()
    if text.startswith("推測："):
        text = text[len("推測："):].strip()
    if text:
        if len(text) > max_len:
            text = text[:max_len].rstrip("、。 ") + "…"
        return text

    key_points = article.get("key_points") or []
    if key_points and isinstance(key_points[0], str) and key_points[0].strip():
        kp = key_points[0].strip()
        if kp.startswith("推測:"):
            kp = kp[len("推測:"):].strip()
        if kp.startswith("推測："):
            kp = kp[len("推測："):].strip()
        if len(kp) > max_len:
            kp = kp[:max_len].rstrip("、。 ") + "…"
        return kp

    return _extract_clear_point(article)


def _extract_clear_point(article: dict) -> str:
    title = str(article.get("title") or "").strip()
    summary = str(article.get("summary") or "").strip()
    perspectives = article.get("perspectives") or {}
    perspective = next((str(v).strip() for v in perspectives.values() if str(v).strip()), "")

    base = title or summary or perspective or "主要トピック"
    base = " ".join(base.split())
    for sep in ["。", "!", "？", "?", "！"]:
        idx = base.find(sep)
        if 0 < idx <= 70:
            base = base[: idx + 1]
            break
    if len(base) > 72:
        base = base[:72].rstrip("、。 ") + "…"
    return base


ENGINEER_BANNED_PHRASES = [
    "総合的に判断すべき",
    "バランスが重要",
    "今後の動向を注視",
    "詳細は引き続き確認",
    "ケースバイケース",
]


def _sanitize_engineer_phrase(text: str) -> str:
    cleaned = str(text or "")
    for phrase in ENGINEER_BANNED_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    return " ".join(cleaned.split())


def _build_combined_opinion(role: str, picked_articles: list[dict]) -> str:
    """立場別の意見を記事のperspectivesから動的に構成する。"""
    role_map = {"engineer": "技術者", "management": "経営者", "consumer": "消費者"}
    role_label = role_map.get(role, role)

    if not picked_articles:
        return (
            f"主張: 本日は{role_label}の判断に直結する記事が不足している。"
            f"根拠: 立場条件を満たす一次情報が見つからなかった。"
            f"影響: 次回更新で追加情報を確認し、判断を再提示する。"
        )

    def _strip_guess(text: str) -> str:
        for prefix in ("推測:", "推測："):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text

    def _get_persp(art, r):
        return _strip_guess(((art.get("perspectives") or {}).get(r) or "").strip())

    def _get_summary(art):
        s = (art.get("summary") or "").strip()
        return s if s and s != "（要約を生成できませんでした）" else ""

    def _first_kp(art):
        for kp in (art.get("key_points") or []):
            if isinstance(kp, str) and kp.strip() and not kp.strip().startswith("推測"):
                return kp.strip()
        return ""

    # --- 主張: 先頭記事の perspective を最優先 ---
    lead = picked_articles[0]
    lead_persp = _get_persp(lead, role)
    lead_summary = _get_summary(lead)

    if lead_persp:
        claim_core = lead_persp
    elif lead_summary:
        claim_core = lead_summary
        if len(claim_core) > 80:
            claim_core = claim_core[:80].rstrip("、。 ") + "…"
    else:
        dominant_cat = _dominant_category(picked_articles)
        templates = CATEGORY_CLAIM_TEMPLATES.get(role, CATEGORY_CLAIM_TEMPLATES["engineer"])
        claim_core = templates.get(dominant_cat, templates["_default"])

    claim = f"主張: {role_label}としては、{claim_core}。"

    # --- 根拠: 2・3番目の記事から perspectives/key_points ---
    evidence_parts = []
    for art in picked_articles[1:3]:
        persp = _get_persp(art, role)
        kp = _first_kp(art)
        summary = _get_summary(art)
        source = (art.get("source") or "").strip()
        substance = persp or kp or summary
        if substance:
            src_note = f"（{source}）" if source else ""
            evidence_parts.append(f"根拠: {substance}{src_note}。")

    if not evidence_parts:
        lead_kp = _first_kp(lead)
        if lead_kp:
            evidence_parts.append(f"根拠: {lead_kp}。")
        elif lead_summary and lead_summary != claim_core:
            evidence_parts.append(f"根拠: {lead_summary}。")
        else:
            evidence_parts.append("根拠: 一次情報の追加確認が必要。")

    evidence = "".join(evidence_parts)

    # --- 影響: カテゴリ別アクション ---
    dominant_cat = _dominant_category(picked_articles)
    action_templates = CATEGORY_ACTION_TEMPLATES.get(role, CATEGORY_ACTION_TEMPLATES["engineer"])
    action = action_templates.get(dominant_cat, action_templates["_default"])
    impact = f"影響: {action}"

    text = f"{claim}{evidence}{impact}"
    return _fit_text_length(text, target=330, min_len=260, max_len=420)


def _extract_conclusion_line(opinion: str) -> str:
    m = re.search(r"主張:\s*([^。]+。)", opinion)
    if m:
        return m.group(1).strip()
    s = " ".join((opinion or "").split())
    if len(s) > 70:
        return s[:70].rstrip("、。 ") + "…"
    return s


def _extract_recommended_action_line(opinion: str, fallback: str = "関係者合意のもとで段階導入を進める。") -> str:
    if not (opinion or "").strip():
        return fallback
    m = re.search(r"影響:\s*([^。]+。)", opinion)
    if m and len(m.group(1).strip()) >= 5:
        return m.group(1).strip()
    sentences = [s.strip() + "。" for s in re.findall(r"([^。]+)。", opinion) if len(s.strip()) >= 5]
    if sentences:
        return sentences[-1]
    return fallback


DISCUSSION_QUESTION_TEMPLATES = {
    ("engineer", "management"): "技術的なリスク評価と実装コストの見積もりを先に共有しないと、投資判断の精度が下がりませんか。",
    ("engineer", "consumer"): "実装上の制約やセキュリティ要件を利用者目線で説明しないと、機能への期待値がずれませんか。",
    ("management", "engineer"): "事業目標と撤退基準を先に明示しないと、技術選定の優先順位が定まらないのではないですか。",
    ("management", "consumer"): "価格改定や契約条件の変更を利用者視点で検証しないと、解約リスクを見誤りませんか。",
    ("consumer", "engineer"): "利用者が実際に困る場面を起点にして優先順位を決めた方が、実効性が高くないですか。",
    ("consumer", "management"): "利用者の負担増やサービス品質低下を経営指標に組み込まないと、長期的な信頼を失いませんか。",
}

DISCUSSION_ANSWER_TEMPLATES = {
    ("engineer", "management"): "技術負債の可視化とリスク定量化を先行し、経営判断に必要なデータを揃える進め方が現実的です。",
    ("engineer", "consumer"): "利用者フィードバックを設計段階で取り込み、段階リリースで体験品質を検証する方法が有効です。",
    ("management", "engineer"): "事業KPIと技術KPIの対応表を作成し、四半期ごとに優先度を再評価する枠組みが必要です。",
    ("management", "consumer"): "料金変更前に利用者影響のシミュレーションを実施し、緩和策とセットで意思決定すべきです。",
    ("consumer", "engineer"): "ユーザビリティテストの結果を技術要件に反映し、改善効果を定量的に追跡する仕組みが求められます。",
    ("consumer", "management"): "顧客満足度と解約率を経営ダッシュボードに組み込み、サービス品質を定期的にレビューすべきです。",
}


def _build_role_discussion(role_sections: list[dict]) -> dict[str, list[dict[str, str]]]:
    """立場間ディスカッションを記事の perspectives から動的に生成する。"""
    role_map = {str(section.get("role") or ""): section for section in role_sections}
    role_order = ["engineer", "management", "consumer"]
    role_labels = {"engineer": "技術者", "management": "経営者", "consumer": "消費者"}
    default_reco = "関係者レビューを実施し、リスクと優先順位を更新する。"

    def _lead_perspective(section, role):
        """セクションの先頭記事から perspective[role] を取得する。"""
        for art in (section.get("articles") or [])[:1]:
            text = ((art.get("perspectives") or {}).get(role) or "").strip()
            for prefix in ("推測:", "推測："):
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            if text:
                return text
        return ""

    discussions_by_role: dict[str, list[dict[str, str]]] = {}
    for focus_role in role_order:
        focus_sec = role_map.get(focus_role, {})
        focus_summary = str(focus_sec.get("summary") or "")
        focus_reco = str(focus_sec.get("recommendation") or default_reco)
        focus_persp = _lead_perspective(focus_sec, focus_role)
        focus_discussions: list[dict[str, str]] = []

        for other_role in role_order:
            if other_role == focus_role:
                continue
            other_sec = role_map.get(other_role, {})
            other_persp = _lead_perspective(other_sec, other_role)

            # 質問: 相手の perspective から動的生成、なければテンプレート
            if other_persp:
                question = f"『{other_persp}』の観点からすると、{focus_summary}だけでは判断材料が不十分ではないですか。"
            else:
                q_tmpl = DISCUSSION_QUESTION_TEMPLATES.get(
                    (other_role, focus_role),
                    "前提条件と受け入れ基準を先に合意しないと実行リスクが残りませんか。",
                )
                other_summary = str(other_sec.get("summary") or "")
                question = f"{other_summary}の観点では、{q_tmpl}" if other_summary else q_tmpl

            # 回答: 自分の perspective から動的生成、なければテンプレート
            if focus_persp:
                answer = f"{focus_persp}を踏まえ、まずは『{focus_reco}』を小さく試して検証する進め方が現実的です。"
            else:
                answer = DISCUSSION_ANSWER_TEMPLATES.get(
                    (focus_role, other_role),
                    f"まずは『{focus_reco}』を小さく試し、運用データで妥当性を確認する進め方が現実的です。",
                )

            focus_discussions.append({
                "from": role_labels[other_role],
                "to": role_labels[focus_role],
                "type": "question",
                "text": question,
            })
            focus_discussions.append({
                "from": role_labels[focus_role],
                "to": role_labels[other_role],
                "type": "answer",
                "text": answer,
            })

        discussions_by_role[focus_role] = focus_discussions
    return discussions_by_role


EXEC_GAPS_BY_CAT = {
    "security": [
        "インシデントの影響範囲（顧客数・データ量）が未定量。",
        "対策費用と事業継続への影響額の試算が不足。",
    ],
    "ai": [
        "AI導入のROI試算と撤退基準が未定義。",
        "モデル精度の事業KPIへの影響が未接続。",
    ],
    "manufacturing": [
        "設備投資の回収期間と需給変動リスクの同時評価が不足。",
        "生産ラインへの影響範囲と代替手段が未検討。",
    ],
    "policy": [
        "規制変更の事業インパクト（コスト増・参入障壁）が未定量。",
        "対応期限と未対応時のペナルティが未整理。",
    ],
    "industry": [
        "競合動向に対する自社ポジションのギャップが未分析。",
        "市場構造変化の中期シナリオ（楽観/悲観）が未作成。",
    ],
    "_default": [
        "売上・利益・キャッシュへの影響額の幅が見えない。",
        "今四半期で判断すべき期限と先送りリスクが未明示。",
    ],
}

EXEC_ACTIONS_BY_CAT = {
    "security": [
        "インシデント対応の追加予算を緊急稟議し、24時間以内に初動方針を確定する。",
        "事業継続計画の更新と関係者への説明資料を1週間以内に準備する。",
    ],
    "ai": [
        "POCの成功基準を数値化し、撤退ラインを経営会議で合意する。",
        "AI投資額と回収見込みを事業計画に明記し、四半期レビューに組み込む。",
    ],
    "manufacturing": [
        "設備投資の優先順位を需給予測と連動させて即日再評価する。",
        "現場影響のシミュレーションを実施し、代替計画とセットで稟議する。",
    ],
    "policy": [
        "法規制変更の影響評価を法務と共同で実施し、対応優先度を確定する。",
        "コンプライアンス対応の費用と期限を経営会議の議題に追加する。",
    ],
    "industry": [
        "競合ベンチマークと市場シェアを更新し、戦略見直しの要否を判断する。",
        "サプライチェーンリスクの定量評価を調達部門と共同で実施する。",
    ],
    "_default": [
        "各論点に投資額・回収見込み・未対応リスクを1行で併記する。",
        "「24時間以内」「今週中」「四半期内」の3段階で意思決定項目を分ける。",
    ],
}


def _build_dynamic_exec_brief(role_sections: list[dict], opinion_items: list[dict]) -> dict:
    """当日のトピック構成に基づく動的な経営者向けチェック項目を生成する。"""
    management = next((s for s in role_sections if s.get("role") == "management"), None)
    if not management:
        return {"summary": "", "recommendation": "", "gaps": [], "actions": [], "categories": []}

    # カテゴリ分布を分析
    cat_counts: dict[str, int] = {}
    for item in opinion_items[:15]:
        cat = (item.get("category") or "other").lower()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    dominant_cats = [c for c, _ in sorted(cat_counts.items(), key=lambda x: -x[1])[:3]]

    # カテゴリ別の不足情報と是正アクションを集約
    gaps: list[str] = []
    actions: list[str] = []
    for cat in dominant_cats:
        gaps.extend(EXEC_GAPS_BY_CAT.get(cat, EXEC_GAPS_BY_CAT["_default"]))
        actions.extend(EXEC_ACTIONS_BY_CAT.get(cat, EXEC_ACTIONS_BY_CAT["_default"]))

    # 重複除去して上限4件
    seen = set()
    unique_gaps = [g for g in gaps if g not in seen and not seen.add(g)][:4]
    seen.clear()
    unique_actions = [a for a in actions if a not in seen and not seen.add(a)][:4]

    return {
        "summary": management.get("summary", ""),
        "recommendation": management.get("recommendation", ""),
        "gaps": unique_gaps,
        "actions": unique_actions,
        "categories": dominant_cats,
    }


def _extract_labelled_sentences(opinion: str, label: str) -> list[str]:
    pattern = rf"{label}:\s*([^。]+。)"
    return [m.strip() for m in re.findall(pattern, opinion or "") if m.strip()]


def _build_opinion_preview_lines(opinion: str, min_lines: int = 2, max_lines: int = 3) -> list[str]:
    lines: list[str] = []
    lines.extend(_extract_labelled_sentences(opinion, "根拠"))
    lines.extend(_extract_labelled_sentences(opinion, "影響"))

    if len(lines) < min_lines:
        raw_sentences = [s.strip() + "。" for s in re.findall(r"([^。]+)。", opinion or "") if s.strip()]
        claim_sentences = set(_extract_labelled_sentences(opinion, "主張"))
        for sent in raw_sentences:
            if sent in claim_sentences:
                continue
            if sent not in lines:
                lines.append(sent)
            if len(lines) >= min_lines:
                break

    return lines[:max_lines]


def _build_opinion_body_sections(opinion: str) -> list[dict[str, str]]:
    labelled = list(re.finditer(r"(主張|根拠|影響):\s*([^。]+。)", opinion or ""))
    if not labelled:
        raw = " ".join((opinion or "").split())
        return [{"label": "本文", "text": raw}] if raw else []

    counts = {"主張": 0, "根拠": 0, "影響": 0}
    sections: list[dict[str, str]] = []
    for m in labelled:
        label = m.group(1)
        counts[label] += 1
        display_label = label
        if label == "根拠" and counts[label] >= 2:
            display_label = f"根拠 {counts[label]}"
        sections.append({"label": display_label, "text": m.group(2).strip()})
    return sections


def _build_primary_evidence_line(picked_articles: list[dict]) -> str:
    if not picked_articles:
        return "関連一次情報の追加確認が必要（出典精査中）"

    lead = picked_articles[0]
    title = str(lead.get("title") or lead.get("summary") or "主要トピック").strip()
    source = str(lead.get("source") or "出典未記載").strip()
    importance = lead.get("importance")
    if importance is not None:
        return f"{title}（{source} / 重要度 {importance}）"
    return f"{title}（{source}）"


def _build_top_evidence_tags(picked_articles: list[dict], limit: int = 2) -> list[str]:
    tags: list[str] = []
    for article in picked_articles:
        label = _extract_clear_point(article)
        if not label:
            continue
        if label in tags:
            continue
        tags.append(label)
        if len(tags) >= limit:
            break
    return tags

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
            Template(NEWS_HTML).render(
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
            # （現実装: 代表フラグあり=16列 / 旧互換=15列）
            if len(r) >= 16:
                (
                    article_id, title, url, source, category, published_at, fetched_at, dt,
                    importance, typ, summary, key_points, perspectives, tags, evidence_urls,
                    is_representative,
                ) = r
            else:
                (
                    article_id, title, url, source, category, published_at, fetched_at, dt,
                    importance, typ, summary, key_points, perspectives, tags, evidence_urls,
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
    .pred-card-title{font-weight:800;font-size:15px;margin-bottom:8px;line-height:1.5;color:var(--text-main)}
    .highlight .pred-card-title{font-size:16px;color:#991b1b}
    .pred-card-body{font-size:14px;line-height:1.7;color:var(--text-main)}
    .pred-card-body p{margin:6px 0}
    .pred-card-body ul,.pred-card-body ol{margin:6px 0;padding-left:20px}
    .forecast-panel.active{display:block}
    .forecast-panel h2,.forecast-panel h3{margin-top:16px}
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
    .past-reports ul{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:8px}
    .past-reports li a{display:inline-block;padding:4px 12px;border:1px solid var(--border);
      border-radius:6px;font-size:.85rem;text-decoration:none;color:var(--text-main)}
    .past-reports li a:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
    /* === モバイル (640px以下) === */
    @media(max-width:640px){
      .forecast-tabs{gap:3px}
      .forecast-tabs button{padding:5px 10px;font-size:.78rem}
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
</head>
<body>
  <h1>未来予測レポート</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/forecast/" class="{{ 'active' if page=='forecast' else '' }}">未来予測</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
  </div>

  <div class="summary-card" style="margin:16px 0">
    <div class="summary-grid">
      <div class="summary-item"><div class="k">Generated (JST)</div><div class="v">{{ generated_at }}</div></div>
      <div class="summary-item"><div class="k">レポート日付</div><div class="v">{{ report_date }}</div></div>
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
            id="pred-tab-{{ loop.index0 }}">{{ horizon }}</button>
    {% endfor %}
  </div>
  {% for horizon in prediction_keys %}
  <div class="forecast-panel {{ 'active' if loop.first else '' }}" id="pred-panel-{{ loop.index0 }}">
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

  <!-- 過去レポート一覧 -->
  {% if past_reports %}
  <div class="past-reports">
    <h3>過去のレポート</h3>
    <ul>
      {% for pr in past_reports %}
      <li><a href="?date={{ pr.date }}">{{ pr.date }}</a></li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}

  {% else %}
  <div class="no-report">
    <p style="font-size:1.2rem">未来予測レポートはまだ生成されていません</p>
    <p>ローカル環境で未来予測パイプラインを実行し、<br>
       <code>python src/forecast_import.py &lt;レポート.md&gt;</code> でインポートしてください。</p>
  </div>
  {% endif %}

  <script src="{{ common_js_src }}"></script>
  <script>
    function switchTab(group, idx) {
      document.querySelectorAll('#' + group + '-tabs button').forEach(function(b, i) {
        b.classList.toggle('active', i == idx);
      });
      document.querySelectorAll('[id^="' + group + '-panel-"]').forEach(function(p, i) {
        p.classList.toggle('active', i == idx);
      });
    }
    if (window.DTTCommon) window.DTTCommon.setupCommon('forecast');
  </script>
</body>
</html>
"""


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
        SELECT report_date, file_path, executive_summary
        FROM forecast_reports
        ORDER BY report_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    # 過去レポート一覧
    cur.execute("""
        SELECT report_date FROM forecast_reports
        ORDER BY report_date DESC
    """)
    past_reports = [{"date": r[0]} for r in cur.fetchall()]

    has_report = False
    report = ForecastReport()
    report_date = "-"

    if row:
        report_date = row[0]
        file_path = Path(row[1])
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
    prediction_items = {}
    for k, v in report.predictions.items():
        items = parse_prediction_items(v)
        rendered = []
        for item in items:
            rendered.append({
                "impact": item.impact,
                "confidence": item.confidence,
                "title": item.title,
                "body_html": md_to_html(item.body),
            })
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
        past_reports=past_reports[1:] if len(past_reports) > 1 else [],
    )

    forecast_dir = Path(out_dir) / "forecast"
    forecast_dir.mkdir(exist_ok=True)
    (forecast_dir / "index.html").write_text(forecast_html, encoding="utf-8")
    print(f"  forecast page: {forecast_dir / 'index.html'}")


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
            {"id": tid, "title": clean_for_html(title), "articles": int(total), "recent": int(recent),"date": article_date}
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
                  i.perspectives
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
                  i.perspectives
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
            tid, title, url, article_date, recent, source, importance, summary, key_points, evidence_urls, tags, perspectives = r
            items.append(
                {
                    "id": tid,
                    "title": clean_for_html(title),  # ← ここはSQLで title_ja 優先済み
                    "url": url or "#",
                    "date": article_date,
                    "recent": int(recent or 0),
                    "source": source or "",
                    "importance": int(importance) if importance is not None else None,
                    "summary": summary or "",
                    "key_points": _safe_json_list(key_points),
                    "evidence_urls": _safe_json_list(evidence_urls),
                    "tags": _safe_json_list(tags),
                    "perspectives": _safe_json_obj(perspectives),
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
                  i.perspectives
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
                  i.perspectives
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
                tid, title, url, article_date, recent, source, importance, summary, key_points, evidence_urls, tags, perspectives = r
                items.append(
                    {
                        "id": tid,
                        "title": clean_for_html(title),
                        "url": url or "#",
                        "date": article_date,
                        "recent": int(recent or 0),
                        "source": source or "",
                        "importance": int(importance) if importance is not None else None,
                        "summary": summary or "",
                        "key_points": _safe_json_list(key_points),
                        "evidence_urls": _safe_json_list(evidence_urls),
                        "tags": _safe_json_list(tags),
                        "perspectives": _safe_json_obj(perspectives),
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
    except Exception:
        pass  # feed_healthテーブルが無い場合

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
    except Exception:
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
          i.perspectives
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
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",
            "date": article_date,
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
          i.perspectives
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
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",
            "date": article_date,
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
      i.perspectives
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
    for tid, title, category, url, article_date,recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",  # 今は空でOK（後で短文化したければ追加）
            "date": article_date,
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
          i.perspectives
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
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",
            "date": article_date,
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
          i.perspectives
        FROM topics t
        LEFT JOIN topic_insights i ON i.topic_id = t.id
        WHERE COALESCE(NULLIF(t.category,''), 'other') = 'market'
        ORDER BY COALESCE(i.importance,0) DESC, COALESCE(recent,0) DESC, t.id ASC
        LIMIT 10
        """,
        (cutoff_48h,),
    )
    market_top = []
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",
            "date": article_date,
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
          i.perspectives
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
    for tid, title, category, url, article_date, recent, importance, summary, tags, perspectives in cur.fetchall():
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
            "one_liner": "",
            "date": article_date,
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

    _render_errors = []

    try:
        (tech_dir / "index.html").write_text(tech_html_sub, encoding="utf-8")
        (out_dir / "index.html").write_text(tech_html_root, encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] render tech pages failed: {e}")
        _render_errors.append(("tech", str(e)))

    try:
        ops_dir = out_dir / "ops"
        ops_dir.mkdir(exist_ok=True)
        ops_assets = build_asset_paths()
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
            primary_ratio_by_category=primary_ratio_by_category,
            primary_ratio_threshold=primary_ratio_threshold,
        )
        (ops_dir / "index.html").write_text(ops_html, encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] render ops page failed: {e}")
        _render_errors.append(("ops", str(e)))

    try:
        render_news_pages(out_dir, generated_at, cur)
    except Exception as e:
        print(f"[ERROR] render news pages failed: {e}")
        _render_errors.append(("news", str(e)))

    try:
        render_forecast_page(out_dir, generated_at, cur)
    except Exception as e:
        print(f"[ERROR] render forecast page failed: {e}")
        _render_errors.append(("forecast", str(e)))

    conn.close()

    if _render_errors:
        print(f"[WARN] render completed with {len(_render_errors)} error(s): {_render_errors}")
    print(f"[TIME] step=render end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
