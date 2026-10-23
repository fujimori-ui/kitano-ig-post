#!/usr/bin/env python3
"""北野工作所 投稿画像(posts/NN_slug.jpg)からアニメーション付きリール動画(posts/NN_slug.mp4)を作る。

完成画像を上から「ブロック」(タイトル・写真・帯など)に自動で分け、順番に動かして登場させる。
  ヘッダー: 上からスッと降りる / フッター: 下からせり上がる
  写真など大きいブロック: 左→右にワイプしながら少しズームが戻る
  文字など小さいブロック: ふわっと下から浮き上がる
最後のコマは元の画像と同じ。1080×1920(9:16)の中央に 1080×1350 の画像を置くので、
フィードでは画像と同じ見え方、リール画面では上下に余白が付く。

使い方: python make_videos.py            # 全部(mp4が無い/古いものだけ)
        python make_videos.py 03_kawara  # 指定したものだけ作り直す
必要: ffmpeg, Pillow, numpy
"""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).parent
POSTS = HERE / "posts"
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


def make(slug):
    card = Image.open(POSTS / f"{slug}.jpg").convert("RGB")
    blocks = find_blocks(card)
    # 登場の予定表: (開始秒, 長さ, 種類, 範囲)
    plan = [(0.0, 0.6, "down", (0, HEAD)), (0.2, 0.6, "up_in", (FOOT, H))]
    t = 0.5
    for b0, b1 in blocks:
        big = b1 - b0 > 250
        plan.append((t, 0.8 if big else 0.55, "wipe" if big else "rise", (b0, b1)))
        t += 0.75 if big else 0.4
    total = max(8.0, t + 4.0)
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
        if now < 0.8:  # 最初はフッター部分も白から始める
            fr.paste(WHITE, (0, OY + FOOT, VW, VH))
        for s, d, kind, im, y0 in pieces:
            p = ease((now - s) / d)
            if p <= 0:
                continue
            pw, ph = im.size
            if kind == "down":
                piece = blend(im, p)
                fr.paste(piece, (0, OY + y0 - int((1 - p) * 60)))
            elif kind == "up_in":
                dy = int((1 - p) * (VH - OY - y0))
                tall = Image.new("RGB", (VW, VH - OY - y0), BLUE)
                tall.paste(im, (0, 0))
                fr.paste(tall, (0, OY + y0 + dy))
            elif kind == "rise":
                fr.paste(blend(im, p), (0, OY + y0 + int((1 - p) * 40)))
            elif kind == "wipe":
                sc = 1 + 0.06 * (1 - ease((now - s) / (d + 1.2)))
                z = im.resize((int(pw * sc), int(ph * sc)), Image.BILINEAR)
                ox, oy = (z.width - pw) // 2, (z.height - ph) // 2
                z = z.crop((ox, oy, ox + pw, oy + ph))
                cut = max(1, int(pw * p))
                fr.paste(z.crop((0, 0, cut, ph)), (0, OY + y0))
                if p < 1 and 48 < cut < W - 54:  # ワイプの境目に青い線(写真の幅の中だけ)
                    fr.paste(Image.new("RGB", (6, ph), BLUE), (cut, OY + y0))
        if now >= done:  # 全部出そろったら元画像そのもの(取りこぼし防止)
            fr.paste(card, (0, OY))
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg 失敗: {slug}")
    print(f"saved {out.name}  {total:.1f}秒  ブロック{len(blocks)}個 {blocks}")


def blend(im, p):
    """白から元画像へフェード"""
    if p >= 1:
        return im
    return Image.blend(Image.new("RGB", im.size, WHITE), im, p)


if __name__ == "__main__":
    targets = sys.argv[1:] or [p.stem for p in sorted(POSTS.glob("*.jpg"))]
    for slug in targets:
        mp4, jpg = POSTS / f"{slug}.mp4", POSTS / f"{slug}.jpg"
        if not sys.argv[1:] and mp4.exists() and mp4.stat().st_mtime >= jpg.stat().st_mtime:
            continue
        make(slug)
