# アイドル考察アンテナ

人気の大小を離れて、アイドルを読む。公開済みの個人の考察・批評・感想への、メタデータとリンクの総合アンテナです。

公開URL: https://sakura-essays.github.io/idol-kosatsu-antenna/

姉妹サイト: https://sakura-essays.github.io/sakurazaka-kosatsu-antenna/

**作業再開時は `docs/WORK_PROGRESS.md` → `docs/NEXT_WORK.md` を最初に読むこと。**

## 動かす

Python 3.12、Node 22。外部パッケージ不要。

```sh
python -m unittest discover -s tests -v
node tests/search.cjs
python scripts/collect.py
python scripts/build.py
```

`dist/index.html` を直接開いても検索可能。公開は独立したActionsとPages（Source: GitHub Actions）。通常は6時間おきにRSS取得し、未審査の記事を確認待ちへ保存します。push時は取得せずテスト・ビルド・公開。取得失敗時は既存データを維持し、公開した後にActionsを失敗表示にします。

## データの所在

|ファイル|役割|
|---|---|
|`config/sources.json`|確認済み書き手・公開RSS/Atom。新着はすべて確認待ち|
|`config/manual_articles.json`|元記事で確認した過去記事。確認日と根拠必須|
|`config/moderation.json`|記事単位の承認、訂正、URL・書き手の掲載停止|
|`config/taxonomy.json`|大分類・グループ・人物・楽曲の固有IDと表記揺れ|
|`config/pickups.json`|本文を読み選考したURLと紹介文。初期は空|
|`config/candidates.json`|推薦・発掘候補。自動掲載されない|
|`state/articles.json`|蓄積メタデータ。本文は含めない|
|`state/review.json`|確認待ちのメタデータ|
|`state/status.json`|直近の取得成否|
|`web/`|画面編集元|
|`dist/`|生成済み公開ファイル。直接編集しない|

## 編集・取り下げ

`docs/OPERATIONS.md` に手順と承認形式を記録。通常記事を品質採点しません。短い感想も対象。記事の対象適合性と公開元・日付だけを確認し、読み応えによる判断はピックアップに限定します。

検索は登録済みメタデータのみ。辞書にないメンバー・曲はタイトルに含まれる場合だけ検索できます。全アイドルの人物辞書が完成したという意味ではありません。

## 元サイトとの独立性・再利用

元リポジトリの調査時点: `119bef51fe4a3e6cca17f5c8c10923df9f3009db`。
MITのRSS/Atomパーサー、URL正規化、安全な取得、原子的JSON保存、創作検出補助を `scripts/feed.py` へ移植。分類・画面・承認フローは総合アンテナ用に分離しました。旧サイトへの実行時アクセス、データ共有、GA4 IDの継承はありません。元サイトのリポジトリ・登録記事・設定・ワークフローは変更しません。

ソフトウェアはMIT。記事タイトル・筆者名等の権利は各権利者に帰属します。
