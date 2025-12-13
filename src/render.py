from pathlib import Path
from jinja2 import Template
import yaml
from db import connect

HTML = """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Tech Trend</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;line-height:1.5}
    h1{margin:0 0 12px}
    h2{margin:28px 0 8px;border-bottom:1px solid #eee;padding-bottom:6px}
    .meta{color:#666;font-size:12px;margin-bottom:18px}
    ul{margin:0;padding-left:18px}
    li{margin:6px 0}
    .tag{display:inline-block;border:1px solid #ddd;border-radius:999px;padding:2px 8px;font-size:12px;color:#444;margin-left:8px}
  </style>
</head>
<body>
  <h1>Daily Tech Trend</h1>
  <div class="meta">カテゴリ別（最新テーマ）</div>

  {% for cat in categories %}
    <h2>{{ cat.name }} <span class="tag">{{ cat.id }}</span></h2>
    {% if topics_by_cat.get(cat.id) %}
      <ul>
        {% for t in topics_by_cat[cat.id] %}
          <li>{{ t }}</li>
        {% endfor %}
      </ul>
    {% else %}
      <div class="meta">該当なし</div>
    {% endif %}
  {% endfor %}
</body>
</html>
"""

def load_categories():
    with open("src/sources.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # categories: [{id,name}, ...]
    return cfg.get("categories", [])

def main():
    conn = connect()
    cur = conn.cursor()

    categories = load_categories()
    topics_by_cat = {}

    # カテゴリごとに最新N件
    LIMIT_PER_CAT = 20

    for cat in categories:
        cat_id = cat["id"]
        cur.execute(
            """
            SELECT COALESCE(title_ja, title)
            FROM topics
            WHERE category = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (cat_id, LIMIT_PER_CAT)
        )
        topics_by_cat[cat_id] = [r[0] for r in cur.fetchall()]

    conn.close()

    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(
        Template(HTML).render(categories=categories, topics_by_cat=topics_by_cat),
        encoding="utf-8"
    )

if __name__ == "__main__":
    main()
