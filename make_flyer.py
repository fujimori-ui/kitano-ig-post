#!/usr/bin/env python3
"""毎月地域に配っているチラシ(表・裏のPDF)から、Instagram 投稿一式を作る。

出力: posts/flyer_YYYYMM.jpg(表紙 1080×1350)
      posts/flyer_YYYYMM.mp4(リール: 表紙 → 表面を上から下へ → 裏面を上から下へ → 表紙)
      posts/flyer_YYYYMM.txt は別途書く(本文はチラシの中身に合わせて毎月作る)
flyer_ で始まる投稿は post_ig.py が他より先に出す(配った月のうちに出すため)。

使い方: python make_flyer.py 表面.pdf 裏面.pdf 202610
必要: pymupdf, Pillow, ffmpeg
"""
import subprocess, sys
from make_music import add_music
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw, ImageFilter
import make_posts as mp

HERE = Path(__file__).parent
POSTS = HERE / "posts"
VW, VH, FPS = 1080, 1920, 30
A4W, A4H = 595.3, 841.9   # 仕上がりサイズ(トンボ・塗り足しを切り落とす)


def render(pdf, width=2160):
    page = pymupdf.open(pdf)[0]
    r = page.rect
    clip = pymupdf.Rect((r.width - A4W) / 2, (r.height - A4H) / 2, (r.width + A4W) / 2, (r.height + A4H) / 2)
    if r.width < A4W + 2:  # トンボ無しのPDFはそのまま
        clip = r
    pm = page.get_pixmap(matrix=pymupdf.Matrix(width / clip.width, width / clip.width), clip=clip)
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)


def shadowed(img, angle):
    """少し傾けて影を付けたチラシ(RGBA)"""
    pad = 40
    sh = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([pad + 8, pad + 12, pad + img.width + 8, pad + img.height + 12], fill=(0, 0, 0, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    sh.paste(img, (pad, pad))
    return sh.rotate(angle, resample=Image.BICUBIC, expand=True)


def cover(front, back, month):
    im, d = mp.base()
    mp.pill(d, f"{month}月のチラシ", bg=mp.YELLOW, fg=mp.INK)
    mp.draw_text(d, (48, 262), "香芝市内に、配布中です", mp.font(58), mp.INK)
    h = 680
    f = front.resize((int(front.width * h / front.height), h), Image.LANCZOS)
    b = back.resize((int(back.width * h / back.height), h), Image.LANCZOS)
    sb, sf = shadowed(b, -5), shadowed(f, 3)
    im.paste(sb, (1080 - sb.width - 30, 352), sb)
    im.paste(sf, (20, 345), sf)
    mp.band_note(d, "お手元に届いたら、ぜひご覧ください", y=1150)
    return im


def video(card, front, back, out):
    bgc = (238, 243, 248)
    oy = (VH - 1350) // 2

    def card_frame(z=1.0, a=1.0):
        fr = Image.new("RGB", (VW, VH), (255, 255, 255))
        fr.paste(Image.new("RGB", (VW, VH - oy - 1230), mp.BLUE), (0, oy + 1230))
        c = card if z == 1 else card.resize((int(1080 * z), int(1350 * z)), Image.BILINEAR).crop(
            (int(540 * z - 540), int(675 * z - 675), int(540 * z + 540), int(675 * z + 675)))
        fr.paste(c, (0, oy))
        return fr if a >= 1 else Image.blend(Image.new("RGB", (VW, VH), (255, 255, 255)), fr, a)

    def flyer_frame(img, t):
        """t=0..1: 拡大して上から下へなめる → 全体が見える大きさに引く"""
        fr = Image.new("RGB", (VW, VH), bgc)
        fit = min(VW / img.width, VH / img.height) * 0.94
        big = VW / img.width * 1.5
        if t < 0.75:
            s = big; p = mp_ease(t / 0.75)
            w, h = int(img.width * s), int(img.height * s)
            x = (VW - w) // 2; y = int(-(h - VH) * p)
        else:
            q = mp_ease((t - 0.75) / 0.25)
            s = big + (fit - big) * q
            w, h = int(img.width * s), int(img.height * s)
            x = (VW - w) // 2; y = int(-(h - VH) * (1 - q) + ((VH - h) // 2) * q)
        fr.paste(img.resize((w, h), Image.BILINEAR), (x, y))
        return fr

    segs = [(2.5, lambda t: card_frame(1 + 0.04 * t, min(1, t * 5))),
            (6.5, lambda t: flyer_frame(front, t)),
            (6.5, lambda t: flyer_frame(back, t)),
            (2.5, lambda t: card_frame(1.04 - 0.04 * mp_ease(t)))]
    total = sum(s for s, _ in segs)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = None
    for dur, fn in segs:
        n = int(dur * FPS)
        for i in range(n):
            fr = fn(i / n)
            if prev is not None and i < 9:  # 場面の切り替えは0.3秒で重ねる
                fr = Image.blend(prev, fr, (i + 1) / 10)
            ff.stdin.write(fr.tobytes())
        prev = fn(1.0)
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg 失敗")
    add_music(out)


def mp_ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


if __name__ == "__main__":
    front_pdf, back_pdf, ym = sys.argv[1], sys.argv[2], sys.argv[3]
    front, back = render(front_pdf), render(back_pdf)
    card = cover(front, back, int(ym[4:]))
    slug = f"flyer_{ym}"
    card.save(POSTS / f"{slug}.jpg", quality=92)
    video(card, front.resize((1080, int(front.height * 1080 / front.width)), Image.LANCZOS),
          back.resize((1080, int(back.height * 1080 / back.width)), Image.LANCZOS), POSTS / f"{slug}.mp4")
    print("saved", slug, "(本文 posts/%s.txt を書いてください)" % slug)
