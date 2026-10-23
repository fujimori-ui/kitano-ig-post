#!/usr/bin/env python3
"""北野工作所 Instagram 投稿画像(1080x1350)を一括生成。
サイト(kashiba-yanereform.com)の掲載内容を素材にしている。
出力: posts/NN_slug.jpg + posts/NN_slug.txt(本文)
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import textwrap

HERE = Path(__file__).parent
OUT = HERE / "posts"; OUT.mkdir(exist_ok=True)
HD = HERE / "photos_hd"
W, H = 1080, 1350
BLUE = (3, 110, 184)       # ロゴ・サイトの青 #036eb8
SKY = (0, 167, 227)        # サイトの水色 #00a7e3
LIGHT = (219, 247, 254)    # #dbf7fe
YELLOW = (255, 224, 51)    # #ffe033
INK = (35, 24, 21)         # ロゴの黒 #231815
GRAY = (107, 114, 128)
WHITE = (255, 255, 255)
FB = "/mnt/c/Windows/Fonts/YuGothB.ttc"   # サイトと同じ游ゴシック(太字)
FR = "/mnt/c/Windows/Fonts/YuGothM.ttc"   # 游ゴシック(中字)
LOGO = Image.open(HERE / "logo_color.png").convert("RGBA")

def font(size, bold=True):
    return ImageFont.truetype(FB if bold else FR, size)

def wrap(text, f, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if f.getlength(cur + ch) > maxw and cur:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines

def draw_text(d, xy, text, f, fill, maxw=None, spacing=1.35, align="left"):
    x, y = xy
    lines = wrap(text, f, maxw) if maxw else text.split("\n")
    lh = int(f.size * spacing)
    for ln in lines:
        if align == "center":
            tx = x - f.getlength(ln) / 2
        elif align == "right":
            tx = x - f.getlength(ln)
        else:
            tx = x
        d.text((tx, y), ln, font=f, fill=fill)
        y += lh
    return y

def cover(img, w, h, focus=0.5):
    """w×hに切り抜き(中央寄せ、focusで縦位置)"""
    iw, ih = img.size
    s = max(w / iw, h / ih)
    img = img.resize((int(iw * s) + 1, int(ih * s) + 1), Image.LANCZOS)
    iw, ih = img.size
    left = (iw - w) // 2; top = int((ih - h) * focus)
    return img.crop((left, top, left + w, top + h))

def rounded(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)

def base(subtitle="香芝市の屋根・雨漏り修理"):
    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    # ヘッダー: ロゴ
    lg = LOGO.copy(); lh = 64; lg = lg.resize((int(lg.width * lh / lg.height), lh), Image.LANCZOS)
    im.paste(lg, (48, 38), lg)
    f = font(26)
    d.text((W - 48 - f.getlength(subtitle), 56), subtitle, font=f, fill=BLUE)
    d.rectangle([0, 138, W, 146], fill=BLUE)
    # フッター
    d.rectangle([0, 1230, W, H], fill=BLUE)
    f1 = font(34); t1 = "点検・お見積り 無料　☎ 0745-76-4335"
    d.text(((W - f1.getlength(t1)) / 2, 1252), t1, font=f1, fill=WHITE)
    f2 = font(23, False); t2 = "対応エリア 香芝市・大和高田市・橿原市・葛城市・広陵町・王寺町・上牧町・河合町"
    d.text(((W - f2.getlength(t2)) / 2, 1300), t2, font=f2, fill=LIGHT)
    return im, d

def title_block(d, title, y=172, size=54, maxw=984):
    f = font(size)
    return draw_text(d, (48, y), title, f, INK, maxw=maxw, spacing=1.3)

def tag(im, d, xy, text, bg, fg):
    f = font(30)
    tw = f.getlength(text) + 44
    x, y = xy
    rounded(d, [x, y, x + tw, y + 54], 12, bg)
    d.text((x + 22, y + 9), text, font=f, fill=fg)

def photo_pair(im, d, before, after, y0=300, ph=430, gap=20):
    for i, (p, label, bg, fg) in enumerate([(before, "Before", GRAY, WHITE), (after, "After", YELLOW, INK)]):
        y = y0 + i * (ph + gap)
        ph_img = cover(Image.open(p).convert("RGB"), 984, ph)
        im.paste(ph_img, (48, y))
        d.rounded_rectangle([48, y, 48 + 984, y + ph], radius=0, outline=(225, 225, 225), width=2)
        tag(im, d, (64, y + 16), label, bg, fg)

def band_note(d, text, y=1160, bg=LIGHT, fg=BLUE):
    f = font(32)
    rounded(d, [48, y, W - 48, y + 60], 14, bg)
    d.text(((W - f.getlength(text)) / 2, y + 11), text, font=f, fill=fg)

def save(im, n, slug, caption):
    im.save(OUT / f"{n:02d}_{slug}.jpg", quality=92)
    (OUT / f"{n:02d}_{slug}.txt").write_text(caption.strip() + "\n\n" + TAGS, encoding="utf-8")
    print("saved", n, slug)

TAGS = "#北野工作所 #香芝市 #香芝 #奈良県 #橿原市 #大和高田市 #広陵町 #王寺町 #屋根工事 #屋根修理 #雨漏り修理 #雨漏り #屋根リフォーム #瓦屋根 #瓦修理 #棟板金 #雨樋交換 #カバー工法 #葺き替え #板金工事 #葛城市 #上牧町 #河合町 #五位堂 #香芝市屋根修理 #香芝市雨漏り #まちの屋根屋さん #創業大正9年"
CTA = """

