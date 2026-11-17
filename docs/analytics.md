# アイドル考察アンテナ：GA4計測

Google Analytics 4の測定IDは **G-WJ4KERSCRC**。坂道考察アンテナのIDとは別です。

## 自分のアクセスを除外する

本番サイト https://sakura-essays.github.io/idol-kosatsu-antenna/?analytics=off を管理者のブラウザごとに一度開く。ブラウザ内に停止状態を保持する。計測再開は `?analytics=on`。別ブラウザ、別端末、データ削除後は再設定が必要。テストは `?analytics=test`。Googleへ送らず画面下部にイベントを表示する。地域別の除外はしない。

## 主なイベント

- `page_view`：物理ページ読み込みのみ。履歴変更はPVに含めない
- `article_impression`：記事リンクが画面上で50%以上・1秒間表示（読了を意味しない）
- `article_click`：記事へのリンククリック（通常・中クリック・Ctrl/Cmdクリック）
- `view_search_results` / `writer_search`：記事・書き手の検索
- `filter_change`：絞り込みや並び順の変更
- `random_draw`：新旧記事のランダム抽選
- `writer_shuffle` / `more_results`：書き手並べ直し・結果の追加表示

イベントには選択カテゴリー・グループ・並び順・検索語・結果件数などを付与。公開済みの記事タイトル、書き手名、リンク先URLも送信する。メールアドレス、電話番号、URLと推定できる検索語を伏せ、サイト内検索条件を含むページURLは送らない。

## GA4の管理画面で設定すること

拡張計測の「ブラウザの履歴イベントに基づくページ変更」と「サイト内検索」をオフにする。JavaScript側で `send_page_view:false` とし、手動の `page_view` を1回送信する。

必要に応じてイベントスコープのカスタムディメンション `placement`、`author_name`、`article_title`、`article_group`、`site_view`、`filter_category`、`filter_group`、`filter_topic`、`sort_order`、`zero_results`、`draw_type`、`measurement_version` を登録。検索結果件数 `result_count` はイベントスコープのカスタム指標として登録。

GA4は広告ブロックなどにより計測漏れがあり、記事リンクのクリックが遷移先での閲覧や読了を保証するものではない。
