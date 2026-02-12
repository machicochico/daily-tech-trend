import json
import hashlib
import sqlite3
import sys
import time
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

LMSTUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"  # 必要なら変更
MODEL = "openai/gpt-oss-20b"  # LM Studio側で指定不要なら任意文字列でOK

def _looks_english(s: str) -> bool:
    # 英字が多いなら英語寄りと判定（雑でOK）
    letters = sum(c.isascii() and c.isalpha() for c in s)
    return letters >= 20

def _has_japanese(s: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龥]", s or ""))

def _get_lm_content(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"LMStudio returned non-JSON: {resp.text[:500]}") from e

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise RuntimeError(f"LMStudio unexpected schema: {str(data)[:500]}") from e

_SESSION = requests.Session()

def post_lmstudio(payload: dict, timeout: int, retries: int = 2, backoff_sec: float = 0.8):
    last_err = None
    for i in range(retries + 1):
        try:
            r = _SESSION.post(LMSTUDIO_URL, json=payload, timeout=timeout)
            if r.status_code >= 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text
                raise RuntimeError(f"LMStudio HTTP {r.status_code}: {detail}")
            return r
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(backoff_sec * (i + 1))
                continue
            raise

def _now_sec():
    return time.perf_counter()

from pathlib import Path

def connect():
    base = Path(__file__).resolve().parent.parent
    return sqlite3.connect(base / "data" / "state.sqlite")


def _now():
    return datetime.now(timezone.utc).isoformat()

def pick_topic_inputs(conn, limit=300, rescue=False):
    """
    要件:
      - 未要約のtopicに対して、代表article（最新）を1つ選び、LLM入力を作る
      - rescue=True のときは重要度0/要約空/ハッシュ不整合も拾う
      - tech/news の両方を処理対象にする
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    WITH latest AS (
      SELECT
        ta.topic_id,
        a.id AS article_id,
        a.kind AS kind,
        a.source,
        a.title,
        a.title_ja,
        a.url,
        a.content,
        a.category AS article_category,
        a.published_at,
        a.fetched_at,
        ROW_NUMBER() OVER (
          PARTITION BY ta.topic_id
          ORDER BY
            COALESCE(a.published_at, a.fetched_at) DESC,
            a.id DESC
        ) AS rn
      FROM topic_articles ta
      JOIN articles a ON a.id = ta.article_id
      WHERE a.kind IN ('tech','news')
    )
    SELECT
      t.id AS topic_id,

      -- 表示/入力用タイトル（topics優先→article）
      CASE
        WHEN COALESCE(NULLIF(t.category,''),'') = 'news'
            THEN COALESCE(NULLIF(l.title_ja,''), NULLIF(l.title,''), NULLIF(t.title_ja,''), NULLIF(t.title,''))
        ELSE COALESCE(NULLIF(t.title_ja,''), NULLIF(t.title,''), NULLIF(l.title_ja,''), NULLIF(l.title,''))
        END AS topic_title,

      -- ★カテゴリ判定：newsトピックは topics.category を優先（render.py と整合）
      CASE
        WHEN COALESCE(NULLIF(t.category,''),'') = 'news' THEN 'news'
        ELSE COALESCE(NULLIF(l.article_category,''), NULLIF(t.category,''), 'other')
      END AS category,

      l.kind AS kind,
      l.source AS source,
      l.url AS url,
      l.published_at AS published_at,
      t.score_48h AS importance_hint,

      COALESCE(NULLIF(l.content,''), NULLIF(l.title_ja,''), NULLIF(l.title,''), '') AS body,

      l.article_id AS src_article_id,
      ti.src_hash AS prev_src_hash,
      ti.importance AS prev_importance,
      ti.summary AS prev_summary
    FROM topics t
    JOIN latest l ON l.topic_id = t.id AND l.rn = 1
    LEFT JOIN topic_insights ti ON ti.topic_id = t.id
    WHERE
      (
        ti.topic_id IS NULL
        OR (? = 1 AND (
              COALESCE(ti.importance, 0) = 0
           OR COALESCE(ti.summary, '') = ''
           OR COALESCE(ti.src_hash, '') = ''
        ))
      )
    ORDER BY COALESCE(l.published_at, l.fetched_at) DESC
    LIMIT ?
    """, (1 if rescue else 0, limit))

    return cur.fetchall()

