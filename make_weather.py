#!/usr/bin/env python3
"""香芝市周辺の週間天気画像(1080x1350)を気象庁の予報から作る。
出力: weather/weather_YYYYMMDD.jpg + .txt + .mp4 + cover/(リール)。投稿は post_weather.py
データ: 気象庁 https://www.jma.go.jp/bosai/forecast/data/forecast/290000.json (奈良県)
  今日 = 府県天気予報(奈良県北部・奈良の気温)、明日以降 = 週間天気予報(奈良県・奈良の気温)
"""
import json, math, sys, urllib.request
from datetime import date, datetime
from PIL import Image, ImageDraw
from make_posts import (base, font, rounded, title_hl, band_note, HERE, W,
                        BLUE, INK, GRAY, WHITE, YELLOW, TAGS, with_cta)

URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/290000.json"
WD = "月火水木金土日"
RED = (220, 50, 47)
COOL = (30, 110, 210)
SUN = (247, 148, 29)
CLOUD = (150, 160, 172)
DROP = (30, 120, 220)
# 天気ごとの行の背景色(ぱっと見で晴れ/くもり/雨がわかるように)
# 天気は保証できないことを画像と本文に必ず載せる(ユーザー指示 2026-10-28)
NOTE = "※予報は変わることがあります。内容を保証するものではありません"
NOTE_LONG = "天気予報は変わることがあります。この投稿の内容を保証するものではありません。最新の情報は気象庁ホームページでご確認ください。"
ROW_BG = {"晴れ": (255, 243, 214), "くもり": (234, 237, 241), "雨": (214, 233, 252), "雪": (240, 246, 255)}
MAIN = {"1": "晴れ", "2": "くもり", "3": "雨", "4": "雪"}


def parse_code(code):
    """気象庁の天気コード → (主な天気, つなぎ語, 従の天気)。例 202 → (くもり, 一時, 雨)"""
    m = MAIN.get(code[0], "くもり"); r = int(code[1:])
    if r == 0:
        return m, None, None
    if code[0] in "12":
        if r in (1, 10, 11):
            sub = "くもり" if m == "晴れ" else "晴れ"
        elif r in (4, 5, 15, 16, 17):
            sub = "雪"
        else:
            sub = "雨"
        join = "のち" if r >= 10 else ("一時" if r in (2, 4) else "時々")
        return m, join, sub
    if r in (1, 11):
        return m, ("のち" if r >= 10 else "時々"), "晴れ"
    if r == 13:
        return m, "のち", "くもり"
    if r in (3, 14):
        return m, ("のち" if r >= 10 else "時々"), ("雪" if m == "雨" else "雨")
    return m, None, None


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "kitano-ig-post"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    short, week = data[0], data[1]
    days = []
    wts, wtemp = week["timeSeries"]
    for i, t in enumerate(wts["timeDefines"]):
        a = wts["areas"][0]; b = wtemp["areas"][0]
        days.append({"date": date.fromisoformat(t[:10]), "code": a["weatherCodes"][i],
                     "pop": a["pops"][i], "max": b["tempsMax"][i], "min": b["tempsMin"][i]})
    # 今日の分は府県天気予報(奈良県北部=香芝市を含む)で上書き
    today = date.fromisoformat(short["reportDatetime"][:10])
    ts0, ts1, ts2 = short["timeSeries"][:3]
    north = [a for a in ts0["areas"] if a["area"]["name"] == "北部"][0]
    for i, t in enumerate(ts0["timeDefines"]):
        for d in days:
            if d["date"] == date.fromisoformat(t[:10]) and d["date"] <= date.fromordinal(today.toordinal() + 1):
                d["code"] = north["weatherCodes"][i]
    north_p = [a for a in ts1["areas"] if a["area"]["name"] == "北部"][0]
    for d in days:
        ps = [int(p) for t, p in zip(ts1["timeDefines"], north_p["pops"]) if p and date.fromisoformat(t[:10]) == d["date"]]
        if ps:
            d["pop"] = str(max(ps))
    # 今日の最高気温(09:00の値)。今日の最低は朝の発表には無い(00:00欄は最高と同じ値が入る)ので「−」のまま
    nara_t = [a for a in ts2["areas"] if a["area"]["name"] == "奈良"][0]
    for t, v in zip(ts2["timeDefines"], nara_t["temps"]):
        dt = datetime.fromisoformat(t)
        for d in days:
            if d["date"] == dt.date() == today and dt.hour == 9 and not d["max"]:
                d["max"] = v
    days = [d for d in days if d["date"] >= today][:7]
    return days, datetime.fromisoformat(short["reportDatetime"])