────────────
お問い合わせはお気軽に
株式会社北野工作所(奈良県香芝市五位堂)
☎ 0745-76-4335(8:00〜18:00)
現地調査・お見積りは無料です
香芝市・大和高田市・橿原市・葛城市・広陵町・王寺町・上牧町・河合町 すぐ伺います
LINE・ホームページはプロフィールのリンクから
────────────"""
# ---------- 1 代表あいさつ ----------
def post01():
    im, d = base()
    person = Image.open(HERE / "person_cut.png").convert("RGBA")
    ph = 680; person = person.resize((ph, ph), Image.LANCZOS)
    # 背景の水色の丸
    d.ellipse([W / 2 - 300, 300, W / 2 + 300, 900], fill=LIGHT)
    im.paste(person, (int(W / 2 - ph / 2), 270), person)
    f = font(58)
    draw_text(d, (W / 2, 180), "はじめまして。", f, INK, align="center")
    f2 = font(44)
    draw_text(d, (W / 2, 985), "香芝の屋根屋、北野です", f2, BLUE, align="center")
    band_note(d, "創業106年・瓦1枚の修理から葺き替えまで", y=1120)
    cap = """はじめまして。奈良県香芝市で屋根の仕事をしている、北野工作所の北野完です。

大正9年(1920年)に創業して106年。瓦1枚の補修、雨漏り、雨どい、葺き替えまで、お家の「上のほう」のことなら何でもやっています。

このアカウントでは、工事の様子と、知っておくと得する屋根の話を投稿していきます。「こんなことで頼んでいいのかな？」という小さな工事こそ、大切にしています。""" + CTA
    save(im, 1, "greeting", cap)

# ---------- 2 数字で見る ----------
def post02():
    im, d = base()
    title_block(d, "数字で見る、北野工作所")
    boxes = [("1920", "年 創業(大正9年)", "香芝で106年"),
             ("3,000", "件以上", "解決した雨漏り"),
             ("57", "件", "先月のお問い合わせ"),
             ("0", "円", "点検・診断・お見積り")]
    bw, bh = 470, 360
    for i, (num, unit, label) in enumerate(boxes):
        x = 48 + (i % 2) * (bw + 44); y = 300 + (i // 2) * (bh + 40)
        rounded(d, [x, y, x + bw, y + bh], 24, LIGHT)
        d.rectangle([x, y, x + bw, y + 10], fill=BLUE)
        f = font(110); fu = font(34); fl = font(32, False)
        nw = f.getlength(num); uw = fu.getlength(unit)
        sx = x + (bw - nw - uw - 8) / 2
        d.text((sx, y + 70), num, font=f, fill=BLUE)
        d.text((sx + nw + 8, y + 140), unit, font=fu, fill=INK)
        d.text((x + (bw - fl.getlength(label)) / 2, y + 250), label, font=fl, fill=INK)
    band_note(d, "地元・香芝市で、顔の見える屋根屋です", y=1130)
    cap = """北野工作所を数字でご紹介します。

