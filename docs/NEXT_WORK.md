# 次回Work：この順で再開

1. `WORK_PROGRESS.md`、`OPERATIONS.md`、`PHASE2_SOURCE_AUDIT.md`、`SISTER_IMPORT_20261117.md` を読む。新サイトのGitHub main最新を取得し、公開45記事/40人、40フィードの基準から開始する。公開済み17人と姉妹サイト流用10人を再発掘しない。
2. 流用元は読取時点の固定メタデータで、旧サイトの今後の取り下げと自動同期しない。転載/寄稿の執筆者とブログ所有者が異なるものは分離設計まで保留。
3. 最新Actions、`state/status.json`、公開URLの実数を確認。変更があれば実数を優先し、古いローカルstateをpushしない。
4. `state/review.json` の候補から、未充実領域・古い年代を少数ずつ原文確認。筆者・公開日・対象適合性・重複・利用条件を確認し、`config/moderation.json` へ正確なreviewed_title/reviewed_at等を登録する。品質採点せず、1人だけ大量追加しない。
5. WordPress/独自ドメイン、ソロ、解散済み、海外非韓国、制作者論などの新しい書き手を手動探索。候補は `config/candidates.json`、確認済み筆者は `config/sources.json`、RSS外の実在する過去記事は `config/manual_articles.json` に登録。本文や画像を保存しない。
6. グループ/ソロ・人物・楽曲は安定IDと別名で追加し、同名・所属期間を確認。タイはShimmer Shrimpmer、SNH48は海外分類、ライブ開催日と記事公開日を取り違えない。
7. `python -m unittest discover -s tests -v`、`node tests/search.cjs`、`python scripts/build.py`。必要な変更範囲だけブラウザ確認し、機能単位でGitHubへ保存する。
8. 接続API書込403の場合は `OPERATIONS.md` の画面アップロード手順。ソースパッチZIPへstate/distを含めず、Actions成功・通常ファイルの保存・公開反映まで確認する。
9. 実数、残タスク、エラー、検証限界を進捗に更新。未選定のピックアップを無理に埋めない。実機スマホと大規模ブラウザ実測は未完了。

旧・坂道考察アンテナはリポジトリ/記事/設定/公開/定期更新を変更しない。新サイトからは姉妹リンク済み。逆リンクは元サイト変更禁止の解除後のみ。
