# src/render.py
from __future__ import annotations
import os

import json
from pathlib import Path
from typing import Any, Dict, List

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

      <div id="tagBar" class="tag-bar collapsed" style="margin-top:6px">
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
    <div class="quick-controls">
      <input id="q" type="search" placeholder="タイトル・要約を検索" />
      <button class="btn" type="button" data-toggle-all-cats onclick="toggleAllCats()">すべて閉じる</button>
      <label class="small">並び替え
        <select id="sortKey">
          <option value="date">日付</option>
          <option value="importance">重要度</option>
        </select>
      </label>

      <label class="small">順序
        <select id="sortDir">
          <option value="desc">降順</option>
          <option value="asc">昇順</option>
        </select>
      </label>

      <button class="btn" type="button" onclick="applySort()">適用</button>

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

  <details class="foldable-section top-zone-fold" data-top-zone-details>
    <summary>🏭 Source露出（競合比較）</summary>
    <section class="top-col" style="margin:8px 0 16px;">
    <div class="metric-note">
      <div>この指標で分かること: どの企業ソースに記事露出が偏っているか、直近48hで増勢のある企業はどこかを把握できます。</div>
      <div>閾値を下回った時の対応: 露出が特定企業に集中する場合は、他の一次情報源（公式ブログ・開発者向け発表）を優先追加してください。</div>
    </div>
    <div class="small" style="margin-bottom:8px">同一企業名で集計（全期間 / 48h）</div>
    {% if source_exposure and source_exposure|length > 0 %}
      <table class="source-table">
        <thead>
          <tr>
            <th>企業</th>
            <th class="num">露出</th>
            <th class="num">48h</th>
            <th>主カテゴリ</th>
          </tr>
        </thead>
        <tbody>
          {% for s in source_exposure %}
            <tr>
              <td>{{ s.source }}</td>
              <td class="num">{{ s.total }}</td>
              <td class="num">{{ s.recent48 }}</td>
              <td>{{ s.categories }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="meta">該当ソースなし</div>
    {% endif %}
    </section>
  </details>

  <details class="foldable-section top-zone-fold" data-top-zone-details>
    <summary>🧭 カテゴリ別 一次情報比率</summary>
    <section class="top-col" style="margin:8px 0 16px;">
    <div class="metric-note">
      <div>この指標で分かること: カテゴリごとに一次情報（公式発表・一次資料）がどれだけ確保できているかを確認できます。</div>
      <div>閾値を下回った時の対応: 警告理由を見て「一次ソース追加候補」か「サンプル不足」かを切り分け、収集対象を補強してください。</div>
    </div>
    <div class="small" style="margin-bottom:8px">一次情報率 = primary / 全記事（tech）。閾値 {{ (primary_ratio_threshold * 100)|round(0)|int }}% 未満は警告表示。</div>
    {% if primary_ratio_by_category and primary_ratio_by_category|length > 0 %}
      <table class="source-table">
        <thead>
          <tr>
            <th>カテゴリ</th>
            <th class="num">一次情報率</th>
            <th class="num">primary</th>
            <th class="num">total</th>
            <th>ステータス</th>
          </tr>
        </thead>
        <tbody>
          {% for r in primary_ratio_by_category %}
            <tr>
              <td>{{ cat_name.get(r.category, r.category) }}</td>
              <td class="num">{{ r.ratio_pct }}%</td>
              <td class="num">{{ r.primary_count }}</td>
              <td class="num">{{ r.total_count }}</td>
              <td>
                {% if r.warn %}
                  <span class="warn-text">⚠ 閾値未達（{{ r.warn_reason }}）</span>
                {% else %}
                  OK
                {% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="meta">カテゴリ集計対象なし</div>
    {% endif %}
    </section>
  </details>

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
  <section class="category-section" id="cat-{{ cat.id }}">
    <div class="category-header">
      <h2 style="margin:0">{{ cat.name }} <span class="tag">{{ cat.id }}</span></h2>
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

            {% if t.summary or (t.key_points and t.key_points|length>0) or (t.perspectives) or (t.evidence_urls and t.evidence_urls|length>0) %}
              <details class="insight">
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
                  <div class="small" style="margin-top:6px;">
                    根拠：
                    {% for u in t.evidence_urls %}
                      <a href="{{ u }}" target="_blank" rel="noopener">{{ u }}</a>{% if not loop.last %}, {% endif %}
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
      <div id="tagBar" class="tag-bar collapsed" style="margin-top:6px">
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
      <input id="q" type="search" placeholder="タイトル・要約を検索" />
      <button class="btn" type="button" data-toggle-all-cats onclick="toggleAllCats()">すべて閉じる</button>
      <label class="small">並び替え
        <select id="sortKey">
          <option value="date">日付</option>
          <option value="importance">重要度</option>
        </select>
      </label>

      <label class="small">順序
        <select id="sortDir">
          <option value="desc">降順</option>
          <option value="asc">昇順</option>
        </select>
      </label>

      <button class="btn" type="button" onclick="applySort()">適用</button>

    </div>
    <div id="filter-count" class="small" style="margin-top:6px; display:none;"></div>
    <div id="filter-hint" class="small" style="margin-top:4px; display:none;"></div>
  </div>

  <!-- techと同じ：Top-zone 2カラム -->
  <section class="top-zone">
    <div class="top-col">
      <h3>🇯🇵 Japan Top 10（importance / date）</h3>
      <ol class="top-list">
        {% for it in jp_top %}
          <li class="topic-row"
              data-title="{{ it.title|e }}"
              data-summary="{{ (it.summary or '')|e }}"
              data-imp="{{ it.importance or 0 }}"
              data-date="{{ it.dt }}"
              data-tags="{{ it.tags|default([])|join(',') }}">
            <span class="badge imp">重要度 {{ it.importance or 0 }}</span>
            {% if it.is_representative %}<span class="badge">代表記事</span>{% endif %}            
            <a class="topic-link" href="#news-{{ it.id }}">{{ it.title }}</a>
            <a class="small" href="{{ it.url }}" target="_blank" rel="noopener">開く</a>
            <span class="date">{{ it.dt_jst }}</span>
            <details class="insight">
              <summary class="small">要約・解説を表示</summary>
              {% if it.summary %}<div><strong>要約</strong>：{{ it.summary }}</div>{% endif %}
              <div class="small" style="margin-top:6px;"><strong>算出根拠（簡易）</strong>：{{ it.importance_basis }}</div>
            </details>

            {% if it.tags and it.tags|length>0 %}
              <span class="small">
                {% for tg in it.tags %}
                  <span class="badge">{{ tg }}</span>
                {% endfor %}
              </span>
            {% endif %}

            {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}
          </li>
        {% endfor %}
      </ol>
    </div>

    <div class="top-col">
      <h3>🌍 Global Top 10（importance / date）</h3>
      <ol class="top-list">
        {% for it in global_top %}
          <li class="topic-row"
              data-title="{{ it.title|e }}"
              data-summary="{{ (it.summary or '')|e }}"
              data-imp="{{ it.importance or 0 }}"
              data-date="{{ it.dt }}"
              data-tags="{{ it.tags|default([])|join(',') }}">
            <span class="badge imp">重要度 {{ it.importance or 0 }}</span>
            {% if it.is_representative %}<span class="badge">代表記事</span>{% endif %}           
            <a class="topic-link" href="#news-{{ it.id }}">{{ it.title }}</a>
            <a class="small" href="{{ it.url }}" target="_blank" rel="noopener">開く</a>
            <span class="date">{{ it.dt_jst }}</span>
            <details class="insight">
              <summary class="small">要約・解説を表示</summary>
              {% if it.summary %}<div><strong>要約</strong>：{{ it.summary }}</div>{% endif %}
              <div class="small" style="margin-top:6px;"><strong>算出根拠（簡易）</strong>：{{ it.importance_basis }}</div>
            </details>

            {% if it.tags and it.tags|length>0 %}
              <span class="small">
                {% for tg in it.tags %}
                  <span class="badge">{{ tg }}</span>
                {% endfor %}
              </span>
            {% endif %}

            {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}
          </li>
        {% endfor %}
      </ol>
    </div>
  </section>

  <!-- techと同じ：カテゴリ（折りたたみ） -->
 {% for sec in sections %}
  <section class="category-section" id="cat-{{ sec.anchor }}">
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

          {% if it.source %}<div class="mini">{{ it.source }}</div>{% endif %}

           {% if it.importance_basis or it.summary or (it.key_points and it.key_points|length>0) or (it.perspectives and (it.perspectives.engineer or it.perspectives.management or it.perspectives.consumer)) %}
              <details class="insight">
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
                  <div class="small" style="margin-top:6px;">
                    根拠：
                    {% for u in it.evidence_urls %}
                      <a href="{{ u }}" target="_blank" rel="noopener">{{ u }}</a>{% if not loop.last %}, {% endif %}
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
                      <details class="insight">
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

    # --- techと同じ構成にするためのnews用データ ---
    # Top（最新）
    jp_top = fetch_news_articles(cur, "jp", NEWS_REGION_TOP_LIMIT.get("jp", 10))
    gl_top = fetch_news_articles(cur, "global", NEWS_REGION_TOP_LIMIT.get("global", 10))

    def to_top_items(rows, region_label):
      out = []
      for r in rows:
          # fetch_news_articles(region指定) の戻り:
          # title,url,source,category,dt,importance,tags,summary
          article_id, title, url, source, category, dt, importance, tags, summary = r

          imp = int(importance) if importance is not None else 0

          llm_tags = _safe_json_list(tags)
          if not llm_tags:
              llm_tags = [region_label, (category or "other")]
              if source:
                  llm_tags.append(source)

          out.append({
              "id": int(article_id),
              "title": clean_for_html(title),
              "url": clean_for_html(url),
              "source": clean_for_html(source),
              "category": clean_for_html(category or "other"),
              "region": region_label,
              "dt": clean_for_html(dt),
              "dt_jst": fmt_date(dt),
              "tags": llm_tags,
              "recent": 0,
              "importance": imp,
              "summary": clean_for_html((summary or "").strip() or f"{source} / {fmt_date(dt)}"),
              "importance_basis": _news_importance_basis_simple(imp, dt, category, llm_tags),
          })
      return out


    jp_top_items = to_top_items(jp_top, "jp")
    gl_top_items = to_top_items(gl_top, "global")

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
                jp_top=jp_top_items,
                global_top=gl_top_items,

                sections=sections,
            ),

            encoding="utf-8",
        )

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

