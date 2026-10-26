#!/usr/bin/env python3
"""北野工作所 投稿画像(posts/NN_slug.jpg)からアニメーション付きリール動画(posts/NN_slug.mp4)を作る。

完成画像を上から「ブロック」(タイトル・写真・帯など)に自動で分け、順番に動かして登場させる。
動かし方は投稿ごとに組み合わせを変える(毎回同じに見えないように。投稿名から決まるので作り直しても同じ):
  ヘッダー: 上から降りる / ふわっと出る / 左から入る
  フッター: 下からせり上がる / ふわっと出る / 右から入る
  写真など大きいブロック: 左→右ワイプ / 右→左ワイプ / ズームイン / 中央から開く / 縦じまブラインド / 左からスライド
  文字など小さいブロック: 浮き上がる / ふわっと / 左から / 右から / ポップ / 左→右に現れる
  出る順番: 上から / 下から / 写真先 / 文字先、速さ: 0.8〜1.25倍、最後の止め時間: 0〜3秒
最後のコマは元の画像と同じ。音は make_music.py のBGM(購入曲、無ければ自前合成)を入れる。
1080×1920(9:16)の中央に 1080×1350 の画像を置くので、
フィードでは画像と同じ見え方、リール画面では上下に余白が付く。

リールの表紙(カバー)は posts/cover/NN_slug.jpg(1080×1920、動画の最後のコマと同じ)に別に作る。
4:5 の投稿画像をそのまま表紙にすると Instagram が 9:16 に広げて左右が切れるため(2026-10-26 に判明)。
動画を作ると自動で作られ、無い/動画より古い表紙は実行のたびに動画の最後のコマから作り直す。

使い方: python make_videos.py            # 全部(mp4が無い/古いものだけ)＋表紙の不足分
        python make_videos.py 03_kawara  # 指定したものだけ作り直す
        python make_videos.py --covers   # 表紙だけ作り直す(全部)
必要: ffmpeg, Pillow, numpy
"""
import random, subprocess, sys, zlib
from pathlib import Path
import numpy as np
from PIL import Image
from make_music import add_music

HERE = Path(__file__).parent
POSTS = HERE / "posts"
COVERS = POSTS / "cover"     # リールの表紙(9:16)
W, H = 1080, 1350            # 投稿画像
VW, VH = 1080, 1920          # 動画
OY = (VH - H) // 2           # 画像を置く縦位置
FPS = 30
BLUE = (3, 110, 184)
WHITE = (255, 255, 255)
HEAD, FOOT = 146, 1230       # make_posts.py の base() のヘッダー下端・フッター上端


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def find_blocks(card):
    """ヘッダーとフッターの間を、白い隙間で区切ったブロック(y0, y1)のリストにする。"""
    a = np.asarray(card.convert("RGB")).astype(int)
    ink = (np.abs(255 - a).max(axis=2) > 20).sum(axis=1) > 3
    blocks, y, top = [], HEAD + 4, None
    gap = 0
    for y in range(HEAD + 4, FOOT - 2):
        if ink[y]:
            if top is None:
                top = y
            gap = 0
        elif top is not None:
            gap += 1
            if gap >= 10:
                blocks.append((top, y - gap + 1)); top = None
    if top is not None:
        blocks.append((top, FOOT - 2))
    return [(max(HEAD + 2, b0 - 4), min(FOOT - 1, b1 + 4)) for b0, b1 in blocks if b1 - b0 > 6]


HEAD_STYLES = ["down", "fade", "slide_l"]
FOOT_STYLES = ["up_in", "fade_in", "slide_r"]
BIG_STYLES = ["wipe", "wipe_r", "zoom", "curtain", "blinds", "slide_l"]
SMALL_STYLES = ["rise", "fade", "slide_l", "slide_r", "pop", "wipe_flat"]
ORDERS = ["top", "bottom", "big_first", "small_first"]


