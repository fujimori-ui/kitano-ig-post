# Googleビジネスプロフィール(マイビジネス)への自動投稿

Instagram に投稿したネタを、同じ内容で北野工作所のビジネスプロフィールにも自動投稿する仕組み。
(2026-10-27 作成。それまでは Google ドライブに「マイビジネス用」を保存して手で投稿していた)

## 仕組み
1. `post_ig.py` が Instagram に投稿(今まで通り)
2. `gbp_export.py` がマイビジネス用(横長画像+ハッシュタグ無し本文)を Google ドライブへ保存(今まで通り・控え用)
3. **新規** `gbp_post.py` が Google の API(Business Profile API)でビジネスプロフィールに「最新情報」として投稿
   - 写真 = `gbp_img/NN_slug.jpg`(1200×900)。post.yml が投稿前に作って push(Google が公開URLで取りに来る)
   - 本文 = ドライブ用と同じ(ハッシュタグ無し、ホームページURL入り)
   - ボタン = 「詳細」→ https://kashiba-yanereform.com/
   - 結果は state.json の posted[slug].gbp_post と RESULT 行(メール)に出る
4. 接続キーが無い・API 未承認・投稿先未設定のときは ⚠ を付けて Instagram だけで完了(止まらない)

## 使えるようにするまで(Google の承認が必要)
Business Profile API は申請制。Cloud プロジェクトは Google 広告・ドライブと同じ **utopian-pier-326805(番号 1052537713441)**。

### 1. 接続キーの取得(ユーザーがブラウザで2回「許可」)
```
cd ~/google_ads && python3 get_token_gbp.py
```
- 1回目 auth_url_gbp1.txt … Cloud プロジェクトで API 3つを有効にする許可(キーは保存しない)
- 2回目 auth_url_gbp2.txt … ビジネスプロフィール管理の許可 → gbp_creds.json → GitHub Secrets GBP_CLIENT_ID / GBP_CLIENT_SECRET / GBP_REFRESH_TOKEN
- 「このアプリは Google で確認されていません」と出たら「詳細」→「(安全ではないページ)に移動」で進む(自社アプリなので問題なし)

### 2. API アクセス申請(ユーザーが Google のフォームに記入)
https://support.google.com/business/contact/api_default
fujimori@jibulabo.jp でログインして記入。記入例:

| 項目 | 記入例 |
|---|---|
| 会社名 | ジブラボ (JibuLabo) |
| 会社のウェブサイト | https://jibulabo.jp/ |
| 連絡先メール | fujimori@jibulabo.jp |
| Google Cloud プロジェクト ID | utopian-pier-326805 |
| プロジェクト番号 | 1052537713441 |
| 業種 / 立場 | マーケティング支援(小規模工務店のコンサルティング・代理) / Agency |
| 対象の店舗数 | 1〜10(クライアント工務店の店舗。まず北野工作所 1店舗) |
| 用途(英語で聞かれたとき) | We manage Google Business Profiles on behalf of our small-business clients (local remodeling contractors in Japan). We will use the API to publish the same update posts (text + photo + "Learn more" button) that we post to Instagram, 1-3 times per day per location, from our own automated tool (GitHub Actions). No reselling, no third-party access. |
| 用途(日本語) | クライアント(地域のリフォーム工務店)のビジネスプロフィールを代理で運用しています。Instagram に投稿している最新情報(文章+写真+詳細ボタン)を、自社の自動投稿ツールから同じ内容で1日1〜3本投稿するために API を使います。 |

- 申請者の Google アカウント(fujimori@jibulabo.jp)が、対象のビジネスプロフィールの**オーナーまたは管理者**になっている必要がある
- 承認メールが来るまで数日〜数週間。来たら `python3 gbp_post.py --check` でつながるか確認


**2026-10-29 申請送信済み。ケース ID 2-6320000041922(審査 7〜10 営業日=11月中旬ごろ)。同じプロジェクトで再申請しないこと。**

**2026-10-30 却下**: 「申請のウェブサイトURLがビジネスプロフィールに表示されているURLと完全一致しない」(jibulabo.jp を書いたため)。
→ 2026-10-31 再申請: 会社名=株式会社北野工作所、ウェブサイト=北野のプロフィールに表示されているURLをそのままコピー(サイト本体は https://www.kashiba-yanereform.com/ へ転送される)。他の項目は上の表と同じ。
**再申請送信済み: ケース ID 6-2797000042251(2026-10-31)。同じプロジェクトで重ねて申請しないこと。結果メールは迷惑メールフォルダに入ることがある。**

### 3. 北野工作所のプロフィールに権限があるか確認
https://business.google.com/ → 北野工作所 → ビジネス プロフィールの設定 → ユーザーとアクセス権
に **fujimori@jibulabo.jp** が「オーナー」または「管理者」で入っていること。無ければ北野さん側で追加してもらう。

### 4. 投稿先を記録して試し投稿
```
cd ~/kitano-ig-post
python3 gbp_post.py --check            # 見える店舗一覧(承認後)
python3 gbp_post.py --setup 北野        # state.json に投稿先を記録 → git commit/push
python3 gbp_post.py --test 17_komari_bankin   # 送る内容を見るだけ
python3 gbp_post.py --one  17_komari_bankin   # 1本だけ今すぐ投稿(投稿後 state.json を push)
```
**テストはこの1本だけ(ユーザー指示 2026-10-27)。** 毎回の自動投稿は state.json の `"gbp_auto": true` を入れて push するまで動かない
(ユーザーがテスト投稿を見て OK を出してから `python3 gbp_post.py --auto on`)。止めるときは `--auto off`。

## 困ったとき
- RESULT に「⚠ マイビジネス投稿に失敗: HTTP 403/429 … quota」→ API がまだ未承認(または有効化されていない)。Instagram は正常
- 「写真の公開URLがまだ見えません」→ gbp_img/ の push が遅れただけ。次回は通る。`gbp_post.py --one slug` で出し直せる
- 承認後もすべて止めたいとき → GitHub Secrets の GBP_REFRESH_TOKEN を削除(Instagram・ドライブ保存はそのまま)
- API では「サービス」タイプの投稿は作れない(最新情報・イベント・特典のみ)。今は最新情報だけ使用
