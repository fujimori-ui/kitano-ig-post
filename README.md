# 北野工作所 Instagram 自動投稿(クラウド版)

パソコンの電源が入っていなくても、毎朝自動で @kashiba_yanereform に投稿する仕組みです。
投稿のネタは `posts/` に番号順(01, 02, …)で入れてあり、朝7:00・昼12:30・夜20:00の1日3本、順番に出ます。毎月のチラシ(flyer_YYYYMM)はその月の7日前から他より先に出ます(月1回必ず)。

## 流れ

1. claude.ai の定期ルーティン(朝7:00・昼12:30・夜20:00)が GitHub Actions `post.yml` を起動
2. `post_ig.py` が `posts/` の次の1本を Instagram API で投稿。順番は番号順ではなく、種類(施工事例/豆知識/訪問販売注意/会社紹介/お困りごと)が**まんべんなく回る**ように、いちばん久しく出ていない種類の中で番号が小さいものを選ぶ(2026-10-26〜。同じ種類ばかり続かない)。種類は投稿名のキーワードで判定(`post_ig.py` の CATEGORY_RULES。新しい種類の投稿は `chuui_` `mame_` `jirei_` `komari_` などを名前に入れる。それ以外は会社紹介扱い)。これからの順番は `python post_ig.py --plan 30` で確認できる
3. 投稿済みは `state.json` に記録(Actions がコミットで書き戻す)
4. ルーティンが結果(投稿URL・残り本数)を fujimori@jibulabo.jp にメールで知らせる
5. 予備: GitHub の schedule が 9:30 / 14:30 / 22:00 JST にも起動し、その時間帯(朝=〜11時/昼=11〜17時/夜=17時〜)が未投稿のときだけ投稿(ルーティン失敗の保険)。
   同じ時間帯に2本出ることはない。予備は朝7〜11時/昼12〜17時/夜20〜23時半の間だけ動く(深夜投稿なし)。
6. 今月のチラシ(posts/flyer_YYYYMM.jpg)がまだ無いと、朝の結果メールの件名に「・今月のチラシ未作成」が付く → 表裏PDFをもらって `make_flyer.py` で作る。

## Googleマイビジネス(ビジネスプロフィール)用の保存(2026-10-26〜)

Instagram に1本投稿するたびに、`gbp_export.py` が同じ内容の「マイビジネス用」を Google ドライブに保存します(投稿が失敗しない限り毎回)。
- 保存先: マイドライブの `北野工作所_マイビジネス投稿用/日付_時刻_ネタ名/`(フォルダ ID は `state.json` の `gbp_folder_id`。ドライブ内で移動してもOK)
- `画像.jpg` = 1200×900 の横長(投稿画像を中央に、まわりは同じ画像をぼかして敷く。マイビジネス推奨サイズで左右が切れない)
- `本文.txt` = ハッシュタグを外し、「プロフィールのリンクから」をホームページURLに替えた本文(1500字以内)
- フォルダの `使い方.txt` にスマホからの投稿手順。結果メールの RESULT 行にもそのフォルダのURLが付く
- マイビジネスへの投稿自体は手作業(API は使わない)。1日1本でもOK
- 接続は Google 広告と同じ OAuth クライアント + `drive.file` 権限。Secrets `GDRIVE_CLIENT_ID` / `GDRIVE_CLIENT_SECRET` / `GDRIVE_REFRESH_TOKEN`。
  キーの取り直しは `~/google_ads/get_token_gdrive.py`(URLを auth_url_gdrive.txt に書き、ブラウザで許可すると Secrets 登録と投稿済みぶんの保存まで自動)
- 手元で試す: `python3 gbp_export.py --test 13_amadoi`(gbp_preview/ に書き出すだけ) / `--one 13_amadoi` / `--backfill`(投稿済みで未保存のものを全部)

## ネタの自動作成(2026-10-26〜)