def choose_pattern(slug):
    """投稿ごとに動かし方の組み合わせを決める(投稿名から決まるので作り直しても同じ)。"""
    r = random.Random(zlib.crc32(slug.encode()) ^ 0x5eed)
    return dict(head=r.choice(HEAD_STYLES), foot=r.choice(FOOT_STYLES), big=r.choice(BIG_STYLES),
                small=r.choice(SMALL_STYLES), order=r.choice(ORDERS), speed=r.choice([0.8, 1.0, 1.0, 1.25]),
                extra=r.choice([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]))


def draw(fr, kind, im, y0, p, now, s, d):
    """1つのブロックを進み具合 p(0〜1)で描く"""
    pw, ph = im.size
    y = OY + y0
    if kind == "down":
        fr.paste(blend(im, p), (0, y - int((1 - p) * 60)))
    elif kind == "fade":
        fr.paste(blend(im, p), (0, y))
    elif kind == "slide_l":
        fr.paste(blend(im, p), (-int((1 - p) * 160), y))
    elif kind == "slide_r":
        fr.paste(blend(im, p), (int((1 - p) * 160), y))
    elif kind == "rise":
        fr.paste(blend(im, p), (0, y + int((1 - p) * 40)))
    elif kind in ("pop", "zoom"):
        sc = (0.9 if kind == "pop" else 0.8) + (1 - (0.9 if kind == "pop" else 0.8)) * p
        z = im.resize((max(1, int(pw * sc)), max(1, int(ph * sc))), Image.BILINEAR)
        fr.paste(blend(z, p), ((pw - z.width) // 2, y + (ph - z.height) // 2))
    elif kind == "wipe_flat":
        cut = max(1, int(pw * p))
        fr.paste(im.crop((0, 0, cut, ph)), (0, y))
    elif kind in ("up_in", "fade_in"):
        tall = Image.new("RGB", (VW, VH - y), BLUE)
        tall.paste(im, (0, 0))
        if kind == "up_in":
            fr.paste(tall, (0, y + int((1 - p) * (VH - y))))
        else:
            fr.paste(blend(tall, p), (0, y))
    elif kind in ("wipe", "wipe_r", "curtain", "blinds"):
        sc = 1 + 0.06 * (1 - ease((now - s) / (d + 1.2)))
        z = im.resize((int(pw * sc), int(ph * sc)), Image.BILINEAR)
        ox, oy = (z.width - pw) // 2, (z.height - ph) // 2
        z = z.crop((ox, oy, ox + pw, oy + ph))
        if kind == "wipe":
            cut = max(1, int(pw * p))
            fr.paste(z.crop((0, 0, cut, ph)), (0, y))
            if p < 1 and 48 < cut < W - 54:  # ワイプの境目に青い線(写真の幅の中だけ)
                fr.paste(Image.new("RGB", (6, ph), BLUE), (cut, y))
        elif kind == "wipe_r":
            cut = max(1, int(pw * p))
            fr.paste(z.crop((pw - cut, 0, pw, ph)), (pw - cut, y))
            if p < 1 and 54 < pw - cut < W - 48:
                fr.paste(Image.new("RGB", (6, ph), BLUE), (pw - cut - 6, y))
        elif kind == "curtain":
            half = max(1, int(pw * p / 2))
            fr.paste(z.crop((pw // 2 - half, 0, pw // 2 + half, ph)), (pw // 2 - half, y))
        else:  # blinds: 8本の縦じまが左から開く
            n = 8
            sw = pw // n
            for k in range(n):
                cut = max(1, int(sw * p))
                fr.paste(z.crop((k * sw, 0, k * sw + cut, ph)), (k * sw, y))


def make(slug):
    card = Image.open(POSTS / f"{slug}.jpg").convert("RGB")
    blocks = find_blocks(card)
    pat = choose_pattern(slug)
    sp = pat["speed"]
    # 登場の予定表: (開始秒, 長さ, 種類, 範囲)
    plan = [(0.0, 0.6 * sp, pat["head"], (0, HEAD)), (0.2, 0.6 * sp, pat["foot"], (FOOT, H))]
    foot_end = 0.2 + 0.6 * sp
    bigs = [b for b in blocks if b[1] - b[0] > 250]
    smalls = [b for b in blocks if b[1] - b[0] <= 250]
    order = {"top": blocks, "bottom": blocks[::-1], "big_first": bigs + smalls, "small_first": smalls + bigs}[pat["order"]]
    t = 0.5
    for b0, b1 in order:
        big = b1 - b0 > 250
        plan.append((t, (0.8 if big else 0.55) * sp, pat["big"] if big else pat["small"], (b0, b1)))
        t += (0.75 if big else 0.4) * sp
    # 最後に止まって見せる時間も投稿ごとに変える(全体 8〜11 秒) → BGMの長さも投稿ごとに変わる
    total = max(8.0, t + 4.0) + pat["extra"]
    nframes = int(total * FPS)
    done = max(s + d for s, d, _, _ in plan) + 0.3

    out = POSTS / f"{slug}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    bg = Image.new("RGB", (VW, VH), WHITE)
    bg.paste(Image.new("RGB", (VW, VH - OY - FOOT), BLUE), (0, OY + FOOT))  # フッターの青を下まで
    pieces = [(s, d, kind, card.crop((0, y0, W, y1)), y0) for s, d, kind, (y0, y1) in plan]

    for i in range(nframes):
        now = i / FPS
        fr = bg.copy()
        if now < foot_end:  # フッターが出そろうまでは下の青も白から始める
            fr.paste(WHITE, (0, OY + FOOT, VW, VH))
        for s, d, kind, im, y0 in pieces:
            p = ease((now - s) / d)
            if p <= 0:
                continue
            draw(fr, kind, im, y0, p, now, s, d)
        if now >= done:  # 全部出そろったら元画像そのもの(取りこぼし防止)
            fr.paste(card, (0, OY))
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg 失敗: {slug}")
    add_music(out)  # 無音の動画にBGMを入れる
    save_cover(slug, fr)  # 表紙 = 最後のコマ(9:16)
    print(f"saved {out.name}  {total:.1f}秒  ブロック{len(blocks)}個  動き={pat['head']}/{pat['foot']}/{pat['big']}/{pat['small']}/{pat['order']} x{sp}")


def save_cover(slug, frame=None):
    """リールの表紙 posts/cover/<slug>.jpg(1080×1920)を保存する。frame が無ければ mp4 の最後のコマを切り出す。"""
    COVERS.mkdir(exist_ok=True)
    out = COVERS / f"{slug}.jpg"
    if frame is None:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.2", "-i", str(POSTS / f"{slug}.mp4"),
                        "-frames:v", "1", "-update", "1", "-q:v", "2", str(out)], check=True)
    else:
        frame.save(out, quality=92)
    return out


def refresh_covers(force=False):
    """表紙が無い/動画より古いもの(force なら全部)を動画の最後のコマから作り直す。"""
    n = 0
    for mp4 in sorted(POSTS.glob("*.mp4")):
        cov = COVERS / f"{mp4.stem}.jpg"
        if force or not cov.exists() or cov.stat().st_mtime < mp4.stat().st_mtime:
            save_cover(mp4.stem)
            n += 1
    print(f"表紙を{n}枚作成(posts/cover/)")


def blend(im, p):
    """白から元画像へフェード"""
    if p >= 1:
        return im
    return Image.blend(Image.new("RGB", im.size, WHITE), im, p)


if __name__ == "__main__":
    if "--covers" in sys.argv:
        refresh_covers(force=True)
        sys.exit()
    targets = sys.argv[1:] or [p.stem for p in sorted(POSTS.glob("*.jpg"))]
    for slug in targets:
        mp4, jpg = POSTS / f"{slug}.mp4", POSTS / f"{slug}.jpg"
        if not sys.argv[1:] and mp4.exists() and mp4.stat().st_mtime >= jpg.stat().st_mtime:
            continue
        make(slug)
    refresh_covers()  # 表紙が無い/古いものを補う
