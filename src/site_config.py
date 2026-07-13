"""サイト全体の共通設定。

公開サイトの URL は環境変数 FEED_SITE_URL で上書きできる。
モジュールごとに同じデフォルト値を重複定義しない（過去に別ドメインの
プレースホルダが混在した事故があったため、必ずここから import する）。
"""

import os

SITE_URL = os.environ.get(
    "FEED_SITE_URL", "https://nodokaharukaze.github.io/daily-tech-trend/"
)