def _extract_json_object(text: str) -> str | None:
    if not text:
        return None
    # code fence除去
    t = text.strip().replace("```json", "").replace("```", "").strip()

    # 最初の { と最後の } を使う（雑でも復旧率優先）
    s = t.find("{")
    e = t.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    return t[s:e+1]

def call_llm_short_news(title: str, body: str, url: str = "") -> dict:
    """
    NEWS用:
      - summary は事実のみ（短く）
      - key_points は最大3つ。事実が足りない場合は「推測:」で補う（推測を明示）
      - perspectives は engineer/management/consumer を返す（短い本文でも推測で埋める）
    """
    import json

    system = (
        "あなたはニュース記事の要約アシスタント。出力はJSONのみ。"
        "summary は本文/タイトルに明記された事実のみで日本語1文（推測は禁止）。"
        "key_points は配列で最大3つ。事実が足りない場合、残りは必ず '推測: ' で始めて補完する（断定しない）。"
        "perspectives は {engineer,management,consumer} の3キー。短い本文でも必ず埋める。"
        "perspectives は原則 '推測: ' で始める（本文に明記された事実だけで言える場合のみ推測不要）。"
        "同じ内容の繰り返しは禁止。抽象的すぎる文（例:『詳細は本文確認が必要』だけ）は禁止。"
    )

    body = (body or "").strip()
    title = (title or "").strip()

    # LLMへ渡す本文は短めに（NEWSは短文が多いので過剰に切らない）
    body_for_llm = body[:1200]

    user = (
        f"タイトル: {title}\n"
        f"URL: {url}\n"
        f"本文:\n{body_for_llm}\n\n"
        "次のJSONを出力:\n"
        "{\n"
        '  "summary": "事実のみの日本語1文（推測禁止）",\n'
        '  "key_points": ["箇条書き1","箇条書き2","箇条書き3"],\n'
        '  "perspectives": {\n'
        '    "engineer": "技術/セキュリティ/運用の観点（必要なら推測: で）",\n'
        '    "management": "経営/法務/レピュテーションの観点（必要なら推測: で）",\n'
        '    "consumer": "利用者/生活者の観点（必要なら推測: で）"\n'
        "  },\n"
        '  "inferred": 0\n'
        "}\n"
        "inferred は、key_points または perspectives に '推測:' が1つでも含まれる場合 1、それ以外は0。"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
    }

    r = post_lmstudio(payload, timeout=60)
    s = _get_lm_content(r)

    if not s:
        # 形式をさらに強制
        payload["messages"][1]["content"] = (
            f"タイトル: {title}\nURL: {url}\n本文:\n{body_for_llm}\n\n"
            "JSONのみで返して:\n"
            "{\n"
            '  "summary": "事実のみの日本語1文",\n'
            '  "key_points": ["推測: ..."],\n'
            '  "perspectives": {"engineer":"推測: ...","management":"推測: ...","consumer":"推測: ..."},\n'
            '  "inferred": 1\n'
            "}"
        )
        r = post_lmstudio(payload, timeout=60)
        s = _get_lm_content(r)

    candidate = _extract_json_object(s)

    summary = ""
    key_points = []
    perspectives = {"engineer": "", "management": "", "consumer": ""}
    inferred = 0

    if candidate:
        try:
            obj = json.loads(candidate)
            summary = (obj.get("summary") or "").strip()
            key_points = obj.get("key_points") or []
            p = obj.get("perspectives") or {}
            perspectives = {
                "engineer": (p.get("engineer") or "").strip(),
                "management": (p.get("management") or "").strip(),
                "consumer": (p.get("consumer") or "").strip(),
            }
            inferred = 1 if int(obj.get("inferred") or 0) == 1 else 0
        except Exception:
            summary = ""
            key_points = []
            perspectives = {"engineer": "", "management": "", "consumer": ""}
            inferred = 0

    # フォールバック（最低限）
    if not summary:
        summary = title

    # key_points 正規化（最大3）
    kps = []
    for x in (key_points or []):
        if isinstance(x, str):
            t = x.strip()
            if t:
                kps.append(t)
    kps = kps[:3]

    if not kps:
        kps = ["推測: 本文情報が少ないため、影響範囲はリンク先で要確認"]

    # perspectives の空埋め（抽象だけ禁止 → 最低限でも観点を入れる）
    def _fill_if_empty(v: str, fallback: str) -> str:
        v = (v or "").strip()
        if not v:
            return fallback
        return v

    perspectives["engineer"] = _fill_if_empty(
        perspectives.get("engineer"),
        "推測: 技術面では、影響範囲（対象サービス/システム）と再発防止策の有無が要確認"
    )
    perspectives["management"] = _fill_if_empty(
        perspectives.get("management"),
        "推測: 経営面では、信用/コンプライアンス/説明責任への影響が要確認"
    )
    perspectives["consumer"] = _fill_if_empty(
        perspectives.get("consumer"),
        "推測: 利用者目線では、生活への影響や取るべき行動（注意喚起等）の有無が要確認"
    )

    # inferred 自動補正（推測が含まれていれば1）
    if inferred == 0:
        joined = " ".join(kps) + " " + " ".join(perspectives.values())
        if "推測:" in joined:
            inferred = 1

    return {
        "importance": 10,                 # ★NEWSは固定下限（必要なら後段でhint等により上書き）
        "type": "other",                  # ★NEWS側の分類を増やすならここを拡張
        "summary": summary,
        "key_points": kps,
        "perspectives": perspectives,
        "tags": ["ニュース"],             # ★最低1つ保証（render側で使うなら増やす）
        "evidence_urls": [url] if url else [],
        "inferred": inferred,
    }

