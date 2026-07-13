"""サブページ（diff/entity/exec/topic タイムライン等）共通の HTML 部品。

各モジュールがほぼ同一の <style> を複製していたため、ベース部分をここに集約する。
ページ固有のスタイルは各モジュール側で PAGE_BASE_CSS の後ろに追記する
（後勝ちなので body{max-width:960px} のような上書きも可能）。
"""

PAGE_BASE_CSS = (
    ":root{color-scheme:light dark}"
    "body{font-family:system-ui,-apple-system,sans-serif;max-width:820px;"
    "margin:2rem auto;padding:0 1rem;color:#1f2937;line-height:1.6}"
    "h1{font-size:1.4rem;border-bottom:2px solid #2563eb;padding-bottom:.3rem}"
    ".meta{color:#6b7280;font-size:.9rem;margin-bottom:1rem}"
    "a{color:#2563eb}"
)

# ダークモード上書き。各モジュールの固有スタイルより「後」に置くこと
# （<style> の末尾に {PAGE_DARK_CSS} を挿入する）。
PAGE_DARK_CSS = """
@media (prefers-color-scheme: dark){
  body{background:#111827;color:#e5e7eb}
  a,.diff-table a,.timeline-title,ul.entity-list a,.count{color:#7ea9ff}
  h1{border-bottom-color:#7ea9ff}
  h2{color:#7ea9ff}
  .meta,.meta-info,.timeline-date,.timeline-meta,.timeline-snippet,.kind,dl dt,.refs h3,.empty{color:#9ca3af}
  .summary,.exec-item,.diff-table th{background:#1b2432}
  .diff-table th,.diff-table td,ul.entity-list li,li,.exec-item{border-color:#374151}
  ol.timeline{border-left-color:#374151}
  .exec-fallback{color:#fbbf24;background:#3a2e10}
}
"""
