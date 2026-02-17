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
    dt = datetime.fromisoformat(s.replace("Z",""))
    return dt.astimezone(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M")

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
    <h2 style="margin:0 0 6px">意見（お試し版）</h2>
    <div class="small">3つの立場で、記事を400文字前後の意見として整理</div>
    <a class="btn" href="./opinion/index.html">意見ページを見る →</a>
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
    <a href="/daily-tech-trend/opinion/" class="{{ 'active' if page=='opinion' else '' }}">意見（お試し版）</a>
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
      <ul>
        {% for t in topics_by_cat[cat.id] %}
           <li id="topic-{{ t.id }}" class="topic-row"
              data-title="{{ t.title|e }}"
              data-summary="{{ (t.summary or '')|e }}"
              data-imp="{{ t.importance or 0 }}"
              data-recent="{{ t.recent or 0 }}"
              data-date="{{ t.date }}"
              data-tags="{{ t.tags|default([])|join(',') }}">
            <div>
              {% if t.importance is not none %}
                <span class="badge imp">重要度 {{ t.importance }}</span>
              {% endif %}
              {% if t.url and t.url != "#" %}
                <a href="{{ t.url }}" target="_blank" rel="noopener">{{ t.title }}</a>
              {% else %}
                {{ t.title }}
              {% endif %}
              {% if t.date %}
                <span class="small">（{{ fmt_date(t.date) }}）</span>
              {% endif %}

              {% if t.recent > 0 %}
                <span class="badge recent {% if (t.recent or 0) >= 5 %}hot{% endif %}">
                  48h +{{ t.recent }}
                </span>
              {% endif %}
              {% if t.tags and t.tags|length>0 %}
                <span class="small">
                  {% for tg in t.tags %}
                    <span class="badge">{{ tg }}</span>
                  {% endfor %}
                </span>
              {% endif %}
            </div>

            {% if t.summary %}
              <div class="summary-preview">{{ t.summary[:80] }}{% if t.summary|length > 80 %}…{% endif %}</div>
            {% endif %}
            {% if t.source %}<div class="mini">{{ t.source }}</div>{% endif %}

            {% if t.summary or (t.key_points and t.key_points|length>0) or (t.perspectives) or (t.evidence_urls and t.evidence_urls|length>0) %}
              <details class="insight" role="group">
                <summary class="small">要約・解説を表示</summary>

                {% if t.summary %}
                  <div><strong>要約</strong>：{{ t.summary }}</div>
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
                  <div style="margin-top:6px;"><strong>次アクション</strong></div>
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
    <a href="/daily-tech-trend/opinion/" class="{{ 'active' if page=='opinion' else '' }}">意見（お試し版）</a>
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
      <ul>
        {% for it in sec.rows %}
          <li id="news-{{ it.id }}" class="topic-row"
            data-title="{{ it.title|e }}"
            data-summary="{{ (it.summary or '')|e }}"
            data-imp="{{ it.importance or 0 }}"
            data-date="{{ it.dt }}"
            data-tags="{{ it.tags|default([])|join(',') }}">

           <div>
            <span class="badge imp">重要度 {{ it.importance or 0 }}</span>
            {% if it.is_representative %}<span class="badge">代表記事</span>{% endif %}
            <a class="topic-link" href="{{ it.url }}" target="_blank" rel="noopener">{{ it.title }}</a>
            <span class="date">{{ it.dt_jst }}</span>
            {% if it.tags and it.tags|length>0 %}
              <span class="small">
                {% for tg in it.tags %}
                  <span class="badge">{{ tg }}</span>
                {% endfor %}
              </span>
            {% endif %}
          </div>

          {% if it.summary %}
            <div class="summary-preview">{{ it.summary[:80] }}{% if it.summary|length > 80 %}…{% endif %}</div>
          {% endif %}
          {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}

           {% if it.importance_basis or it.summary or (it.key_points and it.key_points|length>0) or (it.perspectives and (it.perspectives.engineer or it.perspectives.management or it.perspectives.consumer)) %}
              <details class="insight" role="group">
                <summary class="small">要約・解説を表示</summary>
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
  <title>意見（お試し版）</title>
  <meta name="description" content="技術者・経営者・消費者の3つの立場で、直近記事を400文字前後の意見として整理した試験ページ。">
  <link rel="canonical" href="/daily-tech-trend/opinion/">
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

    .opinion-toc{margin:8px 0 16px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--bg-soft)}
    .opinion-toc strong{font-size:13px}
    .opinion-toc ul{margin:8px 0 0;padding-left:18px;display:flex;gap:10px;flex-wrap:wrap}
    .opinion-toc a{font-size:13px}
    .role-vertical h2{margin:0 0 14px}
    .role-vertical .section-heading{margin:22px 0 10px;font-size:18px;font-weight:800}
    .role-vertical .news-source-list{margin:0;padding-left:20px}
    .role-vertical .news-source-list li{margin:14px 0}
    .role-vertical .opinion-body{margin-top:10px;line-height:1.8;color:var(--text-main);font-size:15px}
    .role-vertical .opinion-paragraph{margin:12px 0;padding:10px 12px;border-left:3px solid var(--accent-soft);background:#f8fbff;border-radius:8px}
    .role-vertical .opinion-label{display:inline-block;margin-bottom:4px;font-size:12px;font-weight:700;color:#1f4fbf}
    .role-vertical .opinion-text{display:block;line-height:1.9;color:var(--text-main)}
    .role-discussion{margin:12px 0 8px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--bg-soft)}
    .role-discussion ul{margin:8px 0 0;padding-left:18px}
    .role-discussion li{margin:8px 0}
    .role-vertical details.insight[open]{padding:10px 14px}
    .role-vertical details.insight[open] > *:not(summary){margin-top:10px}
    .role-vertical details.insight[open] .opinion-body + .section-heading{margin-top:18px}
    .sticky-mini-nav{position:fixed;right:12px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:20}
    .sticky-mini-nav a,.sticky-mini-nav button{padding:8px 10px;border-radius:999px;border:1px solid var(--border);background:var(--bg);font-size:12px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.08)}
    .sticky-mini-nav .mini-toc{display:none}
    @media (max-width: 640px){
      .role-vertical{line-height:1.75}
      .role-vertical .small{line-height:1.8}
      .role-vertical p,.role-vertical li{margin-top:14px;margin-bottom:14px}
      .role-vertical details.insight[open]{padding:12px 16px}
      .role-vertical .opinion-body{padding:0 2px;line-height:1.9}
      .role-vertical .news-source-list li{margin:16px 0}
      .role-vertical .section-heading{margin:20px 0 10px}
    }
    @media (min-width: 821px){
      .sticky-mini-nav .mini-toc{display:inline-block}
    }
  </style>
