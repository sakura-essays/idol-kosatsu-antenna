# 次回Workの実行順

1. `docs/WORK_PROGRESS.md` を読み、公開・検証結果を確認。GitHub mainの最新を取得する。
2. Actionsの最新成否と公開URLを確認。直近の `state/status.json` にRSSエラーがあれば、元サイトを触らず当該フィードだけ調べる。
3. `state/review.json` から領域・年代・書き手の偏りを見て元記事を確認。本文や画像は保存せず、`config/moderation.json` で対象適合性のみを承認する。少数の筆者だけ大量承認しない。
4. 地域・ソロ・解散済み・海外非韓国の公開ブログを手動検索。実在・日付・感想・利用条件・フィードを確認し `config/candidates.json` に候補登録。架空URLを補わない。
5. 確認できた書き手は `config/sources.json`、RSS外の過去記事は `config/manual_articles.json` へ。人物は所属期間と固有IDを保持して辞書追加。短い略称・同名は自動確定しない。
6. `python -m unittest discover -s tests -v`、`node tests/search.cjs`、`python scripts/build.py` を実行。検索・抽選・書き手ページ・取り下げを必要な範囲で検証。
7. 機能単位でGitHubへ保存しActions成功と公開反映を確認。
8. 実数・エラー・残作業を進捗に追記。未確認のものを完了扱いしない。

旧サイト側の相互リンクは、元サイトの変更禁止条件が解除された場合だけ最小変更する。それまでは新サイト側リンクと引き継ぎ記録を維持する。

新規リポジトリへの接続書込はGit Trees APIで403になった。初回はGitHub画面のアップロードとワークフローで通常ファイルへ展開・保存済み。再調査せず、次回の権限状態を必要なときだけ確認する。
