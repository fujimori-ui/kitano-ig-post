# 北野工作所IG 週次の自動ネタ作り(ルーティン用の手順書)

毎週月曜5:00に claude.ai のルーティンがこの手順で「来週分の投稿21本(1日3本×7日)」を作ります。
作るのは **中身(JSON)だけ**。画像・動画は GitHub Actions(build.yml)が作ります。

## 依頼主と目的
- 株式会社北野工作所(奈良県香芝市五位堂2-580-1、屋根・雨漏り修理、代表 北野完、大正9年創業・2026年2月法人化)
- Instagram @kashiba_yanereform。地元の人に「ここに頼めば安心」と思ってもらうための投稿
- 投稿の種類が偏らないように(施工事例ばかりにしない)。豆知識・訪問販売の注意・会社紹介・季節の話をまんべんなく

## 手順(この順番で。手順に無いことはしない)
1. 在庫とこれまでのタイトルを見る
   ```
   python3 build_auto.py --stock
   python3 build_auto.py --titles
   ls content/
   ```
   すでにあるタイトルと同じ話題は作らない(言い回しを変えただけもNG)。
2. 事実の確認に使う資料: `posts/*.txt`(会社の情報・料金・流れ・資格は必ずここから取る。サイト https://www.kashiba-yanereform.com/ も可)。**資料に無い事実(受賞歴、施工件数、補助金、人数など)は書かない。**
3. 訪問販売の注意・時事ネタは WebSearch で一次情報(国民生活センター、消費者庁、各地の消費生活センター、自治体)を探す。数字を使うときは出典を `source` に書く(例「出典: 国民生活センター(2026年9月)」)。確認できない数字は使わない。
4. `content/auto_YYYYMMDD.json`(今日の日付)に21本を書く(形式は下)。種類の目安:
   - `mame_`(屋根の豆知識) 7本
   - `chuui_`(訪問販売・点検商法の注意、時事ニュース) 5本
   - `company_` / `faq_`(会社紹介・よくある質問・料金・流れ) 4本
   - `season_`(季節の屋根の話: 台風前・冬前・年末・春の強風・梅雨前など、作る時期に合わせる) 3本
   - `komari_`(こんなお困りごとありませんか？ 写真レイアウト) 2本
   レイアウトも混ぜる: list を中心に、photo 5本以上、steps 2本以上、table 1〜2本、quotes 0〜1本。
   **全部の投稿に写真(`photo`)を入れる**(文字だけの投稿にしない。ユーザー指示)。話題に合う写真を下の一覧から選び、同じ写真が続かないようにする。
5. 形式チェック(NGが出たら直して再実行):
   ```
   python3 build_auto.py --check content/auto_YYYYMMDD.json
   ```
6. push:
   ```
   git add content/auto_YYYYMMDD.json && git commit -m "来週分の投稿21本(自動生成)" && git push
   ```
   push できないときは `gh api -X PUT repos/fujimori-ui/kitano-ig-post/contents/content/auto_YYYYMMDD.json -f message="来週分の投稿21本" -f content="$(base64 -w0 content/auto_YYYYMMDD.json)"`
7. 画像・動画は push をきっかけに build.yml が自動で動く(15〜20分)。**自分で `gh workflow run` はしない**(二重に動く)。
   **待ち方の注意: バックグラウンド実行(run_in_background)や Monitor は使わない。使うとセッションが先に終わり、メールが送られない。** 次のコマンドを前面で実行して待つ(timeout は 25分=1500000ms に設定):
   ```
   sleep 60; RID=$(gh run list -R fujimori-ui/kitano-ig-post --workflow=build.yml --limit 1 --json databaseId -q '.[0].databaseId'); echo $RID
   gh run watch $RID -R fujimori-ui/kitano-ig-post --exit-status > /dev/null 2>&1; gh run view $RID -R fujimori-ui/kitano-ig-post --log 2>/dev/null | grep -o "RESULT:.*\|PREVIEW.*\|NG.*" | head -5
   ```
   60秒待っても今回の push より新しい run が無ければ、そのときだけ `gh workflow run build.yml -R fujimori-ui/kitano-ig-post --ref main` で起動する。
   (この環境では WebFetch・curl で外部サイトは開けない。調べものは WebSearch だけで行う。`pip install` が必要なら `python3 -m pip install --break-system-packages requests`)
8. Gmail で fujimori@jibulabo.jp へ1通。件名「【北野IG】来週分21本を作りました」(失敗なら「【北野IG】来週分の作成に失敗(要確認)」)。本文はやさしい日本語で短く:
   - 作った21本のタイトル一覧(種類つき)
   - 確認用の一覧画像: `https://raw.githubusercontent.com/fujimori-ui/kitano-ig-post/main/<PREVIEW行のパス>`
   - 在庫(`python3 build_auto.py --stock` の結果)
   - 直したいときは「この投稿を直して/外して」と返事すればよいこと
   - 失敗時はエラー文と https://github.com/fujimori-ui/kitano-ig-post/actions

## JSON の形式
一番外側は配列。1本=1オブジェクト。`n`(番号)は書かない(Actions が付ける)。CTA(連絡先)とハッシュタグは自動で付くので本文に書かない。

共通項目:
- `photo`: 下の一覧のファイル名(**必須**。quotes だけ省略可)。`focus`(任意0〜1): 写真の縦位置(0=上寄り)。`"a.jpg@0.3+b.jpg@0.2"` のように `+` でつなぐと2〜3枚を横に並べられる(`@` のあとは各写真の縦位置。訪問販売・相談の話題は人物写真を2〜3枚並べると伝わりやすい)
- **画像の文字は少なめ・大きめ**(ユーザー指示 2026-10-30)。画像に載るのは見出しと**説明の最初の1文だけ**(2文目以降は画像に出ない)。説明の1文目だけで意味が通るように短く書き、くわしい話は `cap`(本文)に書く
- `slug`: 英小文字・数字・_。先頭は種類 `mame_` `chuui_` `company_` `faq_` `season_` `komari_`(例 `mame_koke_hanashi`)。既存と重複不可
- `layout`: `list` / `steps` / `table` / `photo` / `quotes`
- `title`: 画像の大見出し。黄色いマーカー帯に乗る。**1行14文字(list) / 16文字(他)まで、`\n`で2行まで**。疑問形や「〜5つ」など、目を止める言い方
- `note`: 画像の下の帯の一言(28文字まで。例「迷ったら、地元の屋根屋にご相談を」)
- `cap`: Instagram本文(150〜900文字)。1行目=タイトル＋絵文字1つ → 空行 → 導入1〜2文 → ①②③…の見出し＋説明 → 空行 → 北野工作所としての一言(「〜だけでもお伺いします」「写真をお見せして説明します」など)。絵文字は全体で2〜4個。やさしい日本語、専門用語には読み仮名か説明を付ける
- `source`(任意): 出典を短く(list のみ表示)

レイアウト別:
- `list`: 写真の帯＋番号付き箇条書き。`pill`(左上ラベル14文字まで。例「屋根の豆知識」「訪問販売にご注意」「よくある質問」)、`points`: `[["見出し(22字)", "説明"], …]` **3〜4個**(説明の1文目は3個なら35字・4個なら22字くらいまでが読みやすい。見出しも短く)、`stat`(任意): `["約3.4倍", "10年で相談件数"]`(写真の左下に黄色札)、`note_style`(任意): `"yellow"`/`"blue"`(chuui_ は自動で黄色)
- `steps`: 写真の帯＋`steps`: `[["見出し(14字)", "説明"], …]` 3〜4個(流れ・手順もの。説明は1文目だけ画像に出る。30字くらいまで)
- `table`: 写真の帯＋`rows`: `[["項目(20字)", "値(16字)"], …]` **4〜7行**、`footnote`(任意、例「※税抜。現地確認後に正確なお見積り」)。料金・年数・時期の一覧もの
- `photo`: 大きい写真＋`heading`(写真の下の見出し24字)＋`checks`: 3〜5個(各20字、丸い黄色の点で並ぶ)。komari_ はこれを使う。`labels`(任意): `[["名前(14字)", x, y], …]` で写真の上に部品の名前札を付けられる(x,y は写真内の位置を0〜1で。例「雨どいの部品の名前」「屋根の各部の名前」のような“図解”投稿に)
- `quotes`: `quotes`: 文字列2個(各95字まで)、`credit`(任意)。お客様の声は posts/12_voice.txt にあるものだけ使う(創作しない)。写真は任意

例:
```json
[
 {"slug": "mame_tsuyu_mae", "layout": "list", "pill": "屋根の豆知識",
  "title": "梅雨の前に\n見ておきたい3か所",
  "points": [["雨どいの詰まり", "落ち葉や土で水があふれると、外壁や基礎を傷めます。"],
             ["棟板金の釘浮き", "屋根のてっぺんの金属カバー。強風で飛ぶ前に。"],
             ["天井の小さな染み", "押し入れの奥も見てみてください。"]],
  "note": "地上から見るだけで大丈夫。登らないでください",
  "cap": "梅雨の前に見ておきたい、屋根の3か所☔\n\n雨が長く続く前に、地上から確認できるところだけでも見ておくと安心です。\n\n① 雨どいの詰まり\n…\n\n② 棟板金(むねばんきん)の釘浮き\n…\n\n③ 天井の小さな染み\n…\n\n気になるところがあれば、写真をお見せしながらご説明します。点検だけでもお気軽にどうぞ😊"},
 {"slug": "komari_hisashi", "layout": "photo", "photo": "works_post-85-4-2_0.png",
  "title": "庇(ひさし)、サビていませんか？", "heading": "こんな様子は、交換の目安です",
  "checks": ["赤茶色のサビが出ている", "雨の日にポタポタ音がする", "波打って見える"],
  "note": "庇1か所の交換もお気軽に", "cap": "…"}
]
```

## 使える写真(photos_hd のファイル名と中身)

**顔が切れないように(ユーザー指示 2026-10-31「また起こらないように」)**: 写真の帯は横長(984×200前後)なので、人物写真は顔が帯の端で切れやすい。
画像を作るとき(make_posts.cover)に顔を自動で探して、頭〜あごが帯に入る位置へ自動でずらす。それでも入りきらない(顔のアップ写真など)と
`⚠ 顔が切れています` と出る → その投稿は別の写真に替える。顔が大きく写った写真(`stock_305_worker_consult_elderly.jpg`・`stock_330_worker_consult_desk.jpg`・`stock_576_elderly_woman_phone.jpg`・`stock_312_elderly_woman_smile.jpg` など)は横長の帯に向かない。人物が小さめ・全身寄りの写真を選ぶ。
社長・作業中・トラック(会社紹介・訪問販売注意・FAQ など、現場写真が合わない話題に):
- `work_01_sealing.jpg` 〜 `work_07_caulk.jpg` 社長(ヘルメット・紺の作業着)が屋根の端でコーキング・板金作業をしている(横顔。01 コーキング、02 板金を押さえる、03/04 手元を確認、05/06 屋根の上、07 コーキングガン)
- ~~`pres_office_01.jpg` 〜 `pres_office_07.jpg`~~ **使わない**(縦長の写真なので横長の帯に入れると顔のアップになり見栄えが悪い。ユーザー指示 2026-10-30。社長の写真は右上の丸に自動で入る)
- ~~`pres_outside_01.jpg` 〜 `pres_outside_05.jpg` / `pres_white_01.jpg` / `pres_white_02.jpg`~~ **使わない**(事務所前の写真。背景に土のうが写っていて汚く見える。ユーザー指示 2026-10-26)。社長の顔を出したいときは `work_03_check.jpg`(ヘルメットで横顔)/`work_07_caulk.jpg`(コーキング中の横顔)を使う
イラスト(透明背景。`illust_` で始まるファイルは切り抜かず薄い青の帯の中に収まる。題名に合う写真が無いときに):
- `illust_interphone.png` インターホンで応対する女性(いらすとや。訪問販売・断り方の話題に)
- `illust_voice.png` ひらめいた主婦(エプロン・人差し指。PIXTA購入、お客様の声・豆知識に)
- `truck_01.jpg` 〜 `truck_04.jpg` 北野工作所の白い軽トラック(事務所前。01/02 斜め前、03 横、04 正面寄り)
購入素材(PIXTA。ジブラボ購入済、投稿に使ってよい。`stock_番号_内容.jpg`。足りない場面はここから):
- `stock_door_sales.jpg` 玄関先で営業マンを笑顔で断る女性(47 断り方で使用)
- `stock_voice_sign.jpg` 「お客様の声」の吹き出し看板と人形(12 お客様の声で使用。帯300で)
- `stock_003_tile_roof_worker_eaves.jpg` 瓦屋根の軒先で作業する職人(施工中)
- `stock_005_attic_inspection.jpg` 小屋裏(屋根裏)をライトで点検する職人
- `stock_009_house_blue_tarp.jpg` 足場とメッシュシートで覆われた工事中の家
- `stock_011_roof_worker_plywood.jpg` 屋根の上で下地の合板を張る職人
- `stock_013_metal_roof_sky.jpg` 金属屋根(立平)と青空
- `stock_014_roof_painting_roller.jpg` スレート屋根をローラーで塗装する手元
- `stock_018_roof_workers_two.jpg` 屋根の上で2人の職人が作業(住宅街)
- `stock_024_town_view.jpg` 高台から見た住宅街の遠景(青空)
- `stock_027_ceiling_leak_stain.jpg` 天井にできた雨漏りの染み(古い和室)
- `stock_046_woman_door_greets_worker.jpg` 玄関で作業員を笑顔で迎える女性(相談・訪問の場面)
- `stock_051_roof_worker_tile2.jpg` 瓦屋根の軒先で作業する職人(別角度)
- `stock_080_tile_roof_sunny.jpg` 瓦屋根と青空(日本瓦)
- `stock_110_elderly_couple_smile.jpg` 笑顔のシニア夫婦(白い背景)
- `stock_115_metal_roof_blue.jpg` 金属屋根と木の影(立平)
- `stock_119_house_exterior.jpg` 新しめの戸建て住宅の外観
- `stock_129_worker_gutter_edge.jpg` 雨どいを手で点検しているアップ
- `stock_142_carport_house.jpg` カーポートのある家の外観
- `stock_162_woman_phone_outdoor.jpg` 屋外で電話する女性(ボーダー服)
- `stock_171_staff_explain_elderly.jpg` スタッフがシニア女性に説明している
- `stock_186_calculator_hand.jpg` 電卓を打つ手元(費用・見積り)
- `stock_189_worker_helmet_docs.jpg` ヘルメットの職人が書類を持つ(ビル前)
- `stock_190_house_five_stars.jpg` 青い木の板に家と五つ星(口コミ・評価)
- `stock_202_slate_roof_damaged.jpg` スレート屋根の割れ・ひび(劣化)
- `stock_215_light_truck_street.jpg` 住宅街を走る白い軽トラック
- `stock_251_tablet_writing.jpg` タブレットとペンで書く手元(申込・記録)
- `stock_263_calendar_calc.jpg` カレンダーと電卓(時期・費用)
- `stock_265_worker_point_ceiling.jpg` 天井を指さして点検する職人
- `stock_274_couple_pc_consult.jpg` 男女がノートPCを見ながら打ち合わせ
- `stock_281_wall_paint_roller.jpg` 外壁をローラーで塗装する職人
- `stock_282_old_tile_roof_broken.jpg` 崩れた古い瓦屋根(劣化・放置)
- `stock_283_elderly_man_arms_crossed.jpg` 腕組みして笑うシニア男性(屋外)
- `stock_294_plan_meeting_hands.jpg` 図面を囲んで打ち合わせする手元
- `stock_305_worker_consult_elderly.jpg` 作業服の職人がシニア夫婦に説明(相談の場面)
- `stock_312_elderly_woman_smile.jpg` 笑顔のシニア女性(室内)
- `stock_330_worker_consult_desk.jpg` 作業服の職人が笑顔で相談に応じる
- `stock_337_woman_surprised.jpg` 驚いて両手を上げる女性(ボーダー服。注意・びっくり)
- `stock_406_old_house_overgrown.jpg` 庭が荒れた古い家(空き家)
- `stock_412_ceiling_insulation_damage.jpg` 天井裏の断熱材の劣化・汚れ
- `stock_416_worker_check_shutter.jpg` 雨戸・シャッターを点検する職人
- `stock_444_gutter_rain.jpg` 雨の日の軒先と雨どい(雨が流れる)
- `stock_445_tile_roof_rain.jpg` 雨の日の瓦屋根
- `stock_447_slate_roof_dark.jpg` スレート屋根と青空(全面)
- `stock_455_fire_insurance_doc.jpg` 「火災保険」の案内書類と赤い矢印
- `stock_457_worker_check_floor.jpg` 室内で床をしゃがんで点検する作業員(青い服)
- `stock_499_drone_over_roof.jpg` 屋根の上を飛ぶドローン(点検)
- `stock_551_old_house_garden.jpg` 古い木造の家と庭
- `stock_576_elderly_woman_phone.jpg` 電話で相談するシニア女性
- `stock_583_laptop_videocall.jpg` ノートPCでビデオ通話(オンライン相談)
- `stock_585_worker_write_indoor.jpg` 室内で書き物をする作業員
- `stock_587_blue_house_exterior.jpg` 青い外壁の家と庭(きれいな外観)
- `stock_592_roof_worker_green_sheet.jpg` 屋根で防水シートを張る職人
- `stock_593_house_scaffold_sheet.jpg` 足場・メッシュシートの家(別角度)
- `stock_596_gutter_cleaning_hands.jpg` 雨どいに詰まった落ち葉を手で取り除く
- `stock_611_worker_ladder_wall.jpg` はしごで外壁を作業する職人
- `stock_614_elderly_couple_consult.jpg` シニア夫婦がスタッフに相談(カウンター)
- `stock_615_ladder_indoor.jpg` 室内の脚立(工事中の部屋)
- `stock_627_ceiling_mold_leak.jpg` 天井の木材が腐食・カビ(雨漏りの末路)
現場の写真(屋根・雨どい・染みなど):
- `1776381380801.png` 白い破風板(屋根の端の板)の軒先、瓦屋根。施工前
- `1776695001497.png` / `1776695017435.png` 破風板をガルバリウム鋼板でカバーした後(光る鋼板と青空)
- `DSC_0747.png` 雨どいの集水器の中に泥と落ち葉が詰まっている(上から)
- `DSC_0748.png` 赤茶色の縦どいと足場(外観)
- `news_post-81-3-2-2-2-2-2-2-2-2_0.png` 室内の天井にできた雨漏りの染み(エアコンとカーテン)
- `news_post-81-3-2-2-2-2-2-2-2-2_2.png` 白い破風板の傷み・はがれ(施工前、瓦屋根の軒先)
- `news_post-81-3-2-2-2-2-2-2-2-2_3.png` 破風板ガルバ施工後(別角度、青空)
- `news_post-81-3-2-2-2-2-2-2-2-2_4.png` 雨の日、軒先から落ちる水滴(ぼかし、雰囲気写真。部品は写っていない)
- `news_post-81-3-2-2-2-2-2-2-2_1.png` 茶色の軒どい・集水器・縦どいがはっきり写った写真(雨どいの説明・名前札に最適。集水器は上中央(0.49,0.12)、軒どいは右(0.78,0.60)、縦どいは左下(0.30,0.78))
- `news_post-81-3-2-2-2-2-2-2_3.png` スレート屋根の新しい棟板金(グレー)と色あせたスレート
- `works_post-85-2_0.png` 古い波板のテラス屋根(コケ・汚れ)施工前
- `works_post-85-2_1.png` 新しい茶色のポリカ波板 施工後
- `works_post-85-3_0.png` 瓦屋根の棟(土・漆喰が見える、板金作業中)
- `works_post-85-4-2-2-2-2_0.png` 瓦屋根の棟積み直し中(資材が乗っている)
- `works_post-85-4-2-2-2-2_1.png` 瓦屋根の棟積み直し後(きれいな棟)
- `works_post-85-4-2-2_0.png` スレート屋根の棟板金が赤サビ・劣化(施工前)
- `works_post-85-4-2-2_1.png` 棟板金交換後(新しいグレー)
- `works_post-85-4-2_0.png` 庇(ひさし)のトタンがサビている(施工前)
- `works_post-85-4-2_1.png` 庇の交換後(新しいグレーの板金)
- `works_post-85-4_0.png` 陸屋根・パラペット(古い、職人が作業中)
- `works_post-85-4_1.png` 立平屋根とかさ木の交換後(黒いガルバ)
- `works_post-85_0.png` 瓦のズレ・棟の崩れ(施工前)
- `works_post-85_1.png` 瓦屋根の棟修理後(鬼瓦が見える)

## 書いてはいけないこと
- 資料に無い事実・数字(補助金、施工件数、受賞、人数、年数の断定)
- 他社の名指し批判、「必ず」「絶対」「100%」などの断定、不安を過度にあおる表現
- 医療・法律の断定(クーリング・オフは「条件を満たせば8日以内」の書き方で)
- ハッシュタグ、電話番号、URL(自動で付く)