▶ 1920年(大正9年)創業。香芝市・五位堂で106年、同じ場所で屋根を直してきました。
▶ 解決した雨漏りは3,000件以上。
▶ 先月のお問い合わせは57件。雨漏り修理が一番多く、次いで波板の張替え、瓦の補修です。
▶ 現地点検・診断・お見積りは0円。

長く続いた理由はひとつ。直した屋根のそばに、ずっと住んでいるからです。手を抜けば、すぐ分かる町です。""" + CTA
    save(im, 2, "numbers", cap)

# ---------- ビフォーアフター共通 ----------
def ba_post(n, slug, title, before, after, note, cap):
    im, d = base()
    title_block(d, title, size=50)
    photo_pair(im, d, HD / before, HD / after, y0=290, ph=410)
    band_note(d, note, y=1150)
    save(im, n, slug, cap)

def post03():
    ba_post(3, "kawara", "瓦1枚のズレ・割れ、放っておくと雨漏りに",
            "works_post-85_0.png", "works_post-85_1.png",
            "小さいうちに直すのが、いちばん安い",
            """「屋根の瓦がずれている気がする」とご相談をいただき、さっそく点検へ。

隅(すみ)の瓦が大きくズレて、一部は割れていました。このままだと隙間から雨水が入り、屋根の内部(下地)を傷めて雨漏りの原因になります。

ズレを直し、割れた瓦は新しいものに交換。しっかり固定して、見た目も元通りです。

「瓦1枚くらいで頼んでいいのかな」とよく言われます。いいんです。屋根のトラブルは、小さいうちに直すのがいちばん安く、お家を長持ちさせるコツです。(香芝市)""" + CTA)

def post04():
    ba_post(4, "mune_tsumi", "屋根のてっぺん「棟」の積み直し工事",
            "works_post-85-4-2-2-2-2_0.png", "works_post-85-4-2-2-2-2_1.png",
            "台風シーズン前の点検がおすすめです",
            """今回は、棟(むね)の積み直し工事です。

棟とは、屋根のいちばん高いところ。屋根面と屋根面が交わる部分で、雨水の侵入を防ぎ、屋根全体を守る大事な場所です。

長年の雨風や台風で、棟の漆喰(しっくい)が傷んだり、ズレたり、割れたりします。放っておくと雨漏りや瓦のズレにつながります。

今回は屋根土をすべて撤去し、傷んだ瓦は交換、傷んでいない瓦は再利用して積み直しました。見た目もきれいになり、耐久性・防水性も安心です。

梅雨前・台風前は屋根点検のご依頼が増える時期。普段見えない場所だからこそ、定期的なチェックをおすすめします。(香芝市)""" + CTA)

def post05():
    ba_post(5, "hisashi", "サビだらけの庇(ひさし)が、見違えました",
            "works_post-85-4-2_0.png", "works_post-85-4-2_1.png",
            "ご予算に合わせたご提案ができます",
            """「最近、庇が古くなってきて心配で…」とご相談をいただきました。

見てみると、サビや傷みが多く、内部の下地も傷んでいる可能性が高い状態。庇は、窓や玄関を雨から守る大事な部分です。小さくても、外壁や建物全体の耐久性に関わります。

