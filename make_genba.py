#!/usr/bin/env python3
"""社長から届いた「今日の現場」写真+ひとことを、Instagram 用(1080×1350)の画像と本文にする(2026-11-09〜)。
ブログ(~/kitano_blog/post_blog.py)と同じ写真を、明るさを整えて使う。横長写真はそのまま(切らずに)載せる。

使い方:
  python3 make_genba.py 記事.json
記事.json:
  {"n": 113, "slug": "genba_toi_shuppatsu",
   "pill": "今日の現場", "title": "午後は樋(とい)工事へ出発！",
   "photo": "/mnt/c/Users/.../写真.jpg", "brightness": 1.12, "contrast": 1.06,
   "lead": "写真の下の説明文(2〜3行)",
   "checks": ["☑ こんなサインは点検時期", ...],     # 省略可(3つまで)
   "note": "雨樋の点検・お見積りは無料です",          # 水色の帯
   "cap": "本文(CTA・ハッシュタグは自動で付く)"}
出力: posts/NN_slug.jpg / posts/NN_slug.txt
"""
import json, sys
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import make_posts as M


def photo_fit(path, w, brightness=1.12, contrast=1.06):
    im = Image.open(path).convert("RGB")
    im = ImageEnhance.Brightness(im).enhance(brightness)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    return im.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=3))


def cover_x(im, w, h, focus_x=0.5):
    """w×h に切り抜き。横長写真の左右どこを残すかを focus_x(0=左端, 1=右端)で指定"""
    iw, ih = im.size
    s = max(w / iw, h / ih)
    im = im.resize((int(iw * s) + 1, int(ih * s) + 1), Image.LANCZOS)
    left = int((im.width - w) * focus_x)
    top = (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def build_big(a):
    """写真を大きく・文字少なめ(ユーザー指示 2026-11-09)。写真は左右いっぱい(1080幅)で高さ約900、
    左上に「今日の現場」ピル、写真の下に黄色帯のタイトル1本と水色帯だけ"""
    im, d = M.base()
    top, bottom = 146, 1040
    ph = Image.open(a["photo"]).convert("RGB")
    ph = ImageEnhance.Brightness(ph).enhance(a.get("brightness", 1.12))
    ph = ImageEnhance.Contrast(ph).enhance(a.get("contrast", 1.06))
    ph = cover_x(ph, M.W, bottom - top, a.get("focus_x", 0.5)).filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=3))
    im.paste(ph, (0, top))
    if a.get("pill"):
        M.pill(d, a["pill"], top + 24)
    y = M.title_hl(d, a["title"], bottom + 26, 60, 984)
    M.band_note(d, a["note"], y=1160)
    M.save(im, a["n"], a["slug"], a["cap"] + M.CTA)


def build(a):
    if a.get("layout") == "big":
        return build_big(a)
    im, d = M.base()
    y = 172
    if a.get("pill"):
        M.pill(d, a["pill"], y)
        y += 84
    y = M.title_hl(d, a["title"], y, 58, 984) + 24
    ph = photo_fit(a["photo"], 984, a.get("brightness", 1.12), a.get("contrast", 1.06))
    if ph.height > 560:
        ph = M.cover(ph, 984, 560)
    im.paste(ph, (48, y))
    d.rectangle([48, y, 48 + 984, y + ph.height], outline=(225, 225, 225), width=2)
    y += ph.height + 28
    y = M.draw_text(d, (48, y), a["lead"], M.font(33, False), M.INK, maxw=984, spacing=1.45) + 18
    for c in a.get("checks", [])[:3]:
        c = c.lstrip("☑☐✔✓ ")
        x0, y0, s = 60, y + 3, 34           # 青いチェック印(フォントの☑は×印に見えるため描画で)
        d.rounded_rectangle([x0, y0, x0 + s, y0 + s], radius=7, outline=M.BLUE, width=3, fill=M.WHITE)
        d.line([(x0 + 8, y0 + s * 0.55), (x0 + s * 0.42, y0 + s - 9), (x0 + s - 6, y0 + 7)], fill=M.BLUE, width=4)
        d.text((112, y), c, font=M.font(31), fill=M.BLUE)
        y += 48
    note_y = max(y + 12, 1150)
    if note_y + 60 > 1222:
        note_y = 1160
    M.band_note(d, a["note"], y=note_y)
    M.save(im, a["n"], a["slug"], a["cap"] + M.CTA)


if __name__ == "__main__":
    build(json.loads(open(sys.argv[1], encoding="utf-8").read()))