NEWS_REGION_TOP_LIMIT = {
    "jp": 10,
    "global": 6,
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
            # （旧実装: 14列, 現実装: 13列）
            if len(r) == 14:
                (
                    article_id, title, url, source, category, dt,
                    importance, typ, summary, key_points, perspectives, tags, evidence_urls,
                    is_representative,
                ) = r
            else:
                (
                    article_id, title, url, source, category, dt,
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

    LIMIT_PER_CAT = 20
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
            tid, title, url, article_date, recent, importance, summary, key_points, evidence_urls, tags, perspectives = r
            items.append(
                {
                    "id": tid,
                    "title": clean_for_html(title),  # ← ここはSQLで title_ja 優先済み
                    "url": url or "#",
                    "date": article_date,
                    "recent": int(recent or 0),
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
                tid, title, url, article_date, recent, importance, summary, key_points, evidence_urls, tags, perspectives = r
                items.append(
                    {
                        "id": tid,
                        "title": clean_for_html(title),
                        "url": url or "#",
                        "date": article_date,
                        "recent": int(recent or 0),
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


        topics_by_cat[cat_id] = items

    all_tags = {}
    for cat_id, items in topics_by_cat.items():
        for t in items:
            for tg in (t.get("tags") or []):
                all_tags[tg] = all_tags.get(tg, 0) + 1
    tag_list = sorted(all_tags.items(), key=lambda x: (-x[1], x[0]))[:50]  # 上位50など
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
        source_exposure=source_exposure,
        primary_ratio_by_category=primary_ratio_by_category,
        primary_ratio_threshold=primary_ratio_threshold,
        fmt_date=fmt_date,
    )

    (tech_dir / "index.html").write_text(tech_html_sub, encoding="utf-8")
    (out_dir / "index.html").write_text(tech_html_root, encoding="utf-8")

    render_news_pages(out_dir, generated_at, cur)

    conn.close()
    print(f"[TIME] step=render end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
