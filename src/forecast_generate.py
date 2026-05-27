# src/forecast_generate.py
"""直近ニュース記事をもとにOllamaで未来予測レポートを自動生成する（ローカル専用）"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

from db import connect, init_db
from llm_insights_api import (
    post_ollama,
    _get_lm_content,
    _extract_json_object,
    _repair_json_with_llm,
)

FORECASTS_DIR = Path("data/forecasts")

# --- カテゴリ日本語名（sources.yaml と同期） ---
CAT_LABELS = {
    "news": "一般ニュース", "market": "市況（コモディティ・海運・スクラップ）",
    "industry": "産業", "security": "セキュリティ", "security_ot": "セキュリティ(OT)",
    "ai": "AI", "policy": "政策・規制（脱炭素）",
    "company": "企業動向", "dev": "開発", "manufacturing": "製造（鉄鋼）",
    "environment": "環境", "quality": "品質",
    "system": "システム", "maintenance": "保全",
    "smart_factory": "スマートファクトリー（導入事例）",
    "decarbonization_ops": "脱炭素オペレーション（算定・LCA）",
    "standards": "標準化・規格", "other": "その他",
}

HORIZONS = ["1週間後", "1〜6ヶ月後", "1年後"]

# --- 時間軸ごとの焦点とtemperature ---
# 注意: ここのキー文字列は forecast_verify / DB の horizon カラム / 過去レポートの
# Markdown 見出しと一致している必要があるため、リネームは互換性破壊になる。
HORIZON_CONFIG = {
    "1週間後": {
        "focus": (
            "1〜2週間以内（おおむね2週間以内）に起きる短期反応のみを書いてください: "
            "直接的な市場反応・株価変動・価格変動・政策発表・製品リリース・契約発表など。"
            "**「2027年までに」「中期的に」「長期的に」「○年後」など中長期スパンの予測は出力禁止**。"
            "もしニュースから1〜2週間スパンの具体的事象を抽出できない場合は、件数を減らしても構いません。"
        ),
        "temperature": 0.3,
    },
    "1〜6ヶ月後": {
        "focus": "技術導入・規制施行・業界再編・サプライチェーン変化などの波及効果に焦点を当ててください。",
        "temperature": 0.5,
    },
    "1年後": {
        "focus": "産業構造の変化・新市場の形成・技術の成熟・社会的影響に焦点を当ててください。",
        "temperature": 0.6,
    },
}

# 短期 horizon で出現したら除外する語彙パターン（中長期混入の検出）
_SHORT_TERM_LEAK_RE = re.compile(r"20(2[7-9]|[3-9]\d)年|中期的|長期的|数年(?:後|以内)|向こう数年")

# --- 重要度の最小閾値 ---
MIN_IMPORTANCE = 30

# ---------------------------------------------------------------------------
# 1. ニュースダイジェスト構築
# ---------------------------------------------------------------------------

def build_news_digest(cur, hours: int = 48, per_cat: int = 5) -> str:
    """直近の記事からカテゴリ別にサンプリングし、ダイジェストテキストを構築

    重要度が MIN_IMPORTANCE 未満の記事は除外する（insight未生成の新着記事はデフォルト50扱いで含める）。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur.execute("""
        SELECT a.title, a.category,
               COALESCE(ti.summary, '') as summary,
               COALESCE(ti.importance, 50) as importance
        FROM articles a
        LEFT JOIN topic_articles ta ON ta.article_id = a.id AND ta.is_representative = 1
        LEFT JOIN topic_insights ti ON ti.topic_id = ta.topic_id
        WHERE datetime(a.fetched_at) >= datetime(?)
          AND COALESCE(ti.importance, 50) >= ?
        ORDER BY ti.importance DESC NULLS LAST
    """, (cutoff, MIN_IMPORTANCE))

    by_cat: dict[str, list] = {}
    for title, cat, summary, importance in cur.fetchall():
        cat = cat or "other"
        if cat not in by_cat:
            by_cat[cat] = []
        if len(by_cat[cat]) < per_cat:
            by_cat[cat].append({
                "title": title or "",
                "summary": summary or "",
                "importance": int(importance or 0),
            })

    lines = []
    for cat, items in sorted(by_cat.items(), key=lambda x: -max((i["importance"] for i in x[1]), default=0)):
        label = CAT_LABELS.get(cat, cat)
        lines.append(f"【{label}】")
        for item in items:
            imp = f"[重要度{item['importance']}]" if item["importance"] else ""
            desc = item["summary"] if item["summary"] else item["title"]
            lines.append(f"- {imp} {item['title']} — {desc}")
        lines.append("")

    digest = "\n".join(lines)
    print(f"  ダイジェスト構築完了: {len(by_cat)}カテゴリ, {sum(len(v) for v in by_cat.values())}記事")
    return digest


# ---------------------------------------------------------------------------
# 2. LLM呼び出し
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
あなたはニュース分析に基づく未来予測の専門家です。
提示されたニュースダイジェストを分析し、指定された時間軸での「未来予測」を JSON 配列で出力してください。

【厳守ルール】
1. **未来時制を必須**: 「〜になる」「〜が起きる」「〜が増加する」「〜と見込まれる」など、未来の事象として書くこと。
   過去形（〜した／〜だった）、現在進行形（〜している／〜している最中）、現在事実の言い換え（〜が発表された）は「既報の繰り返し」と扱い、出力禁止。
2. **対象**: IT／製造業／テクノロジーに関連するもののみ。社会事件・政治・スポーツは出力しない。
3. **重複禁止**: 異なる時間軸であっても、同一企業・同一規制・同一テーマを別の角度で述べたものは重複扱い。出力しない。
4. **数値の扱い**:
   - ニュース原文に明示されている数値は、そのまま使い numeric_claims の source に元記事タイトルを記入。
   - ニュース原文に**明示されていない**数値（市場規模・成長率・地域シェアなど）を出す場合、その数値の直前に必ず "[推定] " プレフィックスを付け、numeric_claims の source を "[推定]" とする。
   - 数値を出さない場合 numeric_claims は空配列 [] でよい。
5. **影響度の閾値**:
   - 大: 業界全体（複数業界含む）に波及する変化
   - 中: 複数企業／一国レベルに影響する変化
   - 小: 単一企業・地域・特定プロダクトに留まる変化