今回は「できるだけ予算は抑えたい」とのご要望だったので、お客様としっかり打ち合わせをして内容を調整しました。

仕上がりはスッキリきれいに。「見違えるようになったね」と喜んでいただけました。

庇はつい後回しにされがちですが、気づいたときがメンテナンスのタイミングです。(香芝市)""" + CTA)

def post06():
    ba_post(6, "namiita", "テラス屋根の波板交換で、お庭が明るく",
            "works_post-85-2_0.png", "works_post-85-2_1.png",
            "波板1枚からでも、喜んで伺います",
            """「テラス屋根が汚れていて、部屋の中まで暗く感じる」「風の強い日にバタバタ音がして心配」

そんなご相談でした。長年の紫外線と雨風で波板が変色し、コケや汚れもびっしり。こうなると光を通しにくくなるだけでなく、素材がパリパリに硬くなって、強風で割れやすくなります。

古い波板をすべて外し、下地を掃除してから、新しいポリカーボネート製の波板に張り替えました。

「お庭が明るくなったし、これで洗濯物も安心して干せるわ」と喜んでいただけました。

テラス・ベランダ・カーポートの波板交換、「1枚だけ剥がれそう」「フックが外れて音がうるさい」も、お気軽にどうぞ。(香芝市)""" + CTA)

def post07():
    ba_post(7, "mune_bankin", "棟板金の交換。見えない下地まで新しく",
            "works_post-85-4-2-2_0.png", "works_post-85-4-2-2_1.png",
            "突風で棟が飛ぶ前に、早めのメンテナンスを",
            """今回は、棟板金(むねばんきん)の交換工事です。

全体的に経年劣化が進み、表面の色あせや細かな傷みが出ていました。このまま年数が経つと防水性が下がり、雨漏りや、突風で棟が飛んでしまうトラブルにつながります。

まず既存の棟板金を外して内部を確認。木下地を整え、新しく防水紙を施工してから、新しい棟板金を取り付けました。

見える部分だけでなく、見えなくなる木下地や防水処理まで丁寧に施工することで、屋根全体の耐久性が上がります。

棟は普段見えにくい場所。気づいたときには劣化が進んでいることも少なくありません。「うちは大丈夫かな？」と気になったら、点検だけでもお気軽に。(香芝市)""" + CTA)

def post08():
    ba_post(8, "parapet", "屋根・パラペット・かさ木の交換工事",
            "works_post-85-4_0.png", "works_post-85-4_1.png",
            "見えないところまで、しっかりチェックします",
            """屋根(立平)、パラペット、かさ木の交換工事をさせていただきました。

屋根はカラーベスト(スレート瓦)で、年数が経ち、細かいひび・割れが見られる状態。屋根まわりのパラペット(外壁が立ち上がっている部分)と、その上の「かさ木」も傷んでいました。

かさ木とは、パラペットのいちばん上にかぶせてある板金のこと。雨水が内部に入らないようにするフタの役割です。ここが傷むと、見えないところから水が入り、雨漏りや内部の腐食につながります。

古いかさ木を外すと、やはり内部には水が回った跡が。下地をしっかり補修してから新しいかさ木を取り付け、屋根も新しい立平に。見た目もスッキリ、安心して過ごしていただける状態になりました。(香芝市)""" + CTA)

# ---------- 9 雨漏りのサイン ----------
def post09():
    im, d = base()
    title_block(d, "天井に染みができたら、もう遅い？", size=50)
    ph = cover(Image.open(HD / "news_post-81-3-2-2-2-2-2-2-2-2_0.png").convert("RGB"), 984, 420)
    im.paste(ph, (48, 280))
    f = font(36); y = 730
    d.text((48, y), "こんな症状が出たら、すぐご相談ください", font=f, fill=BLUE); y += 70
    items = ["天井の染みや変色", "壁紙のふくらみ・剥がれ", "雨の日だけ「ポタポタ」音がする", "押し入れや収納がじめじめする"]
    fi = font(38)
    for it in items:
        d.ellipse([56, y + 10, 56 + 30, y + 40], fill=YELLOW)
        d.text((110, y), it, font=fi, fill=INK); y += 70
    band_note(d, "築10年を超えたら、無料点検をどうぞ", y=1150)
    cap = """天井に雨漏りの染みが出た、ということは、すでに屋根や防水層にかなりのダメージがたまっているサインです。

