# 次回Work：この順で再開

2026-11-25更新。現在は [初回移行記録](discovery-20261125/REPORT.md) と [自動運用](AUTONOMOUS_COLLECTION.md) が基準。GitHubの最新main・Actions・公開データを照合し、`state/status.json` の滞留数、フィード障害、系列別の偏りを確認する。以下は移行前の履歴。

2026-11-18追記：デザインは全面刷新済み。DESIGN_REFRESH_20261118.mdと公開確認記録を先に読む。編集元はweb/とscripts/build.py。開始時点は200記事・41人で、以下の49記事は旧記録。distを直接編集せず、最新mainを優先する。デザイン更新と記事審査は独立して扱う。


1. `WORK_PROGRESS.md`、`OPERATIONS.md`、`PHASE2_SOURCE_AUDIT.md`、`SISTER_IMPORT_20261117.md` を読む。新サイトのGitHub main最新を取得し、公開49記事/41人、41フィードの基準から開始する。公開済み17人と姉妹サイト流用10人を再発掘しない。
2. 流用元は読取時点の固定メタデータで、旧サイトの今後の取り下げと自動同期しない。転載/寄稿の執筆者とブログ所有者が異なるものは分離設計まで保留。
3. 最新Actions、`state/status.json`、公開URLの実数を確認。変更があれば実数を優先し、古いローカルstateをpushしない。
4. `state/review.json` の候補から、未充実領域・古い年代を少数ずつ原文確認。筆者・公開日・対象適合性・重複・利用条件を確認し、`config/moderation.json` へ正確なreviewed_title/reviewed_at等を登録する。品質採点せず、1人だけ大量追加しない。
5. WordPress/独自ドメイン、ソロ、解散済み、海外非韓国、制作者論などの新しい書き手を手動探索。候補は `config/candidates.json`、確認済み筆者は `config/sources.json`、RSS外の実在する過去記事は `config/manual_articles.json` に登録。本文や画像を保存しない。
6. グループ/ソロ・人物・楽曲は安定IDと別名で追加し、同名・所属期間を確認。タイはShimmer Shrimpmer、SNH48は海外分類、ライブ開催日と記事公開日を取り違えない。
7. `python -m unittest discover -s tests -v`、`node tests/search.cjs`、`python scripts/build.py`。必要な変更範囲だけブラウザ確認し、機能単位でGitHubへ保存する。
8. 接続API書込403の場合は `OPERATIONS.md` の画面アップロード手順。ソースパッチZIPへstate/distを含めず、Actions成功・通常ファイルの保存・公開反映まで確認する。
9. 実数、残タスク、エラー、検証限界を進捗に更新。未選定のピックアップを無理に埋めない。実機スマホと大規模ブラウザ実測は未完了。

旧・坂道考察アンテナはリポジトリ/記事/設定/公開/定期更新を変更しない。新サイトからは姉妹リンク済み。逆リンクは元サイト変更禁止の解除後のみ。

本人依頼の深山1234（lively_fennel526）を通常筆者として追加済み。初期公開は秋元康・AKB楽曲論1本。AUTHOR_REGISTRATION_20261117.md参照。新着は他筆者同様に確認待ち。

最後にREVIEW_BATCH_20261117.mdの3本を追加済み。SixTONES/Negicco/NMBの同じ記事を再審査しない。日付の不一致があるNegicco仙台記事は保留。


## 2026-11-18 新規書き手発掘完了

48関連11人、イコノイジョイ9人、KAWAII LAB.10人を登録し、各1記事を本文確認して公開。書き手41→71人、公開200→230記事。ソース0de7285、Actions 44218893127成功。54ページの人気・新着を探索。詳細は docs/discovery-20261118/REPORT.md、registrations.json、survey.json、verification.json、resume.json。

今回の30人は publication_mode=manual とし、将来の未審査RSSを確認待ちに固定。元の41人や全体の自動掲載設定は維持。次回もこの指定を一括standard等へ書き換えない。保留はわた（jin_294）1人、今回記事の主題が対象外なのはD人1人。config/candidates.json参照。各タグ2ページ目以降・育成枠と海外48の本文審査を伴う発掘は未完了。既存biscuit0904フィードのDNS一時障害は次回確認。


最終追記：今回30人・30記事の追加を含む公開データは、並行作業の既存書き手19記事追加後に249記事・71人。run 44219747086で保存9a4a095とPages公開成功。全体は既存biscuit0904のDNSエラー通知でfailure表示（今回30RSSは成功）。36テスト成功。詳細 docs/discovery-20261118/verification.json。


## 2026-11-18 女性アイドル全般の書き手発掘（最新）

ハロプロ・卒業生8人、スターダスト関連7人、WACK関連6人、その他国内7人、女性K-POP2人の計30人を追加し、確認済み各1記事を公開。71人249記事→101人279記事。人気・新着46タグ92ページの初回HTMLから探索した。既存249掲載記事の維持、既存除外記事の公開復活0、新規30人のRSS取得成功、Python39テスト・検索テスト成功を確認。

登録コミット：76d6e9c / 2664c6d / 0f48f4b。Actions run 44254604367 publish成功。公開データ101人279記事、全新規書き手30ページ、実ブラウザでの件数・検索結果・新規記事表示を確認済み。

新規ソースは、直近の新着自動掲載方式に合わせてstandard＋登録時刻のauto_publish_afterを設定。登録前の記事は手動承認したもの以外を自動公開せず、登録後の新着は既存判定・確認待ちを通す。過去のmanual固定の記録は当時の状態であり、現在の設定を一括で戻さない。

保留2人、記事単位の不採用2本、登録技術失敗0人。30人の名前・プロフィール・記事URL、グループ別調査件数、未調査範囲、保留理由は [今回の調査記録](discovery-women-20261118/REPORT.md)、取得日時と候補は同ディレクトリのsurvey.json、公開確認はpublic-verification.jsonを参照。各タグ2ページ目以降や、未審査グループの本文確認は未完了。