</head>
<body id="top">
  <h1>意見（お試し版）</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/opinion/" class="{{ 'active' if page=='opinion' else '' }}">意見（お試し版）</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
  </div>

  <div class="summary-card">
    <div class="summary-title">今日の要点（意見・お試し版）</div>
    <div class="summary-grid">
      <div class="summary-item"><div class="k">Generated (JST)</div><div class="v">{{ generated_at }}</div></div>
      <div class="summary-item"><div class="k">対象記事数</div><div class="v">{{ source_item_count }}</div></div>
      <div class="summary-item"><div class="k">文字数目標</div><div class="v">各立場 260〜420文字</div></div>
      <div class="summary-item"><div class="k">立場</div><div class="v">技術者 / 経営者 / 消費者</div></div>
    </div>
  </div>

  <p class="small" style="margin:6px 0 10px;">まずは「比較表示」で結論を見比べ、気になる立場だけ「縦スクロール表示」の詳細を読むのがおすすめです。</p>

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
    <div class="small"><strong>要約（2〜3行）</strong></div>
    <ul class="small" style="margin:6px 0 8px;">
      {% for line in role.preview_lines %}
      <li>{{ line }}</li>
      {% endfor %}
    </ul>
    <div class="small"><strong>主要根拠</strong>: {{ role.primary_evidence }}</div>
    <div class="small"><strong>推奨アクション</strong>: {{ role.recommendation }}</div>
    <div class="small">{{ role.focus }}</div>
    {% if role.discussion_pairs %}
    <div class="role-discussion">
      <div class="small"><strong>立場間ディスカッション（仕様検討）</strong></div>
      <ul class="small">
        {% for pair in role.discussion_pairs %}
        <li><strong>{{ pair.from }}＞{{ pair.to }}</strong> {{ pair.text }}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}
    {% if role.selection_note %}
    <div class="small" style="color:#b45309; margin-top:6px;">{{ role.selection_note }}</div>
    {% endif %}
    <details class="insight">
      <summary class="small">詳細を読む（{{ role.label }}の意見約{{ role.full_text_len }}文字・ニュースソース）</summary>
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
          <div class="small">{{ art.source }} / 重要度 {{ art.importance }}</div>
          <div class="small">公開日時: {{ art.published_at_jst or '不明' }} / 取得元時刻: {{ art.fetched_at_jst or '不明' }}</div>
          <div class="small">重要度理由: {{ art.importance_basis or '重要語・カテゴリ一致・鮮度から総合判定' }}</div>
        </li>
        {% endfor %}
      </ul>
      {% if not role.articles %}
      <div class="small">本日は該当する記事が少ないため、無関係なニュースは採用していません。</div>
      {% endif %}
    </details>
  </section>
  {% endfor %}

  <div class="sticky-mini-nav" aria-label="スクロール補助">
    <a class="mini-toc" href="#top">目次へ戻る</a>
    <button type="button" class="back-to-top">先頭へ戻る</button>
  </div>

  <script src="{{ common_js_src }}"></script>
  <script>
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
  <title>運用メトリクス | Daily Tech Trend</title>
  <meta name="description" content="Source露出（競合比較）とカテゴリ別 一次情報比率を確認し、収集改善アクションに繋げる運用ページ。">
  <link rel="canonical" href="/daily-tech-trend/ops/">
  <link rel="stylesheet" href="{{ common_css_href }}">
