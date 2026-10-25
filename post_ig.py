#!/usr/bin/env python3
"""北野工作所 Instagram 自動投稿(クラウド版)

posts/ にある NN_slug.jpg + NN_slug.txt を1本ずつ投稿する。
順番は「種類(施工事例/豆知識/訪問販売注意/会社紹介/お困りごと)がまんべんなく回る」ように、
いちばん久しく出ていない種類の中で番号が小さいものを選ぶ(同じ種類ばかり続かない)。
種類は投稿名のキーワードで判定(CATEGORY_RULES / CATEGORY_OVERRIDE)。--plan 30 でこれからの順番を確認できる。
NN_slug.mp4(make_videos.py で作るアニメーション)があればリール(フィードにも表示)で投稿し、
jpg は表紙に使う。mp4 が無ければ画像で投稿。
投稿済みは state.json に記録(GitHub Actions がコミットで書き戻す)。
画像は公開リポジトリの raw URL を Instagram API(graph.instagram.com)に渡す。

1日3本(朝・昼・夜)を確実に出すため、自動投稿は「今の時間帯(朝=11時まで/昼=11〜17時/夜=17時から)に今日まだ出ていないとき」だけ投稿する。
--backup(GitHubの予備スケジュールから起動)は、さらに決まった時間内(朝7〜11時/昼12〜17時/夜20〜23時半)だけ動く。
--slug での手動投稿はこの判定をしない(時間帯の1本には数えない)。

毎月のチラシ(flyer_YYYYMM)は必ず月1回出す: その月の7日前から他より先に投稿する。
今月分のチラシがまだ posts/ に無いときは、朝の結果(RESULT行)に「⚠ 今月のチラシ未作成」を付けてメールで知らせる。

使い方: python post_ig.py [--dry-run] [--slug 03_kawara] [--backup] [--plan 30]
環境変数: KITANO_IG_USER_ID, KITANO_IG_ACCESS_TOKEN
"""
import datetime, json, os, sys, time
from pathlib import Path
import requests

HERE = Path(__file__).parent
POSTS = HERE / "posts"
STATE = HERE / "state.json"
RAW_BASE = "https://raw.githubusercontent.com/fujimori-ui/kitano-ig-post/main/posts/"
API = "https://graph.instagram.com/v21.0"


def log(msg):
    print(msg, flush=True)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(msg + "\n\n")


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"posted": {}}


# ---- 投稿の種類(カテゴリ)。同じ種類ばかり続かないよう、いちばん久しく出ていない種類から順番に出す ----
# 種類の見分けは投稿名(slug)のキーワードで行う。上から順に最初に当たったもの。
CATEGORY_RULES = [
    ("chuui",   ["houmon", "cooling_off", "news_tenken", "news_kimari", "news_kasai", "news_bundenban", "chuui_"]),
    ("komari",  ["komari_"]),
    ("mame",    ["mame_", "sign_", "season_", "amamori_sign"]),
    ("jirei",   ["kawara", "mune_tsumi", "hisashi", "namiita", "mune_bankin", "parapet", "hafu_", "amadoi_naka",
                 "case_", "blog_", "jirei_", "ba_"]),
]
CATEGORY_NAMES = {"jirei": "施工事例", "mame": "豆知識", "chuui": "訪問販売注意", "company": "会社紹介",
                  "komari": "お困りごと", "flyer": "チラシ"}
# 久しさが同じとき(まだ一度も出ていない種類が複数あるとき)の優先順
CATEGORY_ORDER = ["mame", "chuui", "jirei", "company", "komari"]


CATEGORY_OVERRIDE = {"13_amadoi": "mame", "43_blog_shimi": "mame"}  # キーワードで決めにくいもの


def category(slug):
    if slug.startswith("flyer_"):
        return "flyer"
    if slug in CATEGORY_OVERRIDE:
        return CATEGORY_OVERRIDE[slug]
    body = slug.split("_", 1)[1] if "_" in slug else slug
    for cat, keys in CATEGORY_RULES:
        if any(k in body for k in keys):
            return cat
    return "company"