def call_llm(topic_title, category, url, body, kind: str | None = None):
    # ★newsは topics.category='news' または articles.kind='news' のどちらでも判定
    is_news = (category == "news") or ((kind or "").lower() == "news")

    if is_news:
        return call_llm_short_news(topic_title, body, url=url)
    
    # 入力を短く（コスト0でも速度のため）
    body = (body or "").strip()
    body = body[:1200]
    
    system = (
      "あなたは技術判断を行うエンジニア/企画担当向けのトレンド分析アシスタント。"
      "一般向け説明、感想、前置き、結論以外の余談は禁止。"
      "出力はJSONのみ。JSON以外の文字（挨拶、説明、コードブロック、注釈）を一切出さない。"
      "必ず全フィールドを出力し、欠落や型違いは禁止。"
      "key_pointsは入力textに明記された事実のみ。推測・解釈・一般論は禁止。"
      "evidence_urlsは必ず1つ以上で、入力のevidence_urlを必ず含める。"
      "tagsは1〜5個の配列。短い名詞。重複禁止。本文/要約から抽出。足りない場合は推測で補ってよい。"
      "必須キー: importance(int), type(string), summary(string), key_points(array[3]), perspectives(object), tags(array[1..5]), evidence_urls(array[>=1])。"
      "perspectivesの各コメントは推論可。"
      "perspectivesは engineer/management/consumer の3キー固定。"
    )
    user = {    
        "topic_title": topic_title,
        "category": category,
        "evidence_url": url,
        "text": body
    }
    
    schema = {
    "importance": (
        "0-100の整数。以下の基準で評価する。\n"
        "0-30: 周辺情報・補足的ニュース（今すぐの実務影響は小さい）\n"
        "31-60: 実務影響あり（設計・実装・運用に影響する可能性）\n"
        "61-80: 業界影響（技術トレンドや標準、競争環境に影響）\n"
        "81-100: パラダイム変化（前提や常識を変える可能性が高い）\n"
        "評価では必ず次を考慮する：\n"
        "- 既存システムの修正・検証が必要か\n"
        "- 6ヶ月以内に対応判断が必要か\n"
        "- 特定ベンダー依存か／業界全体か"
    ),
    "type": "security|release|research|incident|biz|other",
    "summary": "日本語100字以内の要約1行（結論→理由の順）",
    "key_points": [
      "本文に明記された事実1（15〜40字、推測禁止）",
      "本文に明記された事実2（15〜40字、推測禁止）",
      "本文に明記された事実3（15〜40字、推測禁止）"
    ],
    "perspectives": {
      "engineer": "技術者目線のコメント（50字以内）",
      "management": "経営者目線のコメント（50字以内）",
      "consumer": "消費者目線のコメント（50字以内）"
    },

    "tags": [
      "1〜5個。短い名詞。本文/要約から抽出。足りない場合は推測で補ってよい（例: EU規制, 脆弱性, 鉄鋼, 脱炭素, 生成AI）"
    ],
    "evidence_urls": ["根拠URL（最低1つ）"]
    }

    if is_news:
      schema["summary"] = "日本語100字以内の事実要約1行"

    example = {
      "importance": 35,
      "type": "other",
      "summary": "（例）○○が発表されたため、△△への影響が見込まれる。",
      "key_points": ["事実1", "事実2", "事実3"],
      "perspectives": {"engineer":"...", "management":"...", "consumer":"..."},
      "tags": ["ニュース", "影響"],
      "evidence_urls": [url]
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "次の入力を分析し、スキーマに厳密準拠したJSONのみを返してください。前後に説明文・コードブロックは禁止。"},
            {"role": "user", "content": f"スキーマ: {json.dumps(schema, ensure_ascii=False)}"},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            {"role": "user", "content": "出力チェック: (1) JSONのみ (2) フィールド欠落なし (3) 型一致 (4) summary<=100字 (5) key_pointsは本文の事実のみ (6) evidence_urlをevidence_urlsに含める。違反があれば自己修正してから最終JSONを出力せよ。"},
            {"role": "user", "content": f"出力例（この形式で）：{json.dumps(example, ensure_ascii=False)}"}
        ],
        "temperature": 0.2,
        "max_tokens": 500
    }

    r = post_lmstudio(payload, timeout=120)
    text = r.json()["choices"][0]["message"]["content"].strip()

    # ... LLM応答 text を取得したあと
    candidate = _extract_json_object(text)
    if not candidate:
        return _repair_json_with_llm(text)

    try:
        return json.loads(candidate)
    except Exception:
        return _repair_json_with_llm(candidate)