最初の一滴が天井に届くまでに、水は屋根材・断熱材・構造材と、いくつもの層を通り抜けています。そして一度できた染みは、クロスを張り替えても、内部の木材に染み込んだ水分やカビは残ります。

こんな症状が出たら、すぐご相談ください。
○ 天井の染みや変色
○ 壁紙のふくらみや剥がれ
○ 雨の日だけ「ポタポタ」音がする
○ 押し入れや収納がじめじめする

築25〜30年の家は、屋根材や防水シートの寿命が来るタイミング。近年の集中豪雨や台風で、隠れていた劣化が一気に表に出ることも増えています。

雨の後に天井・壁を見る習慣をつける。築10年を超えたら定期的に屋根点検(無料)。染みを見つけたら、まず原因の特定を優先する。これが早期対策のポイントです。""" + CTA
    save(im, 9, "amamori_sign", cap)

# ---------- 10 料金の目安 ----------
def post10():
    im, d = base()
    title_block(d, "「これくらいで頼んでいいの？」\n小さな工事の料金目安", size=48)
    rows = [("雨どい掃除・つまり直し", "3,000円〜"), ("雨どい金具のゆるみ直し", "3,000円〜"),
            ("屋根のコーキング補修(隙間埋め)", "3,000円〜"), ("トタン屋根の釘・ビス打ち直し", "5,000円〜"),
            ("棟板金の釘浮き補修", "5,000円〜"), ("波板1枚の交換(ベランダ・物置)", "6,000円〜"),
            ("雨漏り点検・診断", "0円(無料)")]
    y = 340; fl = font(34, False); fp = font(38)
    for i, (k, v) in enumerate(rows):
        bg = LIGHT if i % 2 == 0 else WHITE
        d.rectangle([48, y, W - 48, y + 92], fill=bg)
        d.text((72, y + 26), k, font=fl, fill=INK)
        d.text((W - 72 - fp.getlength(v), y + 22), v, font=fp, fill=BLUE)
        y += 92
    f = font(26, False)
    d.text((48, y + 20), "※税抜。現地確認後に正確なお見積りをお出しします", font=f, fill=GRAY)
    band_note(d, "小さな工事こそ、遠慮なくご相談ください", y=1150)
    cap = """「こんな小さなことで頼んでいいのかな？」という内容でも、遠慮なくご相談ください。

小さな補修工事の目安(税抜)
・雨どい掃除・つまり直し 3,000円〜
・雨どい金具のゆるみ直し 3,000円〜
・屋根のコーキング補修(隙間埋め) 3,000円〜
・トタン屋根の釘・ビス打ち直し 5,000円〜
・棟板金の釘浮き補修 5,000円〜
・波板1枚の交換(ベランダ・物置など) 6,000円〜
・雨漏り点検・診断 0円(無料)

必要なところだけ直すことで、費用を抑えられるケースも多くあります。正確な費用は、現地で確認してからお見積りします。