def all_items():
    return sorted(p.stem for p in POSTS.glob("*.jpg") if (POSTS / f"{p.stem}.txt").exists())


def next_item(state, slug=None, posted=None):
    """次に出す1本。posted を渡すと state の代わりにその dict(slug→{"date":..}) を使う(予定表示用)。"""
    items = all_items()
    if slug:
        return slug if slug in items else None
    posted = state["posted"] if posted is None else posted
    # 毎月のチラシ(flyer_YYYYMM)は配った月のうちに必ず出したいので先に(ただし早すぎる月のものはまだ出さない)
    for s in items:
        if s.startswith("flyer_") and s not in posted and flyer_ready(s):
            return s
    todo = [s for s in items if s not in posted and not s.startswith("flyer_")]
    if not todo:
        return None
    # 種類ごとの「最後に出した日時」。まだ出ていない種類は "" で最優先
    # (この仕組みを入れた 2026-10-26 より前の投稿には category が無いので数えない → 今日から豆知識で始まる)
    last = {}
    for s, v in posted.items():
        if "category" not in v:
            continue
        c = v["category"]
        last[c] = max(last.get(c, ""), v.get("date", ""))
    cats = sorted({category(s) for s in todo},
                  key=lambda c: (last.get(c, ""), CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99))
    cat = cats[0]
    return [s for s in todo if category(s) == cat][0]


def plan(state, n=30):
    """これから出る順番を n 本ぶん表示(投稿はしない)。1日3本で日付も添える"""
    posted = {k: dict(v) for k, v in state["posted"].items()}
    day = datetime.date.today()
    slots = ["morning", "noon", "evening"]
    i = len([1 for v in posted.values() if v.get("date", "").startswith(day.isoformat())])
    for _ in range(n):
        s = next_item(state, posted=posted)
        if not s:
            print("(ここでネタ切れ)")
            break
        d = day + datetime.timedelta(days=i // 3)
        print(f"{d.month}/{d.day} {SLOTS[slots[i % 3]]}  {s:24s} [{CATEGORY_NAMES[category(s)]}]")
        posted[s] = {"date": f"{d.isoformat()} {['07:00', '12:30', '20:00'][i % 3]}", "category": category(s)}
        i += 1


def flyer_ready(slug):
    """flyer_YYYYMM は、その月の7日前から投稿してよい(例: flyer_202611 は 10/25 から)"""
    ym = slug.split("_", 1)[1][:6]
    if not ym.isdigit():
        return True
    first = datetime.date(int(ym[:4]), int(ym[4:6]), 1)
    return datetime.date.today() >= first - datetime.timedelta(days=7)


def flyer_warning():
    """今月のチラシが posts/ に無ければ注意文を返す(朝の結果に付けてメールで知らせる)"""
    ym = time.strftime("%Y%m")
    if (POSTS / f"flyer_{ym}.jpg").exists():
        return ""
    return f" | ⚠ 今月のチラシ(flyer_{ym})が未作成です。表裏PDFから make_flyer.py で作って push してください"


SLOTS = {"morning": "朝", "noon": "昼", "evening": "夜"}


def slot_now():
    """今の時間帯 'morning'(〜11時) / 'noon'(11〜17時) / 'evening'(17時〜)(TZ=Asia/Tokyo 前提)"""
    h = time.localtime().tm_hour
    return "morning" if h < 11 else "noon" if h < 17 else "evening"


def slot_done(state, slot):
    today = time.strftime("%Y-%m-%d")
    return any(v.get("slot") == slot and v["date"].startswith(today) for v in state["posted"].values())


def in_backup_window(slot):
    m = time.localtime().tm_hour * 60 + time.localtime().tm_min
    lo, hi = {"morning": (7 * 60, 11 * 60), "noon": (12 * 60, 17 * 60), "evening": (20 * 60, 23 * 60 + 30)}[slot]
    return lo <= m < hi


def api_post(path, data):
    r = requests.post(f"{API}/{path}", data=data, timeout=60)
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"Instagram API error: {j['error']}")
    return j


