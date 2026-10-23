# 北野工作所 Instagram 自動投稿(クラウド版)

パソコンの電源が入っていなくても、毎朝自動で @kashiba_yanereform に投稿する仕組みです。
投稿のネタは `posts/` に番号順(01, 02, …)で入れてあり、朝7:00と夜20:00の1日2本、順番に出ます。

## 流れ

1. claude.ai の定期ルーティン(朝7:00・夜20:00)が GitHub Actions `post.yml` を起動
2. `post_ig.py` が `posts/` の次の1本(未投稿で番号が一番小さいもの)を Instagram API で投稿
3. 投稿済みは `state.json` に記録(Actions がコミットで書き戻す)
4. ルーティンが結果(投稿URL・残り本数)を fujimori@jibulabo.jp にメールで知らせる

## ネタの追加

`posts/NN_slug.jpg`(1080×1350)と `posts/NN_slug.txt`(本文+ハッシュタグ)を同じ名前で置いて push するだけ。
画像は `make_posts.py` で作っています(サイト kashiba-yanereform.com の文章・写真が元)。

**アニメーション(リール)**: `python make_videos.py` で各 jpg から `NN_slug.mp4`(約8秒・9:16)を作って一緒に push。
mp4 があるネタはリール(フィードにも表示・表紙は jpg)で投稿、無いネタは今まで通り画像で投稿されます。
画像を作り直したら `python make_videos.py 03_kawara` のように動画も作り直してください。

- 特定のネタを今すぐ投稿: Actions → kitano-ig-post → Run workflow → slug に `03_kawara` など
- 投稿せず次の1本を見る: dry_run を true
- やり直し(同じネタをもう一度出す): `state.json` からその項目を消して push

## 必要な GitHub Secrets

- `KITANO_IG_USER_ID` … Instagram ユーザーID
- `KITANO_IG_ACCESS_TOKEN` … Instagram アクセストークン(約60日。`refresh-token.yml` が毎週自動延長)
- `PHOTOS_TOKEN` … Secrets を書き戻すための GitHub トークン

トークンの発行: Meta for Developers → 「あかり工務店」アプリ → Instagram → 「InstagramログインによるAPI設定」→ アクセストークンを生成 → kashiba_yanereform でログイン。
