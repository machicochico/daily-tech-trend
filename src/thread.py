import re
from datetime import datetime, timezone
from rapidfuzz import fuzz
from db import connect

# ★ 閾値を少し下げる（集まりやすくする）
TOPIC_SIM = 82

# 比較対象を増やしすぎないため、各カテゴリで直近の topic をこの件数だけ比較
CANDIDATE_TOPICS_PER_CAT = 400

NOISE_PATTERNS = [
    r"\bupdate\b", r"\breleased?\b", r"\bannounce[sd]?\b", r"\bintroducing\b",
    r"\bpreview\b", r"\bga\b", r"\bgeneral availability\b",
    r"\bv\d+(\.\d+)*\b", r"\bver\.?\s*\d+(\.\d+)*\b",
    r"\bcve-\d{4}-\d+\b",  # CVEはテーマに寄与するが、同テーマがバラける原因にもなるので一旦ノイズ扱い（後で改善可）
]

def normalize_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"\[[^\]]+\]|\([^)]+\)", " ", t)  # []や()の補足を落とす
    for p in NOISE_PATTERNS:
        t = re.sub(p, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff\s\-_/]", " ", t)  # 日本語も残す
    t = re.sub(r"\s+", " ", t).strip()
    return t

def make_topic_key(norm_title: str) -> str:
    # 先頭だけキーにして、表記揺れに強くする
    return norm_title[:120]

def load_topic_candidates(cur):
    """
    各カテゴリの直近トピック候補を読み込む
    {cat: [(topic_id, topic_title_norm, topic_title_raw), ...]}
    """
    cur.execute("""
        SELECT id, title, category
        FROM topics
        ORDER BY id DESC
    """)
    by_cat = {}
    for tid, ttitle, cat in cur.fetchall():
        if cat is None:
            continue
        if len(by_cat.get(cat, [])) >= CANDIDATE_TOPICS_PER_CAT:
            continue
        by_cat.setdefault(cat, []).append((tid, normalize_title(ttitle or ""), ttitle or ""))
    return by_cat

def find_best_topic(norm_title: str, cat: str, candidates_by_cat):
    best_tid = None
    best_score = -1
    for tid, tnorm, _traw in candidates_by_cat.get(cat, []):
        score = fuzz.token_set_ratio(norm_title, tnorm)
        if score > best_score:
            best_score = score
            best_tid = tid
    if best_score >= TOPIC_SIM:
        return best_tid, best_score
    return None, best_score

def main():
    conn = connect()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # まず既存 topics を候補として読む
    candidates_by_cat = load_topic_candidates(cur)

    # 直近の articles を処理（必要なら件数増やしてOK）
    cur.execute("""
        SELECT id, title, category
        FROM articles
        ORDER BY id DESC
        LIMIT 2000
    """)
    articles = cur.fetchall()

    for aid, title, cat in articles:
        if not title or not cat:
            continue

        # すでに topic に紐付いてたらスキップ
        cur.execute("SELECT 1 FROM topic_articles WHERE article_id=? LIMIT 1", (aid,))
        if cur.fetchone():
            continue

        norm = normalize_title(title)
        if not norm:
            continue

        tid, score = find_best_topic(norm, cat, candidates_by_cat)

        if tid is None:
            # 新規 topic
            key = make_topic_key(norm)
            # topic_key が衝突しても title は更新せず、既存を使う
            cur.execute("""
                INSERT OR IGNORE INTO topics(topic_key, title, category, created_at)
                VALUES(?,?,?,?)
            """, (key, title[:200], cat, now))
            conn.commit()

            cur.execute("SELECT id, title FROM topics WHERE topic_key=?", (key,))
            row = cur.fetchone()
            if row:
                tid = row[0]
                # 候補にも追加して、以降の記事が同topicに寄るようにする
                candidates_by_cat.setdefault(cat, []).insert(0, (tid, normalize_title(row[1] or ""), row[1] or ""))

        # 紐付け
        cur.execute("INSERT OR IGNORE INTO topic_articles(topic_id, article_id) VALUES(?,?)", (tid, aid))

    # ツリー（topic内をpublished_at→idで並べ、前→後を親子）
    cur.execute("""
        SELECT ta.topic_id, a.id, COALESCE(a.published_at,''), a.title
        FROM topic_articles ta
        JOIN articles a ON a.id=ta.article_id
        ORDER BY ta.topic_id, COALESCE(a.published_at,''), a.id
    """)
    rows = cur.fetchall()

    by_topic = {}
    for tid, aid, pub, t in rows:
        by_topic.setdefault(tid, []).append((pub, aid))

    for tid, items in by_topic.items():
        cur.execute("DELETE FROM edges WHERE topic_id=?", (tid,))
        for i in range(1, len(items)):
            parent = items[i-1][1]
            child = items[i][1]
            cur.execute("""
                INSERT OR IGNORE INTO edges(topic_id, parent_article_id, child_article_id)
                VALUES(?,?,?)
            """, (tid, parent, child))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