6. **確信度の閾値**:
   - 高: 既存の契約・政策・公式ロードマップに基づく
   - 中: 過去パターンや業界動向からの外挿
   - 低: 複数あり得るシナリオの一つ
7. **subjects フィールド**: 影響を受ける主体名（企業名・業界名・地域名）を必ず配列で明示。
8. **evidence は必須かつ実質的に**: 「なぜそうなるか」のロジックを必ず書く。元ニュース記事のタイトルをそのままコピーするのは禁止（タイトルだけでは論拠にならない）。先行事例・市場動向・過去の類似事象・契約・統計を引用する形で論証する。evidence が空・元タイトル丸写し・「〜の記事」だけ等の場合、その予測は出力しない。
9. 出力は JSON のみ。挨拶・説明・コードブロック・注釈を一切出さない。必ず日本語で出力する。"""

PREDICTION_USER_TMPL = """\
以下は直近48時間の主要ニュースダイジェストです。

{digest}

{horizon_focus}
{previous_context}
上記ニュースに基づき、**{horizon}**の未来予測を3〜5件、以下のJSON形式で出力してください。
title は必須（空文字禁止）。prediction は必ず未来時制で書くこと。
[
  {{
    "impact": "大|中|小",
    "confidence": "高|中|低",
    "title": "予測タイトル（30字以内、未来時制で）",
    "prediction": "予測内容（未来時制、具体的な数値・主体名を含め、100字以内）",
    "evidence": "根拠となるニュースと論拠（100字以内、なぜそうなるかのロジックを含める）",
    "subjects": ["影響を受ける企業名/業界名/地域名（1〜3個）"],
    "numeric_claims": [
      {{"value": "12%", "source": "[推定]"}},
      {{"value": "200社", "source": "<元記事タイトル>"}}
    ]
  }}
]"""

SUMMARY_SYSTEM = """\
あなたはニュース分析の専門家です。
複数の時間軸にわたる未来予測の結果を俯瞰し、個別の予測を転記するのではなく、予測群を横断した構造的な示唆・マクロトレンドを3つ抽出してJSON配列で出力してください。
出力はJSONのみ。必ず日本語で出力してください。"""

SUMMARY_USER_TMPL = """\
以下は3つの時間軸の未来予測結果です。

{predictions_text}

上記の予測群を俯瞰し、個別の予測の繰り返しではなく、全体を通じて読み取れる構造的な示唆・マクロトレンドを3つ抽出してください。
各ポイントは複数の予測を横断的に統合した洞察にしてください。
以下のJSON形式で出力してください:
[
  {{
    "title": "ポイントのタイトル",
    "impact_description": "あなたへの影響（1〜2文）"
  }}
]"""


PERSPECTIVES_SYSTEM = """\
あなたはニュース分析の専門家です。
未来予測の結果を、指定された視点から分析し、その視点に特化した洞察をMarkdownで出力してください。
見出しや箇条書きを使い、読みやすく構造化してください。
必ず日本語で出力してください。Markdown以外の余計な文字（挨拶、説明、コードブロック）を出さないでください。"""

PERSPECTIVES_USER_TMPL = """\
以下は3つの時間軸の未来予測結果（確信度・根拠付き）と、ニュース原文から既に抽出された立場別コメントです。

{predictions_text}

上記の素材から **{perspective}視点** の分析を構造化してください。
**「ニュース原文から抽出された立場別コメント」セクションがある場合は、それを主要素材として優先的に使い**、
予測リストはあくまで参考として扱ってください。素材に書かれていない事実や数値を新たに創作してはいけません。
{perspective_guidance}

必ず以下のMarkdown形式で出力してください（見出しは必ず ### を使うこと。## は親見出しが別途付与されるため使用禁止）:

### 注目すべきトレンド

1. **トレンド名** — 説明
2. **トレンド名** — 説明

### リスクと機会

- **リスク**: 説明
- **機会**: 説明

### 推奨アクション