屋根全体の工事(カバー工法・葺き替え・塗装)の目安は、ホームページの「工事目安金額」に載せています。""" + CTA
    save(im, 10, "price", cap)

# ---------- 11 流れ ----------
def post11():
    im, d = base()
    title_block(d, "ご相談から工事までの流れ", size=54)
    steps = [("お問い合わせ", "電話・LINE・フォームから。\n「雨どいが壊れた」など簡単な内容でOK"),
             ("無料点検・診断", "現地で屋根・雨どいの状態を丁寧に点検。\n屋根の上の写真をお見せします"),
             ("お見積り・ご説明", "最適な直し方と費用を分かりやすく説明。\n後から追加費用が出ないようにします"),
             ("ご契約・工事", "ご納得いただいてから。日程はご都合に合わせて。\n工事後の点検・ご相談も無料です")]
    y = 300; fn = font(64); ft = font(40); fd = font(29, False)
    for i, (t, desc) in enumerate(steps):
        d.ellipse([48, y, 48 + 110, y + 110], fill=BLUE)
        n = str(i + 1); d.text((48 + 55 - fn.getlength(n) / 2, y + 16), n, font=fn, fill=WHITE)
        d.text((190, y - 2), t, font=ft, fill=BLUE)
        draw_text(d, (190, y + 52), desc, fd, INK, maxw=840, spacing=1.4)
        y += 200
    band_note(d, "「見てもらっただけで断りづらい」はありません", y=1150)
    cap = """ご相談から工事までの流れをご紹介します。

① お問い合わせ
お電話・LINE・お問い合わせフォームから。「雨どいが壊れた」「雨漏りしている」など、簡単な内容で大丈夫です。

② 無料点検・診断
現地へ伺い、屋根・雨どいの状態を丁寧に点検します。点検・診断はすべて無料です。

③ お見積り・ご説明
点検結果をもとに、最適な修理方法と費用をご説明します。後から追加費用が発生しないよう、事前に分かりやすくお伝えします。

④ ご契約・工事・アフターサポート
内容にご納得いただけたらご契約。日程はご都合に合わせて調整します。経験豊富な職人が安全第一で施工し、工事後の点検やご相談にも対応します。

50万円以上の工事は、工事開始時50%・完了時50%の二分割払いにも対応しています。

「見てもらっただけで断りづらい」はありません。見積りだけでも大丈夫です。""" + CTA
    save(im, 11, "flow", cap)

# ---------- 12 お客様の声 ----------
def post12():
    im, d = base()
    title_block(d, "お客様からいただいた言葉", size=54)
    quotes = ["職人さんはテキパキと動かれ、見ていて気持ち良かったです。仕事も丁寧で、仕上がりは納得できるものでした。また頼むなら北野工作所にお願いすると思います。",
              "北野社長はとにかく話しやすく、雨漏りや板金工事など、お家の悩みなら何でもフラットに相談に乗ってくれます。",
              "良心的な工事費で、丁寧な仕事。短期間で工事が終了しました。すごく良かったです。"]
    y = 290; fq = font(34, False); fm = font(70)
    for q in quotes:
        lines = wrap(q, fq, 900); bh = len(lines) * 50 + 64
        rounded(d, [48, y, W - 48, y + bh], 20, LIGHT)
        d.text((70, y - 6), "“", font=fm, fill=BLUE)
        draw_text(d, (90, y + 30), q, fq, INK, maxw=900, spacing=1.47)
        y += bh + 26
    f = font(26, False)
    d.text((W - 48 - f.getlength("Googleの口コミより(一部抜粋)"), y + 4), "Googleの口コミより(一部抜粋)", font=f, fill=GRAY)
    band_note(d, "これからも、話しやすい屋根屋でいます", y=1150)
    cap = """Googleの口コミにいただいた言葉を、一部ご紹介します。

「職人さんはテキパキと動かれ、見ていて気持ち良かったです。仕事も丁寧で、仕上がりは納得できるものでした。また頼むとすれば北野工作所にお願いすると思います」

「北野社長はとにかく話しやすく、雨漏りや板金工事など、お家の悩みなら何でもフラットに相談に乗ってくれます。現場を支える職人チームの結束力が抜群」

「良心的な工事費で、丁寧な仕事。短期間で工事が終了しました。すごく良かったです」

ありがたいです。これからも、話しやすい屋根屋でいます。