# ---------- 天気マーク(フォントに頼らず図形で描く=GitHub Actionsでも同じ見た目) ----------
def draw_sun(d, cx, cy, r):
    for k in range(8):
        a = math.pi / 4 * k
        d.line([(cx + math.cos(a) * r * 1.25, cy + math.sin(a) * r * 1.25),
                (cx + math.cos(a) * r * 1.65, cy + math.sin(a) * r * 1.65)], fill=SUN, width=max(3, int(r * 0.22)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SUN)


def draw_cloud(d, cx, cy, r, fill=CLOUD):
    d.ellipse([cx - r * 1.5, cy - r * 0.2, cx - r * 0.3, cy + r * 0.9], fill=fill)
    d.ellipse([cx - r * 0.9, cy - r * 0.9, cx + r * 0.5, cy + r * 0.6], fill=fill)
    d.ellipse([cx + r * 0.0, cy - r * 0.5, cx + r * 1.3, cy + r * 0.8], fill=fill)
    d.rounded_rectangle([cx - r * 1.2, cy + r * 0.1, cx + r * 1.0, cy + r * 0.9], radius=int(r * 0.4), fill=fill)


def draw_rain(d, cx, cy, r):
    draw_cloud(d, cx, cy - r * 0.35, r * 0.9, fill=(120, 132, 148))
    for dx in (-0.8, 0, 0.8):
        x = cx + dx * r; y = cy + r * 0.75
        d.line([(x + r * 0.15, y), (x - r * 0.1, y + r * 0.55)], fill=DROP, width=max(3, int(r * 0.2)))


def draw_snow(d, cx, cy, r):
    draw_cloud(d, cx, cy - r * 0.35, r * 0.9, fill=(150, 165, 185))
    for dx in (-0.8, 0, 0.8):
        x = cx + dx * r; y = cy + r * 0.95; s = r * 0.16
        d.ellipse([x - s, y - s, x + s, y + s], fill=(120, 170, 230))


ICON = {"晴れ": draw_sun, "くもり": draw_cloud, "雨": draw_rain, "雪": draw_snow}


def weather_icon(d, cx, cy, main, join, sub):
    if not sub:
        ICON[main](d, cx, cy, 30)
        return
    ICON[main](d, cx - 14, cy - 8, 24)          # 主の天気を大きく左上
    ICON[sub](d, cx + 28, cy + 22, 15)          # 従の天気を小さく右下


def label_text(main, join, sub):
    return main if not sub else f"{main}{join}{sub}"


def comment(days):
    for d in days[1:]:
        m, j, s = parse_code(d["code"])
        if (m == "雨" or s == "雨") and d["pop"] and int(d["pop"]) >= 50:
            return f"{WD[d['date'].weekday()]}曜は雨の予報。雨漏りが気になる方はお早めに"
    if all(parse_code(d["code"])[0] == "晴れ" for d in days):
        return "晴れが続きます。屋根の点検にぴったりの1週間です"
    return "屋根の点検・お見積りは無料。お気軽にご相談ください"


def make(days, issued):
    im, d = base()
    title_hl(d, "香芝市周辺の週間天気", 170, 50, 700)
    fs = font(24, False)
    t = f"{issued.month}/{issued.day} {issued.hour}時 発表"
    d.text((W - 48 - fs.getlength(t), 190), t, font=fs, fill=GRAY)
    # 見出し行
    y = 252; fh = font(22, False)
    for x, s in ((80, "日付"), (300, "天気"), (735, "最高/最低"), (930, "降水確率")):
        d.text((x, y), s, font=fh, fill=GRAY)
    y = 284
    fdate = font(38); fwd = font(30); flab = font(34); ftemp = font(40); fpop = font(36)
    for i, day in enumerate(days):
        main, join, sub = parse_code(day["code"])
        rounded(d, [48, y, W - 48, y + 100], 18, ROW_BG[main])
        if i == 0:
            d.rounded_rectangle([48, y, W - 48, y + 100], radius=18, outline=BLUE, width=5)
        # 日付・曜日(今日はバッジ)
        ds = f"{day['date'].month}/{day['date'].day}"
        d.text((72, y + 23 if i else y + 4), ds, font=fdate, fill=INK)
        wd = WD[day["date"].weekday()]
        wcol = BLUE if wd == "土" else RED if wd == "日" else INK
        d.text((72 + fdate.getlength(ds) + 8, y + 29 if i else y + 10), f"({wd})", font=fwd, fill=wcol)
        if i == 0:
            rounded(d, [72, y + 58, 148, y + 92], 10, BLUE)
            d.text((84, y + 60), "今日", font=font(24), fill=WHITE)
        # マーク + 文字
        weather_icon(d, 330, y + 50, main, join, sub)
        lab = label_text(main, join, sub)
        fl = flab if flab.getlength(lab) <= 300 else font(28)
        d.text((400, y + 50 - fl.size * 0.62), lab, font=fl, fill=INK)
        # 気温
        mx = f"{day['max']}°" if day["max"] else "−"
        mn = f"{day['min']}°" if day["min"] else "−"
        d.text((735, y + 24), mx, font=ftemp, fill=RED)
        d.text((735 + ftemp.getlength(mx) + 6, y + 30), "/", font=font(32, False), fill=GRAY)
        d.text((735 + ftemp.getlength(mx) + 26, y + 24), mn, font=ftemp, fill=COOL)
        # 降水確率(50%以上は青で強調)
        pop = f"{day['pop']}%" if day["pop"] else "−"
        hot = day["pop"] and int(day["pop"]) >= 50
        d.text((W - 72 - fpop.getlength(pop), y + 27), pop, font=fpop, fill=DROP if hot else GRAY)
        y += 112   # 行の間を12px空ける(make_videos.py が1行ずつのブロックとして順に登場させる)
    # 出典(気象庁の利用規約に沿って出典と加工の旨を記載)
    fsrc = font(21, False)
    src = "出典：気象庁ホームページ（奈良県の天気予報・週間天気予報、気温は奈良）を加工して作成"
    d.text(((W - fsrc.getlength(src)) / 2, y), src, font=fsrc, fill=GRAY)
    d.text(((W - fsrc.getlength(NOTE)) / 2, y + 32), NOTE, font=fsrc, fill=GRAY)
    band_note(d, comment(days), y=1158, bg=YELLOW, fg=INK)
    return im


WTAGS = ["#香芝市天気", "#奈良天気", "#週間天気"]


def deg(v):
    return f"{v}°" if v else "−"


def caption(days, issued):
    lines = [f"☀ 香芝市周辺の週間天気（{issued.month}/{issued.day}発表）", ""]
    for day in days:
        m, j, s = parse_code(day["code"])
        lines.append(f"{day['date'].month}/{day['date'].day}({WD[day['date'].weekday()]}) {label_text(m, j, s)}"
                     f"　{deg(day['max'])}/{deg(day['min'])}　☔{day['pop'] + '%' if day['pop'] else '−'}")
    lines += ["", comment(days), "", "出典：気象庁ホームページ（奈良県の天気予報・週間天気予報）を加工して作成",
              "※" + NOTE_LONG]
    # Instagram のハッシュタグは30個まで
    return with_cta("\n".join(lines)) + "\n\n" + " ".join(WTAGS + TAGS.split()[:30 - len(WTAGS)])


WDIR = HERE / "weather"   # posts/ に置くと通常の投稿の順番待ちに混ざるので別フォルダ


def build(out_dir=WDIR, video=True):
    """今日の天気画像・本文・リール動画(BGM付き)・表紙を weather/ に作り、名前(weather_YYYYMMDD)を返す"""
    days, issued = fetch()
    name = f"weather_{issued:%Y%m%d}"
    out_dir.mkdir(exist_ok=True)
    make(days, issued).save(out_dir / f"{name}.jpg", quality=92)
    (out_dir / f"{name}.txt").write_text(caption(days, issued), encoding="utf-8")
    print("saved", out_dir / f"{name}.jpg")
    for d in days:
        print(d)
    if video:
        import make_videos   # 通常の投稿と同じアニメーション(1行ずつ登場)＋BGM。出力先だけ weather/ に向ける
        make_videos.POSTS = out_dir
        make_videos.COVERS = out_dir / "cover"
        make_videos.make(name)
    return name


if __name__ == "__main__":
    # python make_weather.py            画像・本文・動画を weather/ に作る
    # python make_weather.py --no-video 画像と本文だけ(デザイン確認用)
    print("NAME", build(video="--no-video" not in sys.argv))