毎週月曜5:00に claude.ai のルーティン「北野工作所IG: 毎週月曜 来週分21本を自動作成→メール報告」(trig_01SV6ZwBzUZry2VyU4opVGSW)が動き、
`AUTO_GENERATE.md` の手順で来週分21本の中身を `content/auto_YYYYMMDD.json` に書いて push → `build.yml` が画像(Notoフォント)と動画(BGM付き)を作って `posts/` に commit → 一覧画像(`content/preview/`)のリンク付きでGmail報告。
- BGM(購入曲)と高画質写真は非公開リポ `fujimori-ui/kitano-ig-private` に置き、Actions が `PHOTOS_TOKEN` で取り込む
- 直したい投稿があれば、その JSON を直して push し直す(画像を作り直すときは Actions → kitano-ig-build → Run workflow → force にファイル名)。外したい投稿は `posts/NN_slug.*` と JSON の項目を消す
- 自分のPCで試す: `python3 build_auto.py --check content/xxx.json` → `KITANO_FONT=noto python3 build_auto.py`
- 全部の投稿に写真を入れる(文字だけにしない)。写真は photos_hd/(非公開リポ)の現場写真・社長・作業中・トラック。`make_posts.py` の DEFAULT_PHOTOS に投稿名→写真の対応があり、自動生成はJSONの `photo` で指定
- 施工事例(Before/After)は写真が必要なので自動では作らない。写真をもらったら `make_posts.py` の `ba_post` で手作業

## ネタの追加(手作業)

`posts/NN_slug.jpg`(1080×1350)と `posts/NN_slug.txt`(本文+ハッシュタグ)を同じ名前で置いて push するだけ。
画像は `make_posts.py` で作っています(サイト kashiba-yanereform.com の文章・写真が元)。

**アニメーション(リール)**: `python make_videos.py` で各 jpg から `NN_slug.mp4`(約8秒・9:16)を作って一緒に push。
mp4 があるネタはリール(フィードにも表示)で投稿、無いネタは今まで通り画像で投稿されます。
画像を作り直したら `python make_videos.py 03_kawara` のように動画も作り直してください。

**リールの表紙(カバー)**: `posts/cover/NN_slug.jpg`(1080×1920、動画の最後のコマと同じ)。`make_videos.py` が動画と一緒に自動で作り、
無い/動画より古い表紙は実行のたびに動画の最後のコマから作り直します(表紙だけ全部作り直す: `python make_videos.py --covers`)。
4:5 の投稿画像をそのまま表紙にすると Instagram が 9:16 に広げて左右が切れる(2026-10-26 に判明)ので、必ず cover を一緒に push すること。
cover が無いと投稿画像で代用され(左右が切れる)、結果メールに ⚠ が付きます。

**BGM**: 購入曲(Audiostock)は OneDrive\Desktop\北野工作所様\BGM\ に保管 → このリポの `music\private\` にコピーしてから動画を作る(`music/` は公開しない)。無ければ代わりに `make_music.py` で自前合成したさわやかなBGM(`music/bgm_a〜c.wav`、著作権フリー)が自動で入ります。購入曲が複数あれば、隣の投稿と違う曲を選び、使う部分も他の投稿と20秒以上離す(いつも同じに聞こえないように。記録は `music_log.json`)。動画の長さ(8〜11秒)とアニメーションの動かし方(ヘッダー/フッター/写真/文字の出し方・順番・速さ)も投稿ごとに自動で変わる。
既存の mp4 の音だけ入れ直すときは `python make_music.py add 05_hisashi`(全部なら `add-all`)。

- 特定のネタを今すぐ投稿: Actions → kitano-ig-post → Run workflow → slug に `03_kawara` など
- 投稿せず次の1本を見る: dry_run を true
- やり直し(同じネタをもう一度出す): `state.json` からその項目を消して push

## 必要な GitHub Secrets

- `KITANO_IG_USER_ID` … Instagram ユーザーID
- `KITANO_IG_ACCESS_TOKEN` … Instagram アクセストークン(約60日。`refresh-token.yml` が毎週自動延長)
- `PHOTOS_TOKEN` … Secrets を書き戻すための GitHub トークン
- `GDRIVE_CLIENT_ID` / `GDRIVE_CLIENT_SECRET` / `GDRIVE_REFRESH_TOKEN` … マイビジネス用を Google ドライブへ保存するため(無いと ⚠ 付きで投稿だけ続く)

トークンの発行: Meta for Developers → 「あかり工務店」アプリ → Instagram → 「InstagramログインによるAPI設定」→ アクセストークンを生成 → kashiba_yanereform でログイン。
