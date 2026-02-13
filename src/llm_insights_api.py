import json
import os
import re
import subprocess
import time

import requests

LMSTUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
_SESSION = requests.Session()
_LMSTUDIO_READY = False
_AUTOSTART_ATTEMPTED = False
_SELECTED_MODEL = None
_FAILED_MODELS = set()


def _is_lmstudio_ready(timeout: float = 2.0) -> bool:
    health_url = LMSTUDIO_URL.rsplit("/chat/completions", 1)[0] + "/models"
    try:
        r = _SESSION.get(health_url, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


def _models_url() -> str:
    return LMSTUDIO_URL.rsplit("/chat/completions", 1)[0] + "/models"


def _extract_model_ids(data: dict) -> list[str]:
    models = data.get("data") or []
    ids = []
    for item in models:
        if isinstance(item, dict):
            mid = (item.get("id") or "").strip()
            if mid:
                ids.append(mid)
    return ids


def _available_models(timeout: float = 4.0) -> list[str]:
    r = _SESSION.get(_models_url(), timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    return _extract_model_ids(r.json())


def _pick_model_candidates(timeout: float = 4.0) -> list[str]:
    requested = (os.getenv("LMSTUDIO_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    fallback = (os.getenv("LMSTUDIO_FALLBACK_MODEL") or "").strip()

    try:
        model_ids = _available_models(timeout=timeout)
    except Exception:
        model_ids = []

    candidates = []

    def _add(mid: str):
        if mid and (mid not in candidates) and (mid not in _FAILED_MODELS):
            candidates.append(mid)

    _add(_SELECTED_MODEL or "")

    if model_ids:
        if requested in model_ids:
            _add(requested)
        if fallback and fallback in model_ids:
            _add(fallback)
        for mid in model_ids:
            _add(mid)
        _add(requested)
        _add(fallback)
    else:
        _add(requested)
        _add(fallback)

    if not candidates:
        candidates = [requested]

    return candidates


def _pick_usable_model(timeout: float = 4.0) -> str:
    return _pick_model_candidates(timeout=timeout)[0]


def _is_model_load_error(detail) -> bool:
    msg = str(detail).lower()
    return (
        "failed to load model" in msg
        or "erroroutofdevicememory" in msg
        or "out of memory" in msg
    )


def _ensure_lmstudio_ready() -> None:
    global _LMSTUDIO_READY, _AUTOSTART_ATTEMPTED
    if _LMSTUDIO_READY:
        return
    if _is_lmstudio_ready():
        _LMSTUDIO_READY = True
        return

    autostart_cmd = (os.getenv("LMSTUDIO_AUTOSTART_CMD") or "").strip()
    if not autostart_cmd:
        raise RuntimeError(
            "LMStudio is not reachable at 127.0.0.1:1234. "
            "Start LMStudio manually or set LMSTUDIO_AUTOSTART_CMD to auto-launch it."
        )
    if _AUTOSTART_ATTEMPTED:
        raise RuntimeError("LMStudio auto-start was attempted but the API is still unavailable.")

    _AUTOSTART_ATTEMPTED = True
    subprocess.Popen(
        autostart_cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    wait_sec = int(os.getenv("LMSTUDIO_AUTOSTART_WAIT_SEC", "45"))
    for _ in range(max(wait_sec, 1)):
        if _is_lmstudio_ready():
            _LMSTUDIO_READY = True
            return
        time.sleep(1)
    raise RuntimeError("LMStudio auto-start command was launched, but API did not become ready in time.")


def _get_lm_content(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"LMStudio returned non-JSON: {resp.text[:500]}") from e

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise RuntimeError(f"LMStudio unexpected schema: {str(data)[:500]}") from e


def post_lmstudio(payload: dict, timeout: int, retries: int = 2, backoff_sec: float = 0.8):
    global _SELECTED_MODEL
    _ensure_lmstudio_ready()
    body = dict(payload)
    last_err = None

    for i in range(retries + 1):
        candidates = _pick_model_candidates()
        for model in candidates:
            body["model"] = model
            try:
                r = _SESSION.post(LMSTUDIO_URL, json=body, timeout=timeout)
                if r.status_code >= 400:
                    try:
                        detail = r.json()
                    except Exception:
                        detail = r.text
                    if _is_model_load_error(detail):
                        _FAILED_MODELS.add(model)
                        if _SELECTED_MODEL == model:
                            _SELECTED_MODEL = None
                        print(f"[WARN] model '{model}' failed to load on LM Studio; trying another loaded model")
                        continue
                    raise RuntimeError(f"LMStudio HTTP {r.status_code}: {detail}")

                _SELECTED_MODEL = model
                return r
            except Exception as e:
                last_err = e

        if i < retries:
            time.sleep(backoff_sec * (i + 1))
            continue

    if last_err:
        raise last_err
    raise RuntimeError("LMStudio request failed: no model candidate succeeded")


def _extract_json_object(text: str) -> str | None:
    if not text:
        return None
    t = text.strip().replace("```json", "").replace("```", "").strip()
    s = t.find("{")
    e = t.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    return t[s:e + 1]


def _repair_json_with_llm(bad_text: str) -> dict:
    payload = {
        "model": _pick_usable_model(),
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


def call_llm_short_news(title: str, body: str, url: str = "") -> dict:
    system = (
        "あなたはニュース記事の要約アシスタント。出力はJSONのみ。"
        "summary は本文/タイトルに明記された事実のみで日本語1文（推測は禁止）。"
        "key_points は配列で最大3つ。事実が足りない場合、残りは必ず '推測: ' で始めて補完する（断定しない）。"
        "perspectives は {engineer,management,consumer} の3キー。短い本文でも必ず埋める。"
        "perspectives は原則 '推測: ' で始める（本文に明記された事実だけで言える場合のみ推測不要）。"
        "同じ内容の繰り返しは禁止。抽象的すぎる文（例:『詳細は本文確認が必要』だけ）は禁止。"
    )
    body_for_llm = (body or "").strip()[:1200]
    title = (title or "").strip()

    user = (
        f"タイトル: {title}\nURL: {url}\n本文:\n{body_for_llm}\n\n"
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

    payload = {"model": _pick_usable_model(), "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.3, "max_tokens": 700}
    r = post_lmstudio(payload, timeout=60)
    s = _get_lm_content(r)

    if not s:
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
            perspectives = {"engineer": (p.get("engineer") or "").strip(), "management": (p.get("management") or "").strip(), "consumer": (p.get("consumer") or "").strip()}
            inferred = 1 if int(obj.get("inferred") or 0) == 1 else 0
        except Exception:
            pass

    if not summary:
        summary = title

    kps = [x.strip() for x in (key_points or []) if isinstance(x, str) and x.strip()][:3]
    if not kps:
        kps = ["推測: 本文情報が少ないため、影響範囲はリンク先で要確認"]

    def _fill_if_empty(v: str, fallback: str) -> str:
        return (v or "").strip() or fallback

    perspectives["engineer"] = _fill_if_empty(perspectives.get("engineer"), "推測: 技術面では、影響範囲（対象サービス/システム）と再発防止策の有無が要確認")
    perspectives["management"] = _fill_if_empty(perspectives.get("management"), "推測: 経営面では、信用/コンプライアンス/説明責任への影響が要確認")
    perspectives["consumer"] = _fill_if_empty(perspectives.get("consumer"), "推測: 利用者目線では、生活への影響や取るべき行動（注意喚起等）の有無が要確認")

    if inferred == 0 and "推測:" in (" ".join(kps) + " " + " ".join(perspectives.values())):
        inferred = 1

    return {
        "importance": 10,
        "type": "other",
        "summary": summary,
        "key_points": kps,
        "perspectives": perspectives,
        "tags": ["ニュース"],
        "evidence_urls": [url] if url else [],
        "inferred": inferred,
    }


def call_llm(topic_title, category, url, body, kind: str | None = None):
    is_news = (category == "news") or ((kind or "").lower() == "news")
    if is_news:
        return call_llm_short_news(topic_title, body, url=url)

    body = (body or "").strip()[:1200]
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
    user = {"topic_title": topic_title, "category": category, "evidence_url": url, "text": body}
    schema = {
        "importance": "0-100の整数。",
        "type": "security|release|research|incident|biz|other",
        "summary": "日本語100字以内の要約1行（結論→理由の順）",
        "key_points": ["本文に明記された事実1", "本文に明記された事実2", "本文に明記された事実3"],
        "perspectives": {"engineer": "技術者目線のコメント（50字以内）", "management": "経営者目線のコメント（50字以内）", "consumer": "消費者目線のコメント（50字以内）"},
        "tags": ["1〜5個"],
        "evidence_urls": ["根拠URL（最低1つ）"],
    }

    payload = {
        "model": _pick_usable_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "次の入力を分析し、スキーマに厳密準拠したJSONのみを返してください。前後に説明文・コードブロックは禁止。"},
            {"role": "user", "content": f"スキーマ: {json.dumps(schema, ensure_ascii=False)}"},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    r = post_lmstudio(payload, timeout=120)
    text = _get_lm_content(r)
    candidate = _extract_json_object(text)
    if not candidate:
        return _repair_json_with_llm(text)
    try:
        return json.loads(candidate)
    except Exception:
        return _repair_json_with_llm(candidate)
