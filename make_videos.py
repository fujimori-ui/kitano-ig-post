#!/usr/bin/env python3
"""北野工作所 投稿画像(posts/NN_slug.jpg)からアニメーション付きリール動画(posts/NN_slug.mp4)を作る。

完成画像を上から「ブロック」(タイトル・写真・帯など)に自動で分け、順番に動かして登場させる。
動かし方は投稿ごとに組み合わせを変える(毎回同じに見えないように。投稿名から決まるので作り直しても同じ):
  ヘッダー: 上から降りる / ふわっと出る / 左から入る
  フッター: 下からせり上がる / ふわっと出る / 右から入る
  写真など大きいブロック: 左→右ワイプ / 右→左ワイプ / ズームイン / 中央から開く / 縦じまブラインド / 左からスライド
  文字など小さいブロック: 浮き上がる / ふわっと / 左から / 右から / ポップ / 左→右に現れる
  出る順番: 上から / 下から / 写真先 / 文字先、速さ: 0.8〜1.25倍、最後の止め時間: 0〜3秒
さらに系統を4つ持ち(2026-10-30〜)、投稿予定の順で直前2本と同じ系統・直前3本と同じ細かい動きを使わない:
  blocks(上の組み合わせで順に出る) / photo_first(写真を大きく見せてから元の位置へ) /
  focus_items(全体を出したあと箇条書きを1行ずつ拡大) / scan_zoom(青い線が上から走って現れ、最後に少し寄る)
  決めた動きは anim_log.json に記録。決め直しは python make_videos.py --renew NN_slug …
最後のコマは元の画像と同じ。音は make_music.py のBGM(購入曲、無ければ自前合成)を入れる。
1080×1920(9:16)の中央に 1080×1350 の画像を置くので、
フィードでは画像と同じ見え方、リール画面では上下に余白が付く。

リールの表紙(カバー)は posts/cover/NN_slug.jpg(1080×1920、動画の最後のコマと同じ)に別に作る。
4:5 の投稿画像をそのまま表紙にすると Instagram が 9:16 に広げて左右が切れるため(2026-10-26 に判明)。
動画を作ると自動で作られ、無い/動画より古い表紙は実行のたびに動画の最後のコマから作り直す。

使い方: python make_videos.py            # 全部(mp4が無い/古いものだけ)＋表紙の不足分
        python make_videos.py --unposted # 未投稿を全部、投稿予定の順に作り直す
        python make_videos.py 03_kawara  # 指定したものだけ作り直す
        python make_videos.py --covers   # 表紙だけ作り直す(全部)
必要: ffmpeg, Pillow, numpy
"""
import json, random, subprocess, sys, zlib
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


# 出し直しで「違うアニメーションで」と言われた投稿は、ここで動きを指定する(ユーザー指示 2026-10-30)
PATTERN_OVERRIDE = {
    "25_news_kimari_monku": dict(head="slide_l", foot="slide_r", big="curtain", small="pop", order="bottom",
                                 speed=1.25, extra=1.5),
}


FAMILIES = ["blocks", "photo_first", "focus_items", "scan_zoom"]
ANIM_LOG = HERE / "anim_log.json"   # どの投稿にどの動きを使ったかの記録(作り直しても同じ動きになる)
RECENT = 3                          # 直前の何本と被らないようにするか


def load_log():
    return json.loads(ANIM_LOG.read_text(encoding="utf-8")) if ANIM_LOG.exists() else {}