</head>
<body>
  <h1>運用メトリクス</h1>
  <div class="nav">
    <a href="/daily-tech-trend/" class="{{ 'active' if page=='tech' else '' }}">技術</a>
    <a href="/daily-tech-trend/news/" class="{{ 'active' if page=='news' else '' }}">ニュース</a>
    <a href="/daily-tech-trend/opinion/" class="{{ 'active' if page=='opinion' else '' }}">意見（お試し版）</a>
    <a href="/daily-tech-trend/ops/" class="{{ 'active' if page=='ops' else '' }}">運用</a>
  </div>

  <div class="summary-card">
    <div class="summary-title">今日の要点（運用）</div>
    <div class="summary-grid">
      <div class="summary-item"><div class="k">Generated (JST)</div><div class="v">{{ meta.generated_at_jst }}</div></div>
      <div class="summary-item"><div class="k">Articles</div><div class="v">{{ meta.total_articles }} <span class="small">(new48h {{ meta.new_articles_48h }})</span></div></div>
      <div class="summary-item"><div class="k">RSS Sources</div><div class="v">{{ meta.rss_sources }}</div></div>
      <div class="summary-item"><div class="k">Primary Threshold</div><div class="v">{{ (primary_ratio_threshold * 100)|round(0)|int }}%</div></div>
    </div>
  </div>

  <section class="top-col" style="margin:8px 0 16px;">
    <h2>🏭 Source露出（競合比較）</h2>
    <div class="metric-note">
      <div>露出が特定企業に偏っていないか、全期間と48hで確認します。</div>
      <div>改善案: 上位3社への偏りが続く場合は、同カテゴリの一次ソースを追加して偏りを緩和。</div>
    </div>
    {% if source_exposure and source_exposure|length > 0 %}
      <table class="source-table">
        <thead><tr><th>企業</th><th class="num">露出</th><th class="num">48h</th><th>主カテゴリ</th></tr></thead>
        <tbody>
        {% for s in source_exposure %}
          <tr><td>{{ s.source }}</td><td class="num">{{ s.total }}</td><td class="num">{{ s.recent48 }}</td><td>{{ s.categories }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="meta">該当ソースなし</div>
    {% endif %}
  </section>

  <section class="top-col" style="margin:8px 0 16px;">
    <h2>🧭 カテゴリ別 一次情報比率</h2>
    <div class="small" style="margin-bottom:8px">一次情報率 = primary / 全記事（tech）。閾値 {{ (primary_ratio_threshold * 100)|round(0)|int }}% 未満は警告表示。</div>
    {% if primary_ratio_by_category and primary_ratio_by_category|length > 0 %}
      <table class="source-table">
        <thead>
          <tr><th>カテゴリ</th><th class="num">一次情報率</th><th class="num">primary</th><th class="num">total</th><th>ステータス</th></tr>
        </thead>
        <tbody>
          {% for r in primary_ratio_by_category %}
            <tr>
              <td>{{ cat_name.get(r.category, r.category) }}</td>
              <td class="num">{{ r.ratio_pct }}%</td>
              <td class="num">{{ r.primary_count }}</td>
              <td class="num">{{ r.total_count }}</td>
              <td>{% if r.warn %}<span class="warn-text">⚠ 閾値未達（{{ r.warn_reason }}）</span>{% else %}OK{% endif %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="meta">カテゴリ集計対象なし</div>
    {% endif %}
  </section>

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


def _build_trial_opinion(item: dict, role: str) -> str:
    role_map = {
        "engineer": "技術者",
        "management": "経営者",
        "consumer": "消費者",
    }
    role_label = role_map.get(role, role)
    perspectives = item.get("perspectives") or {}
    perspective_text = (perspectives.get(role) or "").strip()
    summary = (item.get("summary") or "").strip()
    key_points = [kp for kp in (item.get("key_points") or []) if isinstance(kp, str) and kp.strip()]
    key_points_text = " / ".join(key_points[:2]) if key_points else "主要ポイントは本文確認が必要"
    url = (item.get("url") or "").strip()

    text = (
        f"{role_label}としての考え方は、まず『{summary or '事実関係'}』を起点に、"
        f"優先順位と影響範囲を切り分けること。"
        f"行動としては、{perspective_text or '関係者と現状を共有し、対応方針を具体化する'}。"
        f"加えて、{key_points_text}を確認し、当日中に実行計画へ落とし込む。"
        f"注意点は、断片情報で結論を急がず、推測と事実を明確に分離すること。"
        f"コスト・品質・信頼への副作用を先に洗い出し、説明可能な判断を維持する。"
        f"参考記事: {url or 'URL未取得'}"
    )
    return _fit_text_length(text)


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
    role_map = {"engineer": "技術者", "management": "経営者", "consumer": "消費者"}
    role_label = role_map.get(role, role)
    if not picked_articles:
        if role == "engineer":
            return (
                "主張: 技術者としては、機能拡張より先に監視指標と切り戻し手順を前提にした仕様確定を優先する。"
                "根拠: 可観測性軸では、立場条件を満たす一次情報が不足しているため監視設計の妥当性を検証できない。"
                "根拠: 依存関係・権限境界軸では、無関係な記事を採用すると責務分離の前提を誤る。"
                "影響: SLO・更新手順・ロールバック条件を先に明文化し、追加情報が揃い次第に実装判断を再提示する。"
            )
        return f"主張: 本日は{role_label}の判断に直結する記事が少ないため、結論は保留する。根拠: 立場条件を満たす一次情報が不足しており、無関係な記事は採用しない。影響: 次回更新で市場・規制・製品情報を追加確認し、判断を再提示する。"

    dominant_cat = _dominant_category(picked_articles)
    claim_templates = CATEGORY_CLAIM_TEMPLATES.get(role, CATEGORY_CLAIM_TEMPLATES["engineer"])
    action_templates = CATEGORY_ACTION_TEMPLATES.get(role, CATEGORY_ACTION_TEMPLATES["engineer"])

    claim_text = claim_templates.get(dominant_cat, claim_templates["_default"])
    action_text = action_templates.get(dominant_cat, action_templates["_default"])

    if role == "engineer":
        article_a = picked_articles[0]
        article_b = picked_articles[1] if len(picked_articles) > 1 else picked_articles[0]
        article_c = picked_articles[2] if len(picked_articles) > 2 else article_b
        point_a = _sanitize_engineer_phrase(_extract_role_perspective(article_a, "engineer"))
        point_b = _sanitize_engineer_phrase(_extract_role_perspective(article_b, "engineer"))
        point_c = _sanitize_engineer_phrase(_extract_role_perspective(article_c, "engineer"))

        axes = CATEGORY_EVIDENCE_AXES.get(dominant_cat, CATEGORY_EVIDENCE_AXES["_default"])

        claim = f"主張: 技術者としては、『{claim_text}』。"
        evidence = (
            f"根拠: {axes[0]}の評価軸では、{point_a}を根拠に優先対応が必要である。"
            f"根拠: {axes[1]}の評価軸では、{point_b}を根拠に先行整備が必須になる。"
            f"根拠: {axes[2]}の評価軸では、{point_c}を根拠に同時設計すべきだ。"
        )
        impact = f"影響: {action_text}"
        text = f"{claim}{evidence}{impact}"
        return _fit_text_length(text, target=330, min_len=260, max_len=420)

    # management / consumer
    evidence_points = []
    for article in picked_articles[:2]:
        source = str(article.get("source") or "出典未記載").strip()
        point = _extract_role_perspective(article, role)
        evidence_points.append(f"{point}（{source}）")
    while len(evidence_points) < 2:
        evidence_points.append("関連一次情報の追加確認が必要（出典精査中）")

    claim = f"主張: {role_label}としては、『{claim_text}』。"
    evidence = f"根拠: {evidence_points[0]}。さらに、{evidence_points[1]}。"
    impact = f"影響: {action_text}"
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
    m = re.search(r"影響:\s*([^。]+。)", opinion or "")
    if m:
        return m.group(1).strip()
    sentences = [s.strip() + "。" for s in re.findall(r"([^。]+)。", opinion or "") if s.strip()]
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
    role_map = {str(section.get("role") or ""): section for section in role_sections}
    role_order = ["engineer", "management", "consumer"]
    role_labels = {
        "engineer": "技術者",
        "management": "経営者",
        "consumer": "消費者",
    }
    default_summary = "判断に直結する情報が不足しているため、仕様の前提条件を整理する。"
    default_reco = "関係者レビューを実施し、リスクと優先順位を更新する。"

    discussions_by_role: dict[str, list[dict[str, str]]] = {}
    for focus_role in role_order:
        focus_summary = str(role_map.get(focus_role, {}).get("summary") or default_summary)
        focus_reco = str(role_map.get(focus_role, {}).get("recommendation") or default_reco)
        focus_discussions: list[dict[str, str]] = []

        for other_role in role_order:
            if other_role == focus_role:
                continue

            other_summary = str(role_map.get(other_role, {}).get("summary") or default_summary)
            other_reco = str(role_map.get(other_role, {}).get("recommendation") or default_reco)

            question_template = DISCUSSION_QUESTION_TEMPLATES.get(
                (focus_role, other_role),
                "仕様の確定タイミングと受け入れ条件を先に合意しないと実行リスクが残りませんか。",
            )
            answer_template = DISCUSSION_ANSWER_TEMPLATES.get(
                (other_role, focus_role),
                f"まずは『{focus_reco}』を小さく試し、運用データで仕様妥当性を確認する進め方が現実的です。",
            )

            focus_discussions.append(
                {
                    "from": role_labels[focus_role],
                    "to": role_labels[other_role],
                    "text": (
                        f"あなたは『{other_reco}』と述べています。"
                        f"{focus_summary}の観点では、{question_template}"
                    ),
                }
            )
            focus_discussions.append(
                {
                    "from": role_labels[other_role],
                    "to": role_labels[focus_role],
                    "text": (
                        f"その懸念は理解します。{other_summary}を踏まえると、"
                        f"{answer_template}"
                    ),
                }
            )

        discussions_by_role[focus_role] = focus_discussions

    return discussions_by_role


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
    opinion_dir = out_dir / "opinion"
    opinion_dir.mkdir(exist_ok=True)
    
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

    opinion_items = []
    for sec in sections_all:
        opinion_items.extend(sec.get("rows", []))

    opinion_items.sort(key=lambda x: (x.get("dt") or "", x.get("importance") or 0), reverse=True)
    opinion_seed_items = opinion_items[:15]

    role_labels = {
        "engineer": "技術者",
        "management": "経営者",
        "consumer": "消費者",
    }
    roles = ["engineer", "management", "consumer"]
    selected_articles = _select_role_articles(opinion_items, roles, max_items=3)

    role_sections = []
    anchor_ids = {
        "engineer": "engineer",
        "management": "executive",
        "consumer": "consumer",
    }
    for role in roles:
        picked = selected_articles.get(role, [])
        full_text = _build_combined_opinion(role, picked)
        summary = _extract_conclusion_line(full_text)
        selection_note = "" if len(picked) >= 3 else "本日は立場条件に合う記事が少ないため、該当ソースのみで構成しています。"
        role_sections.append({
            "role": role,
            "anchor_id": anchor_ids[role],
            "label": role_labels[role],
            "articles": picked,
            "summary": summary,
            "full_text": full_text,
            "full_text_len": len(full_text),
            "full_text_sections": _build_opinion_body_sections(full_text),
            "preview_lines": _build_opinion_preview_lines(full_text),
            "primary_evidence": _build_primary_evidence_line(picked),
            "top_evidence_tags": _build_top_evidence_tags(picked, limit=2),
            "selection_note": selection_note,
            "focus": f"{role_labels[role]}視点: {ROLE_PROFILES.get(role, {}).get('opinion_focus', '重要記事（点）をつないで意見（線）を構成')}" ,
            "recommendation": _extract_recommended_action_line(full_text),
        })

    role_discussions = _build_role_discussion(role_sections)
    for section in role_sections:
        section["discussion_pairs"] = role_discussions.get(section["role"], [])

    opinion_assets = build_asset_paths()
    opinion_html = Template(OPINION_HTML).render(
        common_css_href=opinion_assets["common_css_href"],
        common_js_src=opinion_assets["common_js_src"],
        page="opinion",
        generated_at=generated_at,
        role_sections=role_sections,
        source_item_count=len(opinion_seed_items),
    )
    (opinion_dir / "index.html").write_text(opinion_html, encoding="utf-8")

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
        "blast_furnace",
        "eaf",
        "rolling",
        "quality",
        "maintenance",
        "market",
        "environment",
        "security",
        "ai",
        "dev",
        "other",
    ]
    order_index = {cat_id: idx for idx, cat_id in enumerate(category_order)}
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

    cur.execute(
        """
        SELECT
          COALESCE(NULLIF(source,''), '') AS source,
          COUNT(*) AS total,
          SUM(
            CASE
              WHEN datetime(COALESCE(NULLIF(published_at,''), fetched_at)) >= datetime(?) THEN 1
              ELSE 0
            END
          ) AS recent48,
          GROUP_CONCAT(DISTINCT COALESCE(NULLIF(category,''), 'other')) AS categories
        FROM articles
        WHERE kind='tech'
          AND COALESCE(NULLIF(source,''), '') != ''
        GROUP BY source
        ORDER BY total DESC, recent48 DESC, source ASC
        LIMIT 15
        """,
        (cutoff_48h,),
    )
    source_exposure = []
    for source, total, recent48, categories_str in cur.fetchall():
        cat_ids = [c for c in (categories_str or "").split(",") if c]
        category_labels = [cat_name.get(c, c) for c in cat_ids[:3]]
        source_exposure.append(
            {
                "source": clean_for_html(source),
                "total": int(total or 0),
                "recent48": int(recent48 or 0),
                "categories": " / ".join(category_labels) if category_labels else "-",
            }
        )

    primary_ratio_threshold = float(os.environ.get("PRIMARY_RATIO_THRESHOLD", "0.5") or "0.5")

    cur.execute(
        """
        SELECT
          COALESCE(NULLIF(category,''), 'other') AS category,
          COUNT(*) AS total_count,
          SUM(CASE WHEN COALESCE(NULLIF(source_tier,''), 'secondary') = 'primary' THEN 1 ELSE 0 END) AS primary_count
        FROM articles
        WHERE kind='tech'
        GROUP BY COALESCE(NULLIF(category,''), 'other')
        ORDER BY total_count DESC, category ASC
        """
    )
    primary_ratio_by_category = []
    primary_ratio_min_sample = int(os.environ.get("PRIMARY_RATIO_MIN_SAMPLE", "5") or "5")
    for category, total_count, primary_count in cur.fetchall():
        total_count = int(total_count or 0)
        primary_count = int(primary_count or 0)
        ratio = (primary_count / total_count) if total_count else 0.0
        warn = ratio < primary_ratio_threshold
        warn_reason = ""
        if warn:
            if total_count < primary_ratio_min_sample:
                warn_reason = "サンプル不足"
            else:
                warn_reason = "一次ソース追加候補"
        primary_ratio_by_category.append(
            {
                "category": category,
                "total_count": total_count,
                "primary_count": primary_count,
                "ratio_pct": round(ratio * 100, 1),
                "warn": warn,
                "warn_reason": warn_reason,
            }
        )

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

    (tech_dir / "index.html").write_text(tech_html_sub, encoding="utf-8")
    (out_dir / "index.html").write_text(tech_html_root, encoding="utf-8")

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
        source_exposure=source_exposure,
        primary_ratio_by_category=primary_ratio_by_category,
        primary_ratio_threshold=primary_ratio_threshold,
    )
    (ops_dir / "index.html").write_text(ops_html, encoding="utf-8")

    render_news_pages(out_dir, generated_at, cur)

    conn.close()
    print(f"[TIME] step=render end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
