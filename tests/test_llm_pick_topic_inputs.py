import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_insights_pipeline import pick_topic_inputs


def _setup_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        create table topics (
          id integer primary key,
          title text,
          title_ja text,
          category text,
          score_48h integer
        )
        """
    )
    cur.execute(
        """
        create table articles (
          id integer primary key,
          kind text,
          source text,
          title text,
          title_ja text,
          url text,
          content text,
          category text,
          region text default '',
          published_at text,
          fetched_at text
        )
        """
    )
    cur.execute("create table topic_articles (topic_id integer, article_id integer)")
    cur.execute(
        """
        create table topic_insights (
          topic_id integer primary key,
          importance integer,
          summary text,
          src_hash text
        )
        """
    )
    return conn


def _insert_article(cur, aid, kind, region, pub_ts):
    """簡易ヘルパー：ニュース記事を1件挿入"""
    cur.execute(
        "insert into articles "
        "values (?, ?, 'SrcX', 'en title', 'JA title', ?, 'body', 'news', ?, ?, ?)",
        (aid, kind, f"https://x/{aid}", region, pub_ts, pub_ts),
    )


def _insert_topic(cur, tid):
    cur.execute("insert into topics values (?, 'tt', 'タイトル', 'news', 0)", (tid,))


def test_pick_topic_inputs_rescue_reingests_news_even_if_already_processed():
    conn = _setup_db()
    cur = conn.cursor()

    cur.execute("insert into topics values (1, 't1', 'ニュース1', 'news', 3)")
    cur.execute(
        "insert into articles "
        "values (10, 'news', 'Reuters', 'title', 'タイトル', 'https://example.com/n', '本文', 'news', '', '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')"
    )
    cur.execute("insert into topic_articles values (1, 10)")
    cur.execute("insert into topic_insights values (1, 50, 'ok', 'hash-ok')")
    conn.commit()

    normal_rows = pick_topic_inputs(conn, rescue=False)
    rescue_rows = pick_topic_inputs(conn, rescue=True)

    assert len(normal_rows) == 0
    assert len(rescue_rows) == 1
    assert rescue_rows[0]["topic_id"] == 1


def test_pick_topic_inputs_rescue_does_not_reingest_completed_tech_by_default():
    conn = _setup_db()
    cur = conn.cursor()

    cur.execute("insert into topics values (2, 't2', '技術2', 'security', 4)")
    cur.execute(
        "insert into articles "
        "values (20, 'tech', 'TechCrunch', 'tech title', '技術タイトル', 'https://example.com/t', '本文', 'security', '', '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')"
    )
    cur.execute("insert into topic_articles values (2, 20)")
    cur.execute("insert into topic_insights values (2, 60, 'ok', 'hash-ok')")
    conn.commit()

    rescue_rows = pick_topic_inputs(conn, rescue=True)

    assert len(rescue_rows) == 0


def test_pick_topic_inputs_round_robin_across_region_kind_buckets():
    """jp/news が大量にあっても global/news が後回しにならないことを確認。

    旧実装（published_at DESC 単純順）では limit=20 のとき、
    jp の新しい記事が最新順で優先され、global/news は0件になる可能性があった。
    新実装はバケット横断でラウンドロビンするため、各バケット最新が先頭に並ぶ。
    """
    conn = _setup_db()
    cur = conn.cursor()

    # jp/news 100件（2026-04-24 の最新側）を作る
    for i in range(100):
        tid = 1000 + i
        aid = 10000 + i
        _insert_topic(cur, tid)
        # 04-24 02:00 台に集中配置（globalより新しい）
        pub_ts = f"2026-04-24T02:{i%60:02d}:00+00:00"
        _insert_article(cur, aid, "news", "jp", pub_ts)
        cur.execute("insert into topic_articles values (?, ?)", (tid, aid))

    # global/news を10件（04-24 00:00 台＝jpより古い）
    for i in range(10):
        tid = 2000 + i
        aid = 20000 + i
        _insert_topic(cur, tid)
        pub_ts = f"2026-04-24T00:{i:02d}:00+00:00"
        _insert_article(cur, aid, "news", "global", pub_ts)
        cur.execute("insert into topic_articles values (?, ?)", (tid, aid))

    conn.commit()

    # limit=20 で呼ぶ。ラウンドロビンなので先頭2件は (jp_news 最新, global_news 最新)
    rows = pick_topic_inputs(conn, limit=20)
    topic_ids = [r["topic_id"] for r in rows]

    # 旧実装では先頭20件すべて jp/news になっていた
    jp_topic_ids = {1000 + i for i in range(100)}
    global_topic_ids = {2000 + i for i in range(10)}

    jp_picked = sum(1 for tid in topic_ids if tid in jp_topic_ids)
    global_picked = sum(1 for tid in topic_ids if tid in global_topic_ids)

    # どちらのバケットからも複数件拾われることが本質
    assert global_picked >= 5, (
        f"global/news が十分に拾われていない: global={global_picked} jp={jp_picked}"
    )
    assert jp_picked >= 5, (
        f"jp/news も最低限は拾われる必要あり: global={global_picked} jp={jp_picked}"
    )


def test_pick_topic_inputs_still_orders_newest_first_within_bucket():
    """同一バケット内は新しい順で拾われることを確認。"""
    conn = _setup_db()
    cur = conn.cursor()

    # global/news 3件を時系列で作成（新しい→古い順に 2003, 2002, 2001）
    for i, pub in enumerate(
        ["2026-04-24T03:00:00+00:00",
         "2026-04-24T02:00:00+00:00",
         "2026-04-24T01:00:00+00:00"]
    ):
        tid = 2001 + i
        aid = 20001 + i
        _insert_topic(cur, tid)
        _insert_article(cur, aid, "news", "global", pub)
        cur.execute("insert into topic_articles values (?, ?)", (tid, aid))

    conn.commit()
    rows = pick_topic_inputs(conn, limit=10)
    ids = [r["topic_id"] for r in rows]
    # 新しい順
    assert ids == [2001, 2002, 2003]