1. **アクション名** — 説明
2. **アクション名** — 説明"""

PERSPECTIVE_GUIDANCE = {
    "技術者": "技術的な実現可能性、アーキテクチャへの影響、学ぶべき新技術、開発プロセスへの影響に着目してください。他の視点（経営者・消費者）とは異なる、技術者ならではの独自の切り口で分析し、重複する内容は避けてください。",
    "経営者": "ビジネスインパクト、投資判断、競合優位性、リソース配分、組織戦略への影響に着目してください。他の視点（技術者・消費者）とは異なる、経営者ならではの独自の切り口で分析し、重複する内容は避けてください。",
    "消費者": "日常生活への影響、利便性の変化、コスト変動、プライバシーやセキュリティへの影響に着目してください。他の視点（技術者・経営者）とは異なる、消費者ならではの独自の切り口で分析し、重複する内容は避けてください。",
}

FORECAST_MODEL = os.environ.get("FORECAST_MODEL", "gpt-oss:20b")


# ---------------------------------------------------------------------------
# 英語残存検知 ＆ LLMによる日本語化（B案）
# ---------------------------------------------------------------------------
# LLM（gpt-oss:20b 等）は system prompt で日本語指定しても英文を返すことがある。
# 生成直後にフィールド単位で英文検知し、検出時のみ LLM 翻訳を再呼び出しする。

# ASCII 4文字以上の単語を英単語とみなす（"GPU", "AI" など短い略語は許容）
_EN_WORD_RE = re.compile(r"[A-Za-z]{4,}")


def _looks_english(text: str) -> bool:
    """英文を含むかを判定。

    4文字以上の英単語が2つ以上含まれていれば英文とみなす。
    "OpenAI製の新サービス" のように固有名詞単独の混入は許容する。
    """
    if not text:
        return False
    return len(_EN_WORD_RE.findall(text)) >= 2


_TRANSLATE_SYSTEM = """\
あなたは英日翻訳の専門家です。入力された英文を自然で簡潔な日本語に翻訳してください。
- 固有名詞（企業名・製品名・規格名）は原文のまま残してください。
- 数値・パーセント・期間表現は正確に保ってください。
- 出力は翻訳後の日本語のみ。説明・挨拶・引用符・コードブロック・見出しを一切付けないでください。"""


def _translate_to_ja(text: str) -> str:
    """LLMで英文を日本語化。日本語のみ／空文字／LLM失敗時は原文を返す。"""
    if not _looks_english(text):
        return text
    payload = {
        "model": FORECAST_MODEL,
        "messages": [
            {"role": "system", "content": _TRANSLATE_SYSTEM},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    try:
        resp = post_ollama(payload, timeout=60, retries=2)
        translated = _get_lm_content(resp).strip()
        # コードフェンス・前後の引用符を除去
        translated = re.sub(r"^```\w*\s*|\s*```$", "", translated, flags=re.MULTILINE).strip()
        translated = translated.strip().strip('"').strip("'").strip("「").strip("」")
        if translated:
            return translated
    except Exception as e:
        print(f"  [WARN] LLM翻訳失敗: {e}")
    return text


# 影響度／確信度の英語値→日本語enum マッピング
# LLMが "High / Medium / Low" や "Lower latency..." のような英文を返したケースに対応。
_IMPACT_MAP = {
    "大": "大", "中": "中", "小": "小",
    "high": "大", "large": "大", "major": "大",
    "medium": "中", "moderate": "中", "mid": "中",
    "low": "小", "lower": "小", "minor": "小", "small": "小",
}
_CONFIDENCE_MAP = {
    "高": "高", "中": "中", "低": "低",
    "high": "高", "medium": "中", "moderate": "中", "mid": "中",
    "low": "低",
}


def _normalize_enum(value: str, mapping: dict, default: str) -> str:
    """impact/confidence の英語値を日本語enumに正規化。

    "Lower latency for ..." のように説明文化された値は最初の単語で判定。
    マップ未ヒットなら default を返す。
    """
    if not value:
        return default
    head = re.split(r"[\s,.;:/]", str(value).strip(), maxsplit=1)[0].lower()
    return mapping.get(head, default)


def _safe_translate(value: str) -> str:
    """`_translate_to_ja` のラッパー。翻訳結果が空文字になったケースで原文を維持する。

    LLM翻訳は稀に空応答を返すため、上書きで title 等を喪失する事故を防ぐ二重防御。
    """
    if not isinstance(value, str) or not value.strip():
        return value or ""
    translated = _translate_to_ja(value)
    return translated if isinstance(translated, str) and translated.strip() else value


def _localize_prediction_item(item: dict) -> dict:
    """1件の予測項目について英文フィールドをLLMで日本語化し、enumを正規化。

    subjects / numeric_claims / unverified_numerics は LLM 由来の補助メタデータで、
    翻訳対象ではないため structure を保ったまま通過させる。
    """
    if not isinstance(item, dict):
        return item
    item["title"] = _safe_translate(item.get("title", ""))
    item["prediction"] = _safe_translate(item.get("prediction", ""))
    item["evidence"] = _safe_translate(item.get("evidence", ""))
    item["impact"] = _normalize_enum(item.get("impact", ""), _IMPACT_MAP, "中")
    item["confidence"] = _normalize_enum(item.get("confidence", ""), _CONFIDENCE_MAP, "中")
    # 新フィールドは構造を保ったまま保持（後段の重複抑制・数値検証で使う）
    subjects = item.get("subjects")
    if isinstance(subjects, list):
        item["subjects"] = [str(s).strip() for s in subjects if str(s).strip()]
    elif isinstance(subjects, str):
        item["subjects"] = [subjects.strip()] if subjects.strip() else []
    else:
        item["subjects"] = []
    nc = item.get("numeric_claims")
    item["numeric_claims"] = nc if isinstance(nc, list) else []
    return item


def _localize_predictions(predictions: list[dict]) -> list[dict]:
    """予測リスト全体を日本語化＆enum正規化。"""
    return [_localize_prediction_item(it) for it in predictions]


def _call_llm_json(system: str, user: str, max_tokens: int = 16000,
                    temperature: float = 0.4, max_retries: int = 2) -> list | dict:
    """Ollamaを呼び出してJSON結果を取得する。JSON解析失敗時はリトライする。"""
    for attempt in range(max_retries + 1):
        payload = {
            "model": FORECAST_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = post_ollama(payload, timeout=180, retries=2)
        raw_text = _get_lm_content(resp)

        # JSON抽出
        text = raw_text.strip().replace("```json", "").replace("```", "").strip()
        # 配列を試みる
        s = text.find("[")
        e = text.rfind("]")
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                pass
        # オブジェクトを試みる
        candidate = _extract_json_object(text)
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        # LLM修復
        try:
            return _repair_json_with_llm(raw_text)
        except Exception:
            if attempt < max_retries:
                print(f"  [WARN] JSON解析失敗、リトライ {attempt + 1}/{max_retries}")
                time.sleep(1)

    print(f"  [ERROR] JSON解析が{max_retries + 1}回失敗しました。空配列を返します")
    return []


def generate_predictions(digest: str, horizon: str,
                         previous_predictions: dict[str, list] | None = None) -> list[dict]:
    """1つの時間軸の予測を生成。前の時間軸の予測を渡すことで重複を抑制する。"""
    config = HORIZON_CONFIG.get(horizon, {"focus": "", "temperature": 0.4})

    # 前の時間軸の予測があれば重複抑制コンテキストを構築
    # 単なるタイトル列挙では LLM が「同じテーマでも言い回しを変えれば別物」と
    # 解釈するため、主体名（subjects）と prediction 先頭も渡して同一テーマ判定を強める。
    previous_context = ""
    if previous_predictions:
        prev_lines = [
            "以下は既に出した他の時間軸の予測です。これらと重複しない、この時間軸ならではの新しい予測を出してください。",
            "同じ主体（企業・規制・地域）や同じテーマを別の角度で述べたものも重複とみなします:\n",
        ]
        for h, items in previous_predictions.items():
            for item in items:
                subjects = item.get("subjects") or []
                subj_text = ", ".join(subjects) if subjects else "-"
                pred_head = (item.get("prediction") or "")[:50]
                prev_lines.append(
                    f"- [{h}] {item.get('title', '')} (主体: {subj_text}) / {pred_head}"
                )
        prev_lines.append("")
        previous_context = "\n".join(prev_lines)

    user = PREDICTION_USER_TMPL.format(
        digest=digest,
        horizon=horizon,
        horizon_focus=config["focus"],
        previous_context=previous_context,
    )
    def _call_and_filter(temp: float) -> list[dict]:
        raw = _call_llm_json(SYSTEM_PROMPT, user, temperature=temp)
        if isinstance(raw, dict):
            raw = [raw]
        # title / prediction / evidence のすべてが空のアイテムは除外
        return [
            it for it in raw
            if isinstance(it, dict) and _has_prediction_content(it)
        ]

    # 初回
    result = _call_and_filter(config["temperature"])
    # 空殻バグ緩和: 1件も残らなければ temperature を +0.2 して再試行する（1回のみ）
    if not result:
        retry_temp = min(1.0, float(config["temperature"]) + 0.2)
        print(f"  {horizon}: 初回0件のため temperature={retry_temp} で再試行")
        result = _call_and_filter(retry_temp)

    # 3〜5件に制限
    result = result[:5]
    # 英語残存があればLLMで日本語化＆enum正規化（system promptが効かないケースの保険）
    result = _localize_predictions(result)
    # 短期 horizon に中長期スパンの語彙が混入したら除去（プロンプト指示の最終防御）
    if horizon == "1週間後":
        before = len(result)
        result = [
            it for it in result
            if not _SHORT_TERM_LEAK_RE.search((it.get("prediction") or "") + " " + (it.get("evidence") or ""))
        ]
        if len(result) < before:
            print(f"  {horizon}: 中長期スパンを含む {before - len(result)} 件を除去")
    # 数値出典の検証: digest に裏付けのない数値を unverified_numerics に記録（本文は改変しない）
    result = [_validate_numeric_claims(it, digest) for it in result]
    print(f"  {horizon}: {len(result)}件の予測を生成")
    return result


def _has_prediction_content(item: dict) -> bool:
    """予測アイテムが最低限の中身（title / prediction / evidence のいずれか）を持つかを判定。"""
    for key in ("title", "prediction", "evidence"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return True
    return False


# 数値表現抽出用（パーセント・金額単位・社数等を含む）
_NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|％|億|兆|万|千|百|円|ドル|ユーロ|社|台|件|人|本)")

# 検証対象から **除外** する数値表現（P4）。パーセンテージは「予測の本質」であり
# LLM が独自に推定するのが当然なので、出典未確認バッジで読者を不安にさせない。
# 出典が問われるべきは「200社が採用」「90ドルに達する」のような、ニュース原文に
# 書いてあるはずの具体的な count / 金額。
_PERCENT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|％)")


def _smart_truncate_for_title(text: str, max_len: int = 40) -> str:
    """タイトル用に文字列を句読点優先で切り詰める（P3）。

    `prediction[:40]` の単純切り捨てでは「日本のOEMやフリート…」のように途中で
    切れて読みにくくなるため、最初の句読点（。、！？ / .,!?）で切ることを優先する。
    句読点がなければ max_len で切って末尾に「…」を付ける。
    """
    if not text:
        return ""
    text = text.strip()
    # max_len 以内に句読点があればそこで切る
    head = text[:max_len + 10]  # 句読点検索のため少し広めに
    for i, ch in enumerate(head):
        if i > max_len:
            break
        if ch in "。.!?！？":
            return head[: i + 1]
    # 読点（、,）は max_len の70%超えてからなら採用
    for i in range(len(head) - 1, int(max_len * 0.5), -1):
        if i < len(head) and head[i] in "、,":
            return head[:i]
    # フォールバック: 単純切り詰め + …
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def _is_title_redundant(title: str, prediction: str, overlap_ratio: float = 0.8) -> bool:
    """title が prediction とほぼ同じなら冗長と判定（P3）。

    例: title="ブレント原油先物は来週までに2％上昇する見込みです。"
        prediction="ブレント原油先物は来週までに2％上昇する見込みです。"
    のように title が prediction の先頭部分に丸ごと含まれる場合は冗長扱い。
    冗長な場合、build_markdown_report は title を短縮版に置き換える。
    """
    if not title or not prediction:
        return False
    t = title.strip().rstrip("。.!?！？")
    p = prediction.strip()
    if not t or not p:
        return False
    # title が prediction の prefix にある（先頭一致）
    if p.startswith(t):
        return True
    # 文字レベル共通部分が title の overlap_ratio 以上
    common = sum(1 for ch in t if ch in p[: len(t) + 10])
    return common / max(len(t), 1) >= overlap_ratio


def _validate_numeric_claims(item: dict, digest: str) -> dict:
    """予測 item の数値のうち digest（ニュース原文）に裏付けがないものを警告として記録する。

    本文（title/prediction/evidence）は改変しない。`unverified_numerics` メタデータに
    検出した未裏付け数値を追加するだけ。Markdown レンダ時に build_markdown_report が
    そのリストを ⚠ バッジ＋脚注として出す。

    判定方針:
    - prediction の文字列から数値表現を全て抽出
    - 既に `[推定]` プレフィックスで宣言されている数値はスキップ（LLM が自主申告）
    - LLM が出した numeric_claims の source="[推定]" にマッチする数値もスキップ
    - 残った数値が digest に含まれていなければ未裏付けとして記録
    """
    if not isinstance(item, dict):
        return item
    prediction = item.get("prediction") or ""
    if not prediction:
        return item

    # [推定] プレフィックス直後の数値は自主申告済みなのでスキップ対象
    estimated_values = set()
    for m in re.finditer(r"\[推定\]\s*(" + _NUMERIC_RE.pattern + ")", prediction):
        estimated_values.add(m.group(1).strip())
    # numeric_claims に "[推定]" 宣言がある value もスキップ
    for claim in (item.get("numeric_claims") or []):
        if isinstance(claim, dict) and "推定" in str(claim.get("source", "")):
            v = str(claim.get("value", "")).strip()
            if v:
                estimated_values.add(v)

    unverified = []
    for m in _NUMERIC_RE.finditer(prediction):
        value = m.group(0).strip()
        # 表記揺れに耐えるため空白除去で比較
        compact = value.replace(" ", "").replace("　", "")
        # パーセンテージは検証対象外（予測の本質的な推定値）
        if _PERCENT_RE.fullmatch(value):
            continue
        if any(compact == ev.replace(" ", "").replace("　", "") for ev in estimated_values):
            continue
        # digest に該当数値が含まれているか
        if compact in digest.replace(" ", "").replace("　", ""):
            continue
        unverified.append(value)

    if unverified:
        # 重複排除しつつ順序維持
        seen = set()
        deduped = []
        for u in unverified:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        item["unverified_numerics"] = deduped
    return item


def _dedupe_across_horizons(all_predictions: dict[str, list],
                            horizon_order: list[str],
                            threshold: int = 85) -> dict[str, list]:
    """複数 horizon に跨る重複予測を、短期 horizon 側を優先して除去する。

    LLM への previous_context 渡しだけでは「同じ主体・同じテーマを別の角度で」
    というケースを抑え切れないため、後処理で rapidfuzz token_set_ratio による
    意味類似度判定をかける。

    閾値は試行値 85（80〜90 で調整余地あり）。
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        print("  [WARN] rapidfuzz が未インストールのため重複除去をスキップ")
        return all_predictions

    def _signature(item: dict) -> str:
        parts = [
            item.get("title") or "",
            item.get("prediction") or "",
            " ".join(item.get("subjects") or []),
        ]
        return " ".join(p for p in parts if p)

    kept_signatures: list[str] = []
    result: dict[str, list] = {}
    for h in horizon_order:
        items = all_predictions.get(h) or []
        kept_here = []
        for item in items:
            sig = _signature(item)
            if not sig:
                kept_here.append(item)
                continue
            is_dup = any(
                fuzz.token_set_ratio(sig, prev) >= threshold
                for prev in kept_signatures
            )
            if is_dup:
                print(f"  [dedupe] {h}: 重複除去 -> {(item.get('title') or sig)[:50]}")
                continue
            kept_here.append(item)
            kept_signatures.append(sig)
        result[h] = kept_here
    # horizon_order に無い horizon（保険）はそのまま流す
    for h, items in all_predictions.items():
        if h not in result:
            result[h] = items
    return result


