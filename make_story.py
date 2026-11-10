#!/usr/bin/env python3
"""「今日の現場」をストーリー仕立てのリール動画にする(2026-11-11〜。施工前→作業中→施工後→ひとこと の順に写真が切り替わる)。
  python3 make_story.py content/story_xxx.json
記事.json: {"n":126,"slug":"genba_xxx_story","cap":"本文",
  "scenes":[{"photo":"…jpg","focus":0.5,"pill":"① 施工前","title":"黄色帯の見出し(15字まで)","sub":"説明(2行まで)","sec":4.0}, …],
  "end":{"pill":"…","title":"…","lines":["…"],"note":"水色帯","sec":5.5}}
出力: posts/NN_slug.mp4(BGM入り)/ posts/NN_slug.jpg(1枚目の場面)/ posts/cover/NN_slug.jpg(9:16)/ posts/NN_slug.txt
"""
import json, subprocess, sys
from PIL import Image, ImageDraw
import make_posts as M
from make_videos import VW, VH, OY, FPS, POSTS, save_cover, ease
from make_music import add_music
W, H = M.W, M.H
P0, P1 = 146, 960          # 写真の上端・下端
FADE = 0.5


def text_layer(sc):
    """写真より上に乗る文字(透明地)"""
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    d.rectangle([0, P1, W, 1230], fill=M.WHITE + (255,))
    if sc.get("pill"):
        M.pill(d, sc["pill"], P0 + 24)
    M.person(L, d, 872, P0 + 18, 184)      # 社長写真(写真の右上に小さく。必ず入れる)
    y = M.title_hl(d, sc["title"], P1 + 28, 56, 984)
    if sc.get("sub"):
        M.draw_text(d, (52, y + 22), sc["sub"], M.font(34, False), M.INK, maxw=976, spacing=1.45)
    return L


def end_card(e):
    im, d = M.base()
    d.rectangle([0, 146, W, 1230], fill=M.LIGHT)
    M.pill(d, e["pill"], 200)
    M.person(im, d, 700, 170, 330)         # 社長写真(大きく)
    y = M.title_hl(d, e["title"], 520, 62, 984)
    y += 44
    for ln in e["lines"]:
        y = M.draw_text(d, (52, y), ln, M.font(40, True if ln.startswith("★") else False), M.INK, maxw=976, spacing=1.5) + 26
    M.band_note(d, e["note"], y=1120, bg=M.WHITE)
    return im


def main(a):
    slug = f'{a["n"]:02d}_{a["slug"]}'
    base, _ = M.base()
    scenes = []
    for i, sc in enumerate(a["scenes"]):
        ph = M.cover(Image.open(sc["photo"]).convert("RGB"), int(W * 1.12), int((P1 - P0) * 1.12), sc.get("focus", 0.5))
        ph = ph.crop((0, 0, int(W * 1.12), int((P1 - P0) * 1.12)))
        scenes.append({"ph": ph, "txt": text_layer(sc), "sec": sc.get("sec", 4.0), "zin": i % 2 == 0})
    endc = end_card(a["end"]); esec = a["end"].get("sec", 5.5)

    def card(i, t):
        """i番目の場面の t 秒目(1080×1350)"""
        if i == len(scenes):
            return endc
        s = scenes[i]; im = base.copy()
        p = t / s["sec"]; z = 1 + 0.12 * (p if s["zin"] else 1 - p)          # ゆっくり寄る/引く
        pw, phh = s["ph"].size; cw, ch = pw * 1.12 / z / 1.12, phh / z
        box = ((pw - cw) / 2, (phh - ch) / 2, (pw + cw) / 2, (phh + ch) / 2)
        im.paste(s["ph"].resize((W, P1 - P0), Image.BILINEAR, box=box), (0, P0))
        k = ease((t - 0.15) / 0.6)                                         # 文字は左からすっと入る
        if k > 0:
            L = s["txt"]
            if k < 1:
                L = L.copy(); L.putalpha(L.getchannel("A").point(lambda v: int(v * k)))
            im.paste(L, (int(-60 * (1 - k)), 0), L)
        else:
            ImageDraw.Draw(im).rectangle([0, P1, W, 1230], fill=M.WHITE)
        return im

    secs = [s["sec"] for s in scenes] + [esec]
    total = sum(secs)
    out = POSTS / f"{slug}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-",
                           "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                           "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    first = None
    for f in range(int(total * FPS)):
        now = f / FPS; i = 0
        while now >= secs[i] and i < len(secs) - 1:
            now -= secs[i]; i += 1
        c = card(i, now)
        if i > 0 and now < FADE:                                            # 前の場面からふわっと切り替え
            c = Image.blend(card(i - 1, secs[i - 1]), c, ease(now / FADE))
        fr = Image.new("RGB", (VW, VH), M.WHITE); fr.paste(c, (0, OY))
        if i == 0 and first is None and now >= 1.2:
            first = (c.copy(), fr.copy())
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    assert ff.wait() == 0
    add_music(out)
    first[0].save(POSTS / f"{slug}.jpg", quality=92)
    save_cover(slug, first[1])
    (POSTS / f"{slug}.txt").write_text((a["cap"] + M.CTA).strip() + "\n\n" + M.TAGS, encoding="utf-8")
    print("saved", out, f"{total:.1f}秒")


if __name__ == "__main__":
    main(json.loads(open(sys.argv[1], encoding="utf-8").read()))