def save_log(log):
    ANIM_LOG.write_text(json.dumps(dict(sorted(log.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def post_order():
    """投稿済み(古い順)＋これから出る予定の順番。動きを「直前の投稿と被らない」ように決めるために使う"""
    try:
        import post_ig
        state = post_ig.load_state()
        done = [k for k, v in sorted(state["posted"].items(), key=lambda kv: kv[1].get("date", ""))]
        posted = {k: dict(v) for k, v in state["posted"].items()}
        todo = []
        while True:
            nx = post_ig.next_item(state, posted=posted)
            if not nx or nx in posted:
                break
            todo.append(nx)
            posted[nx] = {"date": "9999", "category": post_ig.category(nx)}
        return done + todo
    except Exception as e:
        print(f"(予定順が取れないので番号順で決めます: {e})")
        return sorted(p.stem for p in POSTS.glob("*.jpg"))


def choose_pattern(slug, log=None, order=None):
    """投稿ごとの動き。ユーザー指示 2026-10-30「アニメーションは都度定期的に変更を繰り返してほしい」:
    ・動きの系統(順番に出る/写真から始まる/1項目ずつ拡大/スキャンして寄る)を、直前2本と同じにしない
    ・細かい動き(入り方・順番・速さ)も直前3本で使ったものを避ける
    決めた結果は anim_log.json に記録(作り直しても同じ。決め直すときは make_videos.py --renew)"""
    if slug in PATTERN_OVERRIDE:
        return dict(PATTERN_OVERRIDE[slug])
    log = load_log() if log is None else log
    if slug in log:
        return dict(log[slug])
    order = order or post_order()
    i = order.index(slug) if slug in order else len(order)
    prev = [log[k] for k in order[:i] if k in log][-RECENT:]
    r = random.Random(zlib.crc32(slug.encode()) ^ 0x5eed)
    fams = [f for f in FAMILIES if f not in [p.get("family", "blocks") for p in prev[-2:]]]
    if not has_photo(slug):
        fams = [f for f in fams if f != "photo_first"] or ["blocks"]
    used = {}
    for p in prev:
        for k, v in p.items():
            used.setdefault(k, set()).add(v)

    def pick(key, choices):
        return r.choice([c for c in choices if c not in used.get(key, set())] or choices)

    pat = dict(family=pick("family", fams), head=pick("head", HEAD_STYLES), foot=pick("foot", FOOT_STYLES),
               big=pick("big", BIG_STYLES), small=pick("small", SMALL_STYLES), order=pick("order", ORDERS),
               speed=pick("speed", [0.8, 1.0, 1.25]), extra=r.choice([0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]))
    log[slug] = pat
    save_log(log)
    return dict(pat)


PALETTE = np.array([(255, 255, 255), (219, 247, 254), (255, 224, 51), (3, 110, 184), (34, 34, 34), (120, 120, 120)])


def photo_block(card, blocks=None):
    """写真の帯の縦の範囲 (y0, y1)。無ければ None。
    行ごとに「デザインの色(白・水色・黄・青・黒・灰)から遠い画素」の割合を見て、写真らしい行が120px以上続く所を探す"""
    a = np.asarray(card.convert("RGB").crop((60, 0, W - 60, H))).astype(int)[:, ::4]
    dist = np.abs(a[:, :, None, :] - PALETTE[None, None, :, :]).sum(axis=3).min(axis=2)
    photo_row = (dist > 40).mean(axis=1) > 0.35
    best, run = None, None
    for y in range(HEAD, FOOT):
        if photo_row[y]:
            run = run or [y, y]
            run[1] = y
        elif run:
            if run[1] - run[0] >= 120 and (not best or run[1] - run[0] > best[1] - best[0]):
                best = tuple(run)
            run = None
    if run and run[1] - run[0] >= 120 and (not best or run[1] - run[0] > best[1] - best[0]):
        best = tuple(run)
    return (best[0], best[1] + 1) if best else None


def has_photo(slug):
    card = Image.open(POSTS / f"{slug}.jpg").convert("RGB")
    return photo_block(card, find_blocks(card)) is not None


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


def make(slug, log=None, order=None):
    card = Image.open(POSTS / f"{slug}.jpg").convert("RGB")
    blocks = find_blocks(card)
    pat = choose_pattern(slug, log, order)
    sp = pat["speed"]
    fam = pat.get("family", "blocks")
    photo = photo_block(card, blocks) if fam == "photo_first" else None
    if fam == "photo_first" and not photo:
        fam = "blocks"
    # 登場の予定表: (開始秒, 長さ, 種類, 範囲)
    plan = [(0.0, 0.6 * sp, pat["head"], (0, HEAD)), (0.2, 0.6 * sp, pat["foot"], (FOOT, H))]
    foot_end = 0.2 + 0.6 * sp
    bigs = [b for b in blocks if b[1] - b[0] > 250]
    smalls = [b for b in blocks if b[1] - b[0] <= 250]
    order = {"top": blocks, "bottom": blocks[::-1], "big_first": bigs + smalls, "small_first": smalls + bigs}[pat["order"]]
    t = 0.5
    scan = None     # scan_zoom: (開始秒, 長さ)
    focus = []      # focus_items: (開始秒, 長さ, 範囲) 1行ずつ拡大して読ませる
    hero = None     # photo_first: (大きく見せる秒, 元の位置へ戻る秒, 写真の範囲)
    if fam == "photo_first":
        hero = (1.3 * sp, 0.7 * sp, photo)
        plan = [(0.9 * sp, 0.6 * sp, pat["head"], (0, HEAD)), (1.1 * sp, 0.6 * sp, pat["foot"], (FOOT, H))]
        foot_end = 1.7 * sp
        t = 2.0 * sp
        for b0, b1 in blocks:
            parts = [(b0, b1)] if b1 <= photo[0] or b0 >= photo[1] else \
                [r for r in ((b0, photo[0]), (photo[1], b1)) if r[1] - r[0] > 6]
            for r in parts:
                plan.append((t, 0.55 * sp, pat["small"], r))
                t += 0.35 * sp
    elif fam == "focus_items":
        for b0, b1 in blocks:   # まず全体をさっと出す
            plan.append((t, 0.45 * sp, "fade" if b1 - b0 <= 250 else pat["big"], (b0, b1)))
            t += 0.15 * sp
        t += 0.6
        for b0, b1 in blocks:   # 箇条書きの行(低めのブロック)を順番に拡大
            if 60 < b1 - b0 < 200:
                focus.append((t, 0.75 * sp, (b0, b1)))
                t += 0.6 * sp
        t = max(t - 2.0, 0.5)
    elif fam == "scan_zoom":
        scan = (0.5, 2.6 * sp)   # ヘッダー・フッターのあと、上から下へ青い線が走って中身が現れる
        t = 0.5 + 2.6 * sp - 1.0
    else:
        for b0, b1 in order:
            big = b1 - b0 > 250
            plan.append((t, (0.8 if big else 0.55) * sp, pat["big"] if big else pat["small"], (b0, b1)))
            t += (0.75 if big else 0.4) * sp
    # 最後に止まって見せる時間も投稿ごとに変える(全体 8〜11 秒) → BGMの長さも投稿ごとに変わる
    total = max(8.0, t + 4.0) + pat["extra"]
    nframes = int(total * FPS)
    done = max([s + d for s, d, _, _ in plan] + [s + d for s, d, _ in focus]
               + ([hero[0] + hero[1]] if hero else []) + ([sum(scan)] if scan else [])) + 0.3

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
        if hero:
            draw_hero(fr, card, hero, now)
        for s, d, (b0, b1) in focus:
            if s <= now < s + d:
                draw_focus(fr, card, b0, b1, (now - s) / d)
        if scan:
            fr = draw_scan(fr, card, scan, now, total)
        ff.stdin.write(fr.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg 失敗: {slug}")
    add_music(out)  # 無音の動画にBGMを入れる
    save_cover(slug, fr)  # 表紙 = 最後のコマ(9:16)
    print(f"saved {out.name}  {total:.1f}秒  ブロック{len(blocks)}個  系統={fam} 動き={pat['head']}/{pat['foot']}/{pat['big']}/{pat['small']}/{pat['order']} x{sp}")


def draw_hero(fr, card, hero, now):
    """photo_first: 写真を画面いっぱいに大きく見せ(ゆっくり寄る)、そのあと元の位置・大きさへ縮みながら戻る"""
    hold, back, (b0, b1) = hero
    if now >= hold + back:
        fr.paste(card.crop((0, b0, W, b1)), (0, OY + b0))
        return
    im = card.crop((48, b0, W - 48, b1))
    big_w = int(VW * 1.08)
    if now < hold:
        w = int(VW * (1.0 + 0.08 * now / hold))
        h = int(im.height * w / im.width)
        fr.paste(WHITE, (0, OY + HEAD, VW, OY + FOOT))
        fr.paste(blend(im.resize((w, h), Image.BILINEAR), min(1.0, now / 0.4)), ((VW - w) // 2, OY + (H - h) // 2))
    else:
        p = ease((now - hold) / back)
        w = int(big_w + (im.width - big_w) * p)
        h = int(im.height * w / im.width)
        cy = int(OY + H // 2 + ((b0 + b1) // 2 - H // 2) * p)
        fr.paste(WHITE, (0, OY + b0, VW, OY + b1))
        fr.paste(im.resize((w, h), Image.BILINEAR), (VW // 2 - w // 2, cy - h // 2))


def draw_focus(fr, card, b0, b1, p):
    """focus_items: 1行を少し大きく(最大1.07倍)して前に出し、左に黄色い印を付けて読ませる"""
    k = float(np.sin(min(max(p, 0.0), 1.0) * np.pi))
    sc = 1 + 0.07 * k
    w, h = int(W * sc), int((b1 - b0) * sc)
    z = card.crop((0, b0, W, b1)).resize((w, h), Image.BILINEAR)
    y = OY + b0 - (h - (b1 - b0)) // 2
    fr.paste(z.crop(((w - W) // 2, 0, (w - W) // 2 + W, h)), (0, y))
    if k > 0.05:
        fr.paste(Image.new("RGB", (int(10 * k) + 2, h - 16), (255, 224, 51)), (20, y + 8))


def draw_scan(fr, card, scan, now, total):
    """scan_zoom: 青い線が上から下へ走り、通ったところから中身が現れる。出そろったあと、ほんの少し(3.5%)寄る
    (大きく寄ると左右の文字が切れるので控えめに)"""
    s0, d = scan
    if now < s0 + d:
        yl = HEAD + int((FOOT - HEAD) * ease((now - s0) / d)) if now > s0 else HEAD
        if yl > HEAD:
            fr.paste(card.crop((0, HEAD, W, yl)), (0, OY + HEAD))
        fr.paste(Image.new("RGB", (VW, 6), BLUE), (0, OY + yl))
        return fr
    t0 = s0 + d + 0.3
    if now <= t0:
        return fr
    z = 1 + 0.035 * ease((now - t0) / max(0.1, total - t0))
    cw, ch = VW / z, VH / z
    box = (int((VW - cw) / 2), int((VH - ch) / 2), int((VW + cw) / 2), int((VH + ch) / 2))
    return fr.crop(box).resize((VW, VH), Image.BILINEAR)


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
    renew = "--renew" in sys.argv   # 指定した投稿の動きを決め直す(anim_log.json の記録を使わない)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    order = post_order()
    if "--unposted" in sys.argv:   # まだ投稿していないものを全部(画像を作り直したあとなど)
        import post_ig
        posted = post_ig.load_state()["posted"]
        args = [x for x in order if x not in posted and (POSTS / f"{x}.jpg").exists()]
    targets = args or [p.stem for p in sorted(POSTS.glob("*.jpg"))]
    log = load_log()
    if renew:
        for slug in targets:
            log.pop(slug, None)
    # 投稿予定の順に作る(前の投稿の動きを見て、被らないものを選ぶため)
    targets.sort(key=lambda x: order.index(x) if x in order else len(order))
    for slug in targets:
        mp4, jpg = POSTS / f"{slug}.mp4", POSTS / f"{slug}.jpg"
        if not args and mp4.exists() and mp4.stat().st_mtime >= jpg.stat().st_mtime:
            continue
        make(slug, log, order)
    refresh_covers()  # 表紙が無い/古いものを補う