def _repair_json_with_llm(bad_text: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "次のテキストを、有効なJSONだけに修復して返せ。JSON以外は禁止。"},
            {"role": "user", "content": bad_text},
        ],
        "temperature": 0.0,
        "max_tokens": 700,
    }
    r = post_lmstudio(payload, timeout=120)
    fixed = _get_lm_content(r)
    candidate = _extract_json_object(fixed)
    if not candidate:
        raise ValueError("no json object in repaired response")
    return json.loads(candidate)

def upsert_insight(conn, topic_id, insight, src_article_id: int | None, src_hash: str):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO topic_insights(
        topic_id,
        importance,
        type,
        summary,
        key_points,
        evidence_urls,
        tags,
        perspectives,
        updated_at,
        src_article_id,
        src_hash,
        inferred
      )
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(topic_id) DO UPDATE SET
        importance=excluded.importance,
        type=excluded.type,
        summary=excluded.summary,
        key_points=excluded.key_points,
        evidence_urls=excluded.evidence_urls,
        tags=excluded.tags,
        perspectives=excluded.perspectives,
        updated_at=excluded.updated_at,
        src_article_id=excluded.src_article_id,
        src_hash=excluded.src_hash,
        inferred=excluded.inferred
    """, (
        topic_id,
        int(insight.get("importance", 0)),
        insight.get("type", "other"),
        insight.get("summary", ""),
        json.dumps(insight.get("key_points", []), ensure_ascii=False),
        json.dumps(insight.get("evidence_urls", []), ensure_ascii=False),
        json.dumps(insight.get("tags", []), ensure_ascii=False),
        json.dumps(insight.get("perspectives", {}), ensure_ascii=False),
        _now(),
        src_article_id,
        src_hash,
        int(insight.get("inferred") or 0)
    ))


def main():
    t0 = _now_sec()
    print("[TIME] step=llm start")
    conn = connect()
    cur = conn.cursor()

    # topic_insights に inferred 列が無ければ追加
    try:
        cur.execute("ALTER TABLE topic_insights ADD COLUMN inferred INTEGER DEFAULT 0")
        conn.commit()
        print("[INFO] added column topic_insights.inferred")
    except sqlite3.OperationalError:
        # 既に存在する場合は無視
        pass

    rescue = ("--rescue" in sys.argv)
    limit = 1500 if rescue else 300
    rows = pick_topic_inputs(conn, limit=limit, rescue=rescue)
    print(f"[DEBUG] rescue={rescue} llm candidates={len(rows)}")
    print(f"[DEBUG] llm candidates={len(rows)}")  # ←追加：0ならLLM以前で弾かれている
    if not rows:
        print("[INFO] no topics to summarize")
        conn.close()
        return
    
    pending = 0
    for r in rows:
        r = dict(r)  # ★ sqlite3.Row -> dict（.get() を使えるようにする）
        topic_id = r["topic_id"]

        try:
            t1 = _now_sec()
            body = (r["body"] or "").strip()
            title = (r["topic_title"] or "").strip()
            url = (r["url"] or "").strip()

            # URLが無いものは根拠URL要件を満たせないのでスキップ（事故防止）
            if not url:
                print(f"[WARN] skip topic_id={topic_id} because url empty")
                continue

            src_hash = hashlib.sha1(
                (title + "\n" + (r.get("category") or "") + "\n" + (r.get("kind") or "") + "\n" + url + "\n" + body)
                .encode("utf-8", errors="ignore")
            ).hexdigest()

            # rescueでない通常運用は「同一入力を二度処理しない」
            prev_hash = (r["prev_src_hash"] or "").strip()
            if (not rescue) and prev_hash and (prev_hash == src_hash):
                print(f"[SKIP] same src_hash topic_id={topic_id}")
                continue

            ins = call_llm(
                title,
                r.get("category") or "other",
                url,
                body,
                kind=r.get("kind"),
            )

            # --- 正規化（欠落対策） ---
            try:
                ins["importance"] = int(ins.get("importance") or 0)
            except Exception:
                ins["importance"] = 0

            if not ins.get("type"):
                ins["type"] = "other"

            # ★categoryではなく kind も含めて NEWS 判定
            is_news = ((r.get("category") or "").lower() == "news") or ((r.get("kind") or "").lower() == "news")

            # ★重要度=0は異常値として潰す（NEWS/それ以外で下限を変える）
            if ins["importance"] <= 0:
                ins["importance"] = 10 if is_news else 20
            
            # ★NEWSで評価が落ちた場合、topics.score_48h を救済ヒントとして反映
            if r.get("category") == "news":
                hint = r.get("importance_hint") or 0
                if hint and ins["importance"] <= 10:
                    # NEWSは過大評価を避けるため上限40程度に抑える
                    ins["importance"] = min(max(int(hint), 10), 40)

            # ★newsはプレースホルダ禁止（空なら失敗扱いにする）
            if r["category"] == "news":
                s = (ins.get("summary") or "").strip()
                if not s:
                    raise RuntimeError("news summary is empty")
            else:
                if not ins.get("summary"):
                    ins["summary"] = "（要約を生成できませんでした）"
            
            print(f"[TIME] llm_one topic={topic_id} sec={_now_sec() - t1:.1f}")

            # URLを必ず入れる保険
            if "evidence_urls" not in ins or not ins["evidence_urls"]:
                ins["evidence_urls"] = [r["url"]]

            # key_points 補完
            kps = ins.get("key_points") or []
            kps = [x for x in kps if isinstance(x, str) and x.strip()]

            if r["category"] == "news":
                # NEWSは「推測で埋める」方針（固定プレースホルダは禁止）
                fallback = [
                    "推測: 詳細はリンク先の本文確認が必要",
                    "推測: 背景や影響は本文で確認が必要",
                    "推測: 続報で条件が変わる可能性がある",
                ]
                i = 0
                while len(kps) < 3 and i < len(fallback):
                    kps.append(fallback[i])
                    i += 1
            else:
                # tech等は従来通りでもOK
                while len(kps) < 3:
                    kps.append("（本文中の明確な事実は限定的）")

            ins["key_points"] = kps[:3]

                        # perspectives 補完（NEWSは推測で埋める）
            p = ins.get("perspectives")
            if not isinstance(p, dict):
                p = {}

            # 空/欠落を埋める（NEWSは推測コメントOK）
            if r["category"] == "news":
                p_fallback = {
                    "engineer": "推測: 技術的な影響や背景はリンク先本文の確認が必要",
                    "management": "推測: 社会的影響や対応要否は続報・一次情報で判断が必要",
                    "consumer": "推測: 生活への影響は現時点では不明で、詳細確認が望ましい",
                }
            else:
                # tech等は推論可だが、最低限空にしない
                p_fallback = {
                    "engineer": "（技術観点のコメントを生成できませんでした）",
                    "management": "（経営観点のコメントを生成できませんでした）",
                    "consumer": "（利用者観点のコメントを生成できませんでした）",
                }

            for k in ("engineer", "management", "consumer"):
                v = p.get(k)
                if not isinstance(v, str) or not v.strip():
                    p[k] = p_fallback[k]

            ins["perspectives"] = p

            # --- 最終バリデーション（保存前の保険） ---
            if "importance" not in ins:
                ins["importance"] = 10 if r.get("category") == "news" else 20

            try:
                ins["importance"] = int(ins.get("importance") or 0)
            except Exception:
                ins["importance"] = 0

            if ins["importance"] <= 0:
                ins["importance"] = 10 if r.get("category") == "news" else 20


            # --- 最終ガード：0/欠落をDBへ入れない ---
            is_news = ((r.get("category") or "").lower() == "news") or ((r.get("kind") or "").lower() == "news")
            try:
                ins["importance"] = int(ins.get("importance") or 0)
            except Exception:
                ins["importance"] = 0
            if ins["importance"] <= 0:
                ins["importance"] = 10 if is_news else 20

            if "evidence_urls" not in ins or not ins["evidence_urls"]:
                ins["evidence_urls"] = [r["url"]]

            upsert_insight(conn, topic_id, ins, r["src_article_id"], src_hash)

            pending += 1
            if pending >= 50:
                conn.commit()
                pending = 0

            print(f"[OK] insight saved topic_id={topic_id} imp={ins['importance']} cat={r['category']}")

        except Exception as e:
            print(f"[WARN] insight failed topic_id={topic_id} cat={r['category']} err={e}")
            continue
    if pending:
        conn.commit()

    print(f"[TIME] step=llm end sec={_now_sec() - t0:.1f}")

if __name__ == "__main__":
    main()