def _load_existing_today_report(report_date: str) -> dict:
    """今日のレポートが既に存在すればパースして horizon 別の既存予測を返す。

    戻り値: {
      "predictions": {"1週間後": [items...], "1〜6ヶ月後": [...], "1年後": [...]},
      "executive_summary": [dict, ...],   # 既存のエグゼクサマリー（生成回避用）
      "perspectives": {"技術者": str, ...},
      "exists": bool,
    }
    predictions に入るのは _has_prediction_content を満たす item のみ。
    空殻プレースホルダや空配列は除外される。
    """
    from forecast_parser import parse_forecast_markdown, parse_prediction_items
    import re

    empty = {"predictions": {}, "executive_summary": [], "perspectives": {}, "exists": False}
    dest = FORECASTS_DIR / f"report_{report_date}.md"
    if not dest.exists():
        return empty
    try:
        md = dest.read_text(encoding="utf-8")
    except OSError:
        return empty

    parsed = parse_forecast_markdown(md)
    # horizon 別予測を再構築（PredictionItem → dict）
    _badge_re = re.compile(
        r"\*{0,2}影響度[:：]\s*(\S+)\s*[/／]\s*確信度[:：]\s*(\S+)\*{0,2}"
    )
    # 「：」直後の水平空白のみを許容し、改行は含めない（次の行の `> **根拠**:` を誤マッチさせないため）
    _pred_re = re.compile(r"[-*][ \t]*\*{0,2}予測内容\*{0,2}[:：][ \t]*(.*)")
    _evi_re = re.compile(r">[ \t]*\*{0,2}根拠\*{0,2}[:：][ \t]*(.*)")

    # フォールバック注記（build_markdown_report で出力される定型文）は「中身なし」扱い
    _fallback_re = re.compile(r"この時間軸の予測は今回生成されませんでした")

    predictions: dict[str, list] = {}
    for horizon, section_md in parsed.predictions.items():
        # セクション全体がフォールバック注記のみならスキップ
        if _fallback_re.search(section_md):
            continue
        items = parse_prediction_items(section_md)
        out = []
        for it in items:
            body = it.body or ""
            # フォールバック注記がアイテムとして解釈されても弾く
            if _fallback_re.search((it.title or "") + " " + body):
                continue
            # body から prediction / evidence を復元
            pred_match = _pred_re.search(body)
            prediction = pred_match.group(1).strip() if pred_match else ""
            evi_match = _evi_re.search(body)
            evidence = evi_match.group(1).strip() if evi_match else ""
            # title は "予測N" のプレースホルダかチェック
            title = (it.title or "").strip()
            is_placeholder = bool(re.match(r"^予測\d+$", title))
            real_title = "" if is_placeholder else title

            recovered = {
                "title": real_title,
                "prediction": prediction,
                "evidence": evidence,
                "impact": it.impact or "中",
                "confidence": it.confidence or "中",
            }
            if _has_prediction_content(recovered):
                out.append(recovered)
        if out:
            predictions[horizon] = out

    # エグゼクティブサマリーを軽く再構築（完全一致不要、生成スキップ判定用）
    exec_summary = []
    if parsed.executive_summary:
        for line in parsed.executive_summary.splitlines():
            m = re.match(r"^\d+\.\s*\*\*(.+?)\*\*", line.strip())
            if m:
                exec_summary.append({"title": m.group(1), "impact_description": ""})

    return {
        "predictions": predictions,
        "executive_summary": exec_summary,
        "perspectives": parsed.perspectives or {},
        "exists": True,
    }