口コミはプロフィールのリンク「Googleの口コミを見る」から読めます。""" + CTA
    save(im, 12, "voice", cap)

# ---------- 13 雨の日は樋点検 ----------
def post13():
    im, d = base()
    title_block(d, "雨の日はチャンス。雨どいを見てみて", size=50)
    ph = cover(Image.open(HD / "news_post-81-3-2-2-2-2-2-2-2-2_4.png").convert("RGB"), 984, 420)
    im.paste(ph, (48, 280))
    y = 730; f = font(36)
    d.text((48, y), "こんな様子は、詰まりや破損のサインです", font=f, fill=BLUE); y += 70
    fi = font(38)
    for it in ["雨どいから水があふれている", "ポタポタと水が垂れている", "一部分だけ水の流れが悪い", "外壁に水が伝っている"]:
        d.ellipse([56, y + 10, 56 + 30, y + 40], fill=YELLOW)
        d.text((110, y), it, font=fi, fill=INK); y += 70
    band_note(d, "ご自身で登らず、プロにお任せください", y=1150)
    cap = """雨の日は、雨どい(樋)の状態をチェックする絶好のタイミングです。普段は気づきにくい不具合が、雨が降ると分かりやすくなります。

こんな様子はありませんか？
・雨どいから水があふれている
・ポタポタと水が垂れている
・一部分だけ水の流れが悪い
・外壁に水が伝っている

これらは、詰まりや破損のサインです。そのままにしておくと、外壁の汚れや劣化、雨漏り、基礎の傷みなど、建物全体に影響が出ることもあります。

先日の現場では、下から見ると何の問題もなさそうな雨どいの中に、落ち葉や土がぎっしり。「こんなに詰まっているとは思わなかった」と驚かれていましたが、実はこういうケース、けっこう多いんです。

気になったら、無理にご自身で登らず、ぜひプロにお任せください。安全にしっかり点検・清掃します。""" + CTA
    save(im, 13, "amadoi", cap)

# ---------- 14 対応エリア ----------
def post14():
    im, d = base()
    title_block(d, "香芝市と、そのまわり。\nすぐ伺います", size=54)
    truck = Image.open("/mnt/c/Users/藤森　保弘/Desktop/北野工作所/インスタ/track.png").convert("RGBA")
    tw = 660; truck = truck.resize((tw, int(truck.height * tw / truck.width)), Image.LANCZOS)
    im.paste(truck, (int((W - tw) / 2), 330), truck)
    y = 330 + truck.height + 30
    f = font(34); d.text((W / 2 - f.getlength("対応エリア") / 2, y), "対応エリア", font=f, fill=BLUE); y += 60
    areas = ["香芝市", "大和高田市", "橿原市", "葛城市", "広陵町", "王寺町", "上牧町", "河合町"]
    fa = font(36); bw, bh, gap = 220, 70, 16
    for i, a in enumerate(areas):
        x = 48 + 8 + (i % 4) * (bw + gap); yy = y + (i // 4) * (bh + gap)
        rounded(d, [x, yy, x + bw, yy + bh], 14, LIGHT)
        d.text((x + (bw - fa.getlength(a)) / 2, yy + 14), a, font=fa, fill=INK)
    band_note(d, "近鉄五位堂駅から西へ300m。地元の屋根屋です", y=1150)
    cap = """北野工作所の事務所は、近鉄五位堂駅から西へ300m(徒歩5分)。香芝市五位堂で106年、屋根の仕事をしています。

対応エリアは、香芝市と、そのまわりの町です。
・香芝市
・大和高田市
・橿原市
・葛城市
・広陵町
・王寺町
・上牧町
・河合町

近いので、「ちょっと見てほしい」にすぐ動けます。雨漏りの応急処置、瓦1枚の補修、雨どいの掃除。大きな工事でなくても大丈夫です。

同じ地域に住んでいる屋根屋だからこそ、直したあとも、ずっとお付き合いできます。""" + CTA
    save(im, 14, "area", cap)

if __name__ == "__main__":
    for fn in [post01, post02, post03, post04, post05, post06, post07, post08, post09, post10, post11, post12, post13, post14]:
        fn()