def publish(user_id, token, image_url, caption, video_url=None):
    if video_url:
        c = api_post(f"{user_id}/media", {"media_type": "REELS", "video_url": video_url, "cover_url": image_url,
                                          "share_to_feed": "true", "caption": caption, "access_token": token})
    else:
        c = api_post(f"{user_id}/media", {"image_url": image_url, "caption": caption, "access_token": token})
    cid = c["id"]
    for _ in range(60):  # 動画は取り込みに時間がかかる(最大5分待つ)
        s = requests.get(f"{API}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"container error: {s}")
        time.sleep(5)
    p = api_post(f"{user_id}/media_publish", {"creation_id": cid, "access_token": token})
    mid = p["id"]
    info = requests.get(f"{API}/{mid}", params={"fields": "permalink", "access_token": token}, timeout=60).json()
    return mid, info.get("permalink", "")


def main():
    dry = "--dry-run" in sys.argv
    slug = sys.argv[sys.argv.index("--slug") + 1] if "--slug" in sys.argv else None
    state = load_state()
    if "--plan" in sys.argv:
        i = sys.argv.index("--plan")
        plan(state, int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 30)
        return
    slot = None if slug else slot_now()
    if slot and "--backup" in sys.argv and not in_backup_window(slot):
        log(f"RESULT: SKIP 予備起動が時間外のため何もしません({time.strftime('%H:%M')})")
        return
    if slot and slot_done(state, slot):
        log(f"RESULT: ALREADY_POSTED 今日の{SLOTS[slot]}の分は投稿済みです")
        return
    warn = flyer_warning() if slot == "morning" else ""
    item = next_item(state, slug)
    if not item:
        log("RESULT: QUEUE_EMPTY 投稿できるネタがありません(posts/ に新しい画像と本文を追加してください)" + warn)
        return
    caption = (POSTS / f"{item}.txt").read_text(encoding="utf-8").strip()
    image_url = RAW_BASE + f"{item}.jpg"
    title = caption.split("\n", 1)[0][:40]
    cat = CATEGORY_NAMES[category(item)]
    log(f"次の投稿: {item} [{cat}] / {title}")
    log(f"画像: {image_url}")
    video_url = RAW_BASE + f"{item}.mp4" if (POSTS / f"{item}.mp4").exists() else None
    if video_url:
        log(f"動画(リール): {video_url}")
    if dry:
        log("RESULT: DRY_RUN " + item)
        print(caption)
        return
    user_id = os.environ["KITANO_IG_USER_ID"]
    token = os.environ["KITANO_IG_ACCESS_TOKEN"]
    # 画像URLが公開されているか確認(push直後は数十秒かかることがある)
    for u in filter(None, [image_url, video_url]):
        for _ in range(12):
            if requests.head(u, timeout=30).status_code == 200:
                break
            time.sleep(10)
    mid, url = publish(user_id, token, image_url, caption, video_url)
    state["posted"][item] = {"date": time.strftime("%Y-%m-%d %H:%M"), "media_id": mid, "url": url, "category": category(item)}
    if slot:
        state["posted"][item]["slot"] = slot
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    todo = [s for s in all_items() if s not in state["posted"]]
    stock = " ".join(f"{CATEGORY_NAMES[c]}{n}" for c, n in
                     sorted(((c, len([s for s in todo if category(s) == c])) for c in set(map(category, todo))), key=lambda x: -x[1]))
    log(f"RESULT: POSTED {item} [{cat}] | {title} | {url} | 残り{len(todo)}本(1日3本なので約{len(todo) // 3}日分、内訳: {stock}){warn}")


if __name__ == "__main__":
    main()