# IT/製造業/テクノロジー系のカテゴリ ID（_aggregate_topic_perspectives で許可するもの）。
# sources.yaml の英語カテゴリ ID と一致させる。事件・テロ・スポーツ・政治雑録など
# サイト主旨と関係ないトピックを3視点分析に混入させないための allowlist。
_TECH_CATEGORIES = (
    "ai", "dev", "system", "manufacturing", "quality",
    "maintenance", "smart_factory", "decarbonization_ops",
    "security", "security_ot", "standards", "policy",
    "industry", "company", "market", "environment",
)


def _aggregate_topic_perspectives(cur, hours: int = 48,
                                   top_n: int = 8) -> dict[str, list[str]]:
    """topic_insights.perspectives JSON を集約し、立場別コメントのリストを返す。

    既に llm_insights_local が記事ごとに engineer/management/consumer の3立場コメントを
    生成・保存している (src/llm_insights_api.py:351 _normalize_perspectives)。
    これを未来予測の 3視点分析プロンプトに「素材」として渡すことで、LLM の役割を
    「自由推論」から「集約と構造化」に格下げし、捏造リスクを下げる。

    重要: トピックは IT/製造業/テクノロジー系カテゴリ (_TECH_CATEGORIES) に限定する。
    事件・テロ・スポーツ等のニュースが重要度トップに来ると、3視点分析が予測と
    完全に乖離した内容に乗っ取られるため。

    戻り値: {"engineer": [...], "management": [...], "consumer": [...]}
    各値はニュース原文に紐付いた立場別コメントの文字列リスト（重要度上位 top_n 件）。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    result = {"engineer": [], "management": [], "consumer": []}
    placeholders = ",".join("?" * len(_TECH_CATEGORIES))
    try:
        cur.execute(f"""
            SELECT DISTINCT ti.perspectives, ti.summary, ti.importance, a.category
            FROM topic_insights ti
            JOIN topic_articles ta ON ta.topic_id = ti.topic_id AND ta.is_representative = 1
            JOIN articles a ON a.id = ta.article_id
            WHERE datetime(a.fetched_at) >= datetime(?)
              AND ti.perspectives IS NOT NULL
              AND COALESCE(ti.importance, 0) >= 50
              AND a.category IN ({placeholders})
            ORDER BY ti.importance DESC
            LIMIT ?
        """, (cutoff, *_TECH_CATEGORIES, top_n))
    except Exception as e:
        print(f"  [WARN] topic_insights 取得失敗: {e}")
        return result

    for raw_perspectives, summary, importance, category in cur.fetchall():
        if not raw_perspectives:
            continue
        try:
            obj = json.loads(raw_perspectives)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        cat_label = CAT_LABELS.get(category, category or "")
        prefix = f"(重要度{importance}/{cat_label}) " if importance else f"({cat_label}) "
        for key in ("engineer", "management", "consumer"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                result[key].append(prefix + val.strip())
    return result


def _format_aggregated_perspectives(agg: dict[str, list[str]]) -> str:
    """_aggregate_topic_perspectives の戻り値を LLM 入力用テキストに整形。"""
    label_map = {"engineer": "技術者", "management": "経営者", "consumer": "消費者"}
    lines = []
    for key, label in label_map.items():
        comments = agg.get(key) or []
        if not comments:
            continue
        lines.append(f"### {label}立場コメント（ニュース原文から抽出済み）")
        for c in comments[:10]:
            lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines)


def generate_perspectives(all_predictions: dict[str, list],
                          topic_perspectives: dict[str, list[str]] | None = None) -> dict[str, str]:
    """3視点（技術者・経営者・消費者）の分析を並列生成。根拠と確信度を含めた入力を渡す。

    topic_perspectives が与えられれば、ニュース原文から抽出した立場別コメントを
    予測テキストと一緒に LLM に渡し、捏造を抑えて構造化中心の出力を促す。
    """
    parts = []
    for horizon, items in all_predictions.items():
        parts.append(f"## {horizon}")
        for item in items:
            confidence = item.get('confidence', '中')
            title = item.get('title', '')
            prediction = item.get('prediction', '')
            evidence = item.get('evidence', '')
            parts.append(f"- [確信度:{confidence}] {title}: {prediction}（根拠: {evidence}）")
        parts.append("")
    predictions_text = "\n".join(parts)

    aggregated_text = _format_aggregated_perspectives(topic_perspectives or {})

    def _gen_one_perspective(name, guidance):
        # ニュース原文由来の立場別コメントを「主要素材」として先頭に注入
        if aggregated_text:
            combined_text = (
                "## ニュース原文から抽出された立場別コメント（主要素材）\n"
                f"{aggregated_text}\n"
                "## 予測リスト（参考素材）\n"
                f"{predictions_text}"
            )
        else:
            combined_text = predictions_text
        user = PERSPECTIVES_USER_TMPL.format(
            predictions_text=combined_text,
            perspective=name,
            perspective_guidance=guidance,
        )
        payload = {
            "model": FORECAST_MODEL,
            "messages": [
                {"role": "system", "content": PERSPECTIVES_SYSTEM},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
            "max_tokens": 12000,
        }
        resp = post_ollama(payload, timeout=180, retries=2)
        text = _get_lm_content(resp).strip()
        text = text.replace("```markdown", "").replace("```", "").strip()
        # `**見出し**` 単独行は ### に昇格させる（LLM が太字で見出し代用するケースの正規化）
        text = re.sub(
            r"^(?:\*\*|__)(.+?)(?:\*\*|__)$",
            r"### \1",
            text,
            flags=re.MULTILINE,
        )
        # LLM が指示に反して ## を返した場合は ### に降格（親見出しと階層が衝突しないように）
        text = re.sub(r"^##\s+", "### ", text, flags=re.MULTILINE)
        return name, text

    perspectives = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_gen_one_perspective, name, guidance): name
            for name, guidance in PERSPECTIVE_GUIDANCE.items()
        }
        for future in as_completed(futures):
            name, text = future.result()
            perspectives[name] = text
            print(f"  {name}視点: {len(text)}文字")

    return perspectives


def generate_executive_summary(all_predictions: dict[str, list]) -> list[dict]:
    """3時間軸の予測からエグゼクティブサマリーを生成"""
    parts = []
    for horizon, items in all_predictions.items():
        parts.append(f"## {horizon}")
        for item in items:
            parts.append(f"- {item.get('title', '')}: {item.get('prediction', '')}")
        parts.append("")
    predictions_text = "\n".join(parts)
    user = SUMMARY_USER_TMPL.format(predictions_text=predictions_text)
    result = _call_llm_json(SUMMARY_SYSTEM, user, max_tokens=8000)
    if isinstance(result, dict):
        result = [result]
    return result[:3]


# ---------------------------------------------------------------------------
# 3. Markdownレポート組み立て
# ---------------------------------------------------------------------------

def build_markdown_report(
    executive_summary: list[dict],
    predictions: dict[str, list[dict]],
    generated_at: str,
    perspectives: dict[str, str] | None = None,
) -> str:
    """forecast_parser.pyが期待する形式でMarkdownレポートを組み立てる"""
    lines = []
    lines.append("# 多視点ニュース分析・未来予測レポート")
    lines.append("")
    lines.append(f"**生成日時:** {generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # エグゼクティブサマリー
    lines.append("# 今週の最重要ポイント")
    lines.append("")
    for i, item in enumerate(executive_summary, 1):
        title = item.get("title", f"ポイント{i}")
        desc = item.get("impact_description", "")
        lines.append(f"{i}. **{title}**  ")
        lines.append(f"   *あなたへの影響:* {desc}  ")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 未来予測
    lines.append("# 未来予測")
    lines.append("")
    lines.append("> 影響度・確信度が高い予測を優先して掲載しています。")
    lines.append("")

    for horizon in HORIZONS:
        items = predictions.get(horizon, [])
        # 念のためレンダー直前にも空アイテムを弾く（generate_predictions のフィルタと二重防御）
        items = [it for it in items if isinstance(it, dict) and _has_prediction_content(it)]
        # 根拠 (evidence) が空のアイテムを除外（P2）。
        # 根拠なしの予測は信頼性ゼロで読者ノイズになる。LLM が evidence を返さなかった
        # ケースは品質欠落として扱い、表示しない。
        items = [it for it in items if (it.get("evidence") or "").strip()]
        lines.append(f"## {horizon}")
        lines.append("")
        if not items:
            # 予測が1件も得られなかった時間軸にはフォールバック文言を明示する。
            # これで「### 1. 予測1（中身なし）」のような誤誘導表示が出なくなる。
            lines.append("> ※ この時間軸の予測は今回生成されませんでした（LLM応答の解析に失敗した可能性があります）。")
            lines.append("")
            lines.append("")
            continue
        # 影響度×確信度でソート（影響度: 大>中>小、確信度: 高>中>低）
        impact_order = {"大": 0, "中": 1, "小": 2}
        conf_order = {"高": 0, "中": 1, "低": 2}
        items.sort(key=lambda x: (impact_order.get(x.get("impact", "小"), 2),
                                   conf_order.get(x.get("confidence", "低"), 2)))
        for idx, item in enumerate(items, 1):
            impact = item.get("impact", "中")
            confidence = item.get("confidence", "中")
            title = (item.get("title") or "").strip()
            prediction = (item.get("prediction") or "").strip()
            evidence = (item.get("evidence") or "").strip()
            # title 空時は prediction を句読点優先で切ってフォールバック（P3）。
            # 単純な [:40] では「日本のOEMやフリート…」のように途中で切れる問題を回避する。
            if not title:
                title = _smart_truncate_for_title(prediction, max_len=40) if prediction else ""
            # title が長すぎる場合も同様に整形（LLM が30字制限を守らないケース）
            elif len(title) > 50:
                title = _smart_truncate_for_title(title, max_len=40)
            # title と prediction が冗長（先頭一致）なら、title を句読点で短くする（P3）。
            # 例: title "ブレント原油先物は来週までに2％上昇する見込みです。"
            #     prediction 同上 → title を「ブレント原油先物が来週2％上昇」程度に縮める
            if title and prediction and _is_title_redundant(title, prediction):
                short_title = _smart_truncate_for_title(title, max_len=25)
                # 句読点で切った結果が短くなれば採用、変わらなければ末尾の重複を取り除く
                if short_title and short_title != title:
                    title = short_title
            if not title:
                continue
            unverified = item.get("unverified_numerics") or []
            badge = " 📊 [推定値あり]" if unverified else ""

            lines.append(f"### {idx}. {title}{badge}")
            lines.append("")
            lines.append(f"**影響度: {impact} / 確信度: {confidence}**")
            lines.append("")
            lines.append(f"- **予測内容**：{prediction}")
            lines.append("")
            lines.append(f"> **根拠**: {evidence}")
            if unverified:
                lines.append("")
                lines.append(f"> 📊 推定値（ニュース原文での明示なし）: {', '.join(str(u) for u in unverified)}")
            lines.append("")
        lines.append("")

    # 3視点分析
    if perspectives:
        lines.append("---")
        lines.append("")
        lines.append("# 3視点分析")
        lines.append("")
        for name in ["技術者", "経営者", "消費者"]:
            content = perspectives.get(name, "")
            if content:
                lines.append(f"## {name}視点")
                lines.append("")
                lines.append(content)
                lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 保存
# ---------------------------------------------------------------------------

def save_report(md_text: str, report_date: str, executive_summary_text: str,
                 model_id: str = "", temperature_config: str = "") -> str:
    """Markdownをファイル保存しDBに登録する"""
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = FORECASTS_DIR / f"report_{report_date}.md"
    dest.write_text(md_text, encoding="utf-8")

    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO forecast_reports
            (report_date, file_path, executive_summary, created_at, model_id, temperature_config)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
            file_path = excluded.file_path,
            executive_summary = excluded.executive_summary,
            created_at = excluded.created_at,
            model_id = excluded.model_id,
            temperature_config = excluded.temperature_config
    """, (
        report_date,
        str(dest),
        executive_summary_text[:2000],
        datetime.utcnow().isoformat(timespec="seconds"),
        model_id,
        temperature_config,
    ))
    conn.commit()
    conn.close()
    print(f"  保存完了: {dest}")
    return str(dest)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ニュース記事から未来予測レポートを自動生成")
    parser.add_argument("--max-sec", type=int, default=600, help="最大実行時間(秒)")
    parser.add_argument("--hours", type=int, default=48, help="対象記事の期間(時間)")
    parser.add_argument("--per-cat", type=int, default=5, help="カテゴリ当たりの記事数")
    parser.add_argument("--min-importance", type=int, default=30, help="重要度の最小閾値")
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の今日のレポートを無視して全horizonを再生成する",
    )
    args = parser.parse_args()

    global MIN_IMPORTANCE
    MIN_IMPORTANCE = args.min_importance

    t0 = time.time()
    print(f"[forecast_generate] 開始 (model={FORECAST_MODEL})")

    init_db()
    conn = connect()
    cur = conn.cursor()

    # 0. 既存の今日レポートを読み込み（差分リカバリー用）
    #   1日4回のバッチ運用で、初回に失敗した horizon のみ次回以降で埋められるようにする。
    now_jst = datetime.now(timezone(timedelta(hours=9)))
    report_date = now_jst.strftime("%Y-%m-%d")
    existing = {} if args.force else _load_existing_today_report(report_date)
    existing_predictions: dict[str, list] = existing.get("predictions", {}) if existing else {}
    existing_perspectives: dict[str, str] = existing.get("perspectives", {}) if existing else {}
    existing_exec_summary: list[dict] = existing.get("executive_summary", []) if existing else []

    if existing.get("exists"):
        filled = [h for h in HORIZONS if existing_predictions.get(h)]
        missing = [h for h in HORIZONS if not existing_predictions.get(h)]
        print(f"[0/5] 既存レポート検出: 充足={filled}, 要再生成={missing}")
        # 全 horizon が埋まっていて、視点も揃っているなら LLM を呼ばず再レンダのみ行う
        if not missing and all(existing_perspectives.get(n) for n in ["技術者", "経営者", "消費者"]):
            print("[0/5] 全horizon＋全視点が既に埋まっています。再生成スキップ（--force で強制再生成可）")
            conn.close()
            return

    # 1. ニュースダイジェスト構築
    print("[1/5] ニュースダイジェスト構築...")
    digest = build_news_digest(cur, hours=args.hours, per_cat=args.per_cat)
    if not digest.strip():
        print("[ERROR] 対象記事が見つかりません")
        conn.close()
        sys.exit(1)

    # 2. 各時間軸の予測生成（空の horizon のみ再生成し、既存は維持）
    all_predictions: dict[str, list] = {}
    any_regenerated = False
    for i, horizon in enumerate(HORIZONS):
        if time.time() - t0 > args.max_sec:
            print(f"[WARN] タイムアウト({args.max_sec}秒)に達しました")
            # タイムアウトしても、未処理 horizon に既存予測があれば流用して
            # 出力から脱落させない（次回バッチでさらに改善できる）
            for rest in HORIZONS[i:]:
                rest_items = existing_predictions.get(rest) or []
                if rest_items and rest not in all_predictions:
                    all_predictions[rest] = _localize_predictions(rest_items)
                    print(f"  {rest}: タイムアウト後、既存{len(rest_items)}件を流用")
            break
        prev_items = existing_predictions.get(horizon) or []
        if prev_items and not args.force:
            # 既に中身ありなら LLM 呼び出しをスキップし、既存を採用
            # 過去バッチが英語のまま保存していた場合に備えて再ローカライズ（日本語のみなら追加コストなし）
            all_predictions[horizon] = _localize_predictions(prev_items)
            print(f"[2/5] {horizon}: 既存の予測{len(prev_items)}件を流用 ({i+1}/{len(HORIZONS)})")
            continue
        print(f"[2/5] {horizon}の予測を生成中... ({i+1}/{len(HORIZONS)})")
        all_predictions[horizon] = generate_predictions(
            digest, horizon,
            previous_predictions=all_predictions if all_predictions else None,
        )
        any_regenerated = True

    # 2.5 horizon 跨ぎ重複の後処理除去（previous_context だけでは抑え切れないケースの安全網）
    if any_regenerated:
        before_counts = {h: len(v) for h, v in all_predictions.items()}
        all_predictions = _dedupe_across_horizons(all_predictions, HORIZONS)
        after_counts = {h: len(v) for h, v in all_predictions.items()}
        if before_counts != after_counts:
            print(f"[2.5/5] 重複除去: {before_counts} -> {after_counts}")

    # 3. エグゼクティブサマリー生成（予測が変わったときのみ or 既存が空のとき）
    if any_regenerated or not existing_exec_summary:
        print("[3/5] エグゼクティブサマリー生成中...")
        exec_summary = generate_executive_summary(all_predictions)
        print(f"  サマリー: {len(exec_summary)}件")
    else:
        print("[3/5] 予測に変化なし。既存サマリーを維持")
        exec_summary = existing_exec_summary

    # 4. 3視点分析生成（予測が変わった or 視点が欠落している場合のみ）
    perspectives = {}
    need_perspective_regen = any_regenerated or not all(
        existing_perspectives.get(n) for n in ["技術者", "経営者", "消費者"]
    )
    if time.time() - t0 < args.max_sec and need_perspective_regen:
        print("[4/5] 3視点分析生成中...")
        # topic_insights.perspectives を集約し「主要素材」として LLM に渡す
        topic_perspectives = _aggregate_topic_perspectives(cur, hours=args.hours)
        agg_counts = {k: len(v) for k, v in topic_perspectives.items()}
        print(f"  既存立場別コメントを集約: {agg_counts}")
        perspectives = generate_perspectives(all_predictions, topic_perspectives=topic_perspectives)
    elif not need_perspective_regen:
        print("[4/5] 予測・視点とも既存を流用")
        perspectives = existing_perspectives
    else:
        print("[4/5] タイムアウトのため3視点分析をスキップ")
        # タイムアウト時も既存があればそれを使う
        perspectives = existing_perspectives or {}

    # 5. レポート組み立て・保存
    print("[5/5] レポート組み立て・保存...")
    # report_date は冒頭で決定済み。generated_at は今回の保存時刻を使う。
    generated_at = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")

    md_text = build_markdown_report(exec_summary, all_predictions, generated_at, perspectives)

    # サマリーテキスト（DB用）
    summary_lines = []
    for item in exec_summary:
        summary_lines.append(f"- {item.get('title', '')}: {item.get('impact_description', '')}")
    summary_text = "\n".join(summary_lines)

    temp_config = json.dumps(
        {h: c["temperature"] for h, c in HORIZON_CONFIG.items()},
        ensure_ascii=False,
    )
    save_report(md_text, report_date, summary_text,
                model_id=FORECAST_MODEL, temperature_config=temp_config)

    conn.close()
    elapsed = time.time() - t0
    print(f"[forecast_generate] 完了 ({elapsed:.1f}秒)")


if __name__ == "__main__":
    main()
