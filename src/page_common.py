"""サブページ（diff/entity/exec/topic タイムライン等）共通の HTML 部品。

各モジュールがほぼ同一の <style> を複製していたため、ベース部分をここに集約する。
ページ固有のスタイルは各モジュール側で PAGE_BASE_CSS の後ろに追記する
（後勝ちなので body{max-width:960px} のような上書きも可能）。
"""

PAGE_BASE_CSS = (
    "body{font-family:system-ui,-apple-system,sans-serif;max-width:820px;"
    "margin:2rem auto;padding:0 1rem;color:#1f2937;line-height:1.6}"
    "h1{font-size:1.4rem;border-bottom:2px solid #2563eb;padding-bottom:.3rem}"
    ".meta{color:#6b7280;font-size:.9rem;margin-bottom:1rem}"
    "a{color:#2563eb}"
)
