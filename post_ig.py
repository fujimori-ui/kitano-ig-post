#!/usr/bin/env python3
"""北野工作所 Instagram 自動投稿(クラウド版)

posts/ にある NN_slug.jpg + NN_slug.txt を1本ずつ投稿する。
順番は「種類(施工事例/豆知識/訪問販売注意/会社紹介/お困りごと)がまんべんなく回る」ように、
いちばん久しく出ていない種類の中で番号が小さいものを選ぶ(同じ種類ばかり続かない)。
種類は投稿名のキーワードで判定(CATEGORY_RULES / CATEGORY_OVERRIDE)。--plan 30 でこれからの順番を確認できる。
NN_slug.mp4(make_videos.py で作るアニメーション)があればリール(フィードにも表示)で投稿し、
表紙には posts/cover/NN_slug.jpg(9:16、make_videos.py が動画と一緒に作る)を使う。
(4:5 の jpg を表紙にすると Instagram が 9:16 に広げて左右が切れる。cover が無いときだけ jpg で代用)
mp4 が無ければ画像で投稿。
投稿済みは state.json に記録(GitHub Actions がコミットで書き戻す)。
(2026-11-03 停止) 以前は投稿成功後に gbp_export.py でマイビジネス用を Google ドライブにも保存していた(state.json "gbp_drive": true で復活)。
さらに gbp_post.py で Googleビジネスプロフィール(マイビジネス)にも同じ内容を API で自動投稿する
(GBP_* の接続キーと state.json の gbp_location がある時だけ。API 未承認などで失敗しても Instagram 投稿は完了扱い)。
画像は公開リポジトリの raw URL を Instagram API(graph.instagram.com)に渡す。

1日2本(朝・夜)を確実に出すため、自動投稿は「今の時間帯(朝=14時まで/夜=14時から)に今日まだ出ていないとき」だけ投稿する。(2026-11-02 昼の投稿を廃止)
--backup(GitHubの予備スケジュールから起動)は、さらに決まった時間内(朝7〜11時/夜20〜23時半)だけ動く。
--slug での手動投稿はこの判定をしない(時間帯の1本には数えない)。

毎月のチラシ(flyer_YYYYMM)は必ず月1回出す: その月の7日前から他より先に投稿する。
ホームページの施工実績から works_watch.py が自動で作った投稿(名前に _web_ が入る)は、チラシの次に優先して出す
(2026-11-14 ユーザー指示「施工実績も投稿。WEBを定期的に見て優先的に投稿」。番号の小さい順=記事の古い順)。
今月分のチラシがまだ posts/ に無いときは、朝の結果(RESULT行)に「⚠ 今月のチラシ未作成」を付けてメールで知らせる。

使い方: python post_ig.py [--dry-run] [--slug 03_kawara] [--backup] [--plan 30]
環境変数: KITANO_IG_USER_ID, KITANO_IG_ACCESS_TOKEN
"""
import datetime, json, os, sys, time
from pathlib import Path
try:
    import requests   # 投稿にだけ必要。--plan や build_auto.py --stock では無くても動くように
except ImportError:
    requests = None

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
    ("miryoku", ["miryoku_"]),   # 北野工作所の魅力(ホームページの「選ばれる理由」「お悩み別」から。ユーザー指示 2026-11-10)
    ("chuui",   ["houmon", "cooling_off", "news_tenken", "news_kimari", "news_kasai", "news_bundenban", "chuui_"]),
    ("komari",  ["komari_"]),
    ("mame",    ["mame_", "sign_", "season_", "amamori_sign"]),
    ("jirei",   ["kawara", "mune_tsumi", "hisashi", "namiita", "mune_bankin", "parapet", "hafu_", "amadoi_naka",
                 "case_", "blog_", "jirei_", "ba_"]),
]
CATEGORY_NAMES = {"jirei": "施工事例", "mame": "豆知識", "chuui": "訪問販売注意", "company": "会社紹介",
                  "komari": "お困りごと", "flyer": "チラシ", "miryoku": "北野の魅力"}
# 久しさが同じとき(まだ一度も出ていない種類が複数あるとき)の優先順
CATEGORY_ORDER = ["miryoku", "mame", "jirei", "company", "komari", "chuui"]
# 訪問販売の注意は続くと多く感じる → 前の注意ネタのあと、ほかの種類を5本はさむ(6本に1本=3日に1本くらい)
# ユーザー指示 2026-11-10「最近訪問営業のネタが多いので、北野工作所の魅力も投稿してほしい」
CHUUI_GAP = 5


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
    todo = [s for s in items if (s not in posted or posted[s].get("requeue")) and not s.startswith("flyer_")]   # requeue=出し直し待ち(2026-11-12)
    # 訪問販売の注意ネタは出さない(ユーザー指示 2026-11-14「訪問販売の注意はいらない」)。作ってある分も順番から外す
    todo = [s for s in todo if category(s) != "chuui"]
    if not todo:
        return None
    # ホームページの新着施工実績(works_watch.py が作る *_web_*)はチラシの次に優先(2026-11-14)
    for s in todo:
        if is_web(s):
            return s
    # 施工事例(今日の現場・工場の様子も含む)は前倒し: 在庫があるかぎり、ほかの種類より先に続けて出す
    # ユーザー指示 2026-11-14「施工事例を優先して発信」「施工事例前倒し」。ブログと一緒に作った新しい現場(requeue)が先
    jirei = [s for s in todo if category(s) == "jirei"]
    if jirei:
        jirei.sort(key=lambda s: not posted.get(s, {}).get("requeue"))
        return jirei[0]
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
    if "chuui" in cats and len(cats) > 1 and last.get("chuui"):
        since = sum(1 for v in posted.values() if v.get("date", "") > last["chuui"] and not v.get("skipped"))
        if since < CHUUI_GAP:
            cats.remove("chuui")
    cat = cats[0]
    return [s for s in todo if category(s) == cat][0]


def plan(state, n=30):
    """これから出る順番を n 本ぶん表示(投稿はしない)。1日2本(朝・夜)で日付も添える"""
    posted = {k: dict(v) for k, v in state["posted"].items()}
    day = datetime.date.today()
    slots = ["morning", "evening"]
    # 今日すでに出た時間帯の数(手動 --slug の分は時間帯に数えない)
    i = len({v.get("slot") for v in posted.values() if v.get("slot") and v.get("date", "").startswith(day.isoformat())})
    for _ in range(n):
        s = next_item(state, posted=posted)
        if not s:
            print("(ここでネタ切れ)")
            break
        d = day + datetime.timedelta(days=i // 2)
        print(f"{d.month}/{d.day} {SLOTS[slots[i % 2]]}  {s:24s} [{CATEGORY_NAMES[category(s)]}]")
        posted[s] = {"date": f"{d.isoformat()} {['07:00', '20:00'][i % 2]}", "category": category(s)}
        i += 1


def planned_order(state=None):
    """投稿済み(古い順)＋これから出る予定の順番。構図・写真の形・アニメーションを直前の投稿と変えるために使う
    (make_posts.py / make_videos.py)。予定の分には順番どおりの仮の日時を入れる(同じ日時だと順番が狂うため)"""
    state = state or load_state()
    done = [k for k, v in sorted(state["posted"].items(), key=lambda kv: kv[1].get("date", "")) if v.get("date")]
    posted = {k: dict(v) for k, v in state["posted"].items()}
    todo = []
    while True:
        nx = next_item(state, posted=posted)
        if not nx or (nx in posted and not posted[nx].get("requeue")):
            break
        todo.append(nx)
        posted[nx] = {"date": f"9999-{len(todo):05d}", "category": category(nx)}
    return done + todo


def is_web(slug):
    """works_watch.py がホームページの施工実績から自動で作った投稿(優先して出す)"""
    return "_web_" in slug


def web_waiting(state):
    """まだ出していないWEB施工実績の投稿(結果メール用)"""
    return [s for s in all_items() if is_web(s) and (s not in state["posted"] or state["posted"][s].get("requeue"))]


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
    """今の時間帯 'morning'(〜14時) / 'evening'(14時〜)(TZ=Asia/Tokyo 前提)。昼(noon)は2026-11-02に廃止"""
    h = time.localtime().tm_hour
    return "morning" if h < 14 else "evening"


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


# 投稿に付ける位置情報「香芝市」(Facebookの場所ID。ユーザー指示 2026-11-14「位置情報を香芝市に」)。空にすると付けない
LOCATION_ID = os.environ.get("KITANO_IG_LOCATION_ID", "184510545004465")


def _container(user_id, token, image_url, caption, video_url, cover_url, location_id):
    """投稿の入れ物を作り、取り込み完了まで待つ(まだ公開はしない)"""
    d = {"caption": caption, "access_token": token}
    if video_url:
        d.update({"media_type": "REELS", "video_url": video_url, "cover_url": cover_url or image_url, "share_to_feed": "true"})
    else:
        d["image_url"] = image_url
    if location_id:
        d["location_id"] = location_id
    cid = api_post(f"{user_id}/media", d)["id"]
    for _ in range(60):  # 動画は取り込みに時間がかかる(最大5分待つ)
        s = requests.get(f"{API}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"container error: {s}")
        time.sleep(5)
    return cid


def publish(user_id, token, image_url, caption, video_url=None, cover_url=None):
    # 位置情報つきで入れ物を作る。断られたら位置なしで作り直す(公開前の段階だけやり直すので二重投稿にはならない)
    try:
        cid = _container(user_id, token, image_url, caption, video_url, cover_url, LOCATION_ID)
        if LOCATION_ID:
            print(f"LOCATION: 位置情報つき({LOCATION_ID})で作成")
    except RuntimeError as e:
        if not LOCATION_ID:
            raise
        print(f"LOCATION: 位置情報つきは失敗 → 位置なしで作り直します: {e}")
        cid = _container(user_id, token, image_url, caption, video_url, cover_url, None)
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
    cover_url = None
    if video_url:
        log(f"動画(リール): {video_url}")
        if (POSTS / "cover" / f"{item}.jpg").exists():
            cover_url = RAW_BASE + f"cover/{item}.jpg"
            log(f"表紙(9:16): {cover_url}")
        else:
            log("⚠ 表紙 posts/cover/ が無いので投稿画像(4:5)で代用します(左右が切れます)。python make_videos.py で作ってください")
    if dry:
        log("RESULT: DRY_RUN " + item)
        print(caption)
        return
    user_id = os.environ["KITANO_IG_USER_ID"]
    token = os.environ["KITANO_IG_ACCESS_TOKEN"]
    # 画像URLが公開されているか確認(push直後は数十秒かかることがある)
    for u in filter(None, [image_url, video_url, cover_url]):
        for _ in range(12):
            if requests.head(u, timeout=30).status_code == 200:
                break
            time.sleep(10)
    old = state["posted"].get(item, {})
    try:
        mid, url = publish(user_id, token, image_url, caption, video_url, cover_url)
    except RuntimeError as e:
        # 2026-11-09: media_publish が「Application request limit reached / action is blocked(2207051)」を返しても
        # 実際には投稿が出ていた(2回とも)。再試行すると二重投稿になるので、投稿済み扱いで記録して止める
        if "2207051" in str(e) or "action is blocked" in str(e):
            state["posted"][item] = {**old, "date": time.strftime("%Y-%m-%d %H:%M"), "media_id": "", "url": "",
                                     "category": category(item), "unconfirmed": True,
                                     "note": "API は action is blocked を返したが投稿は出ている可能性大。アプリで確認"}
            if slot:
                state["posted"][item]["slot"] = slot
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"RESULT: UNCONFIRMED {item} Instagram が「action is blocked」を返しました。投稿は出ていることが多いので、"
                f"アプリで確認してください(出ていなければ --slug {item} で出し直し)。マイビジネス・新着情報は出していません")
            return
        raise
    state["posted"][item] = {"date": time.strftime("%Y-%m-%d %H:%M"), "media_id": mid, "url": url, "category": category(item)}
    wsrc = state.get("works", {}).get("made", {}).get(item)
    if wsrc:   # ホームページの施工実績から作った投稿 → 元記事のURLも記録
        state["posted"][item]["works_url"] = wsrc.get("url", "")
    if old.get("wp"):
        state["posted"][item]["wp_refresh"] = True   # 出し直し → ホームページの記事も新しい内容で上書き(wp_post.py)
    if slot:
        state["posted"][item]["slot"] = slot
    elif old.get("slot") and old.get("date", "").startswith(time.strftime("%Y-%m-%d")):
        # 今日出した分を --slug で出し直したときは、その時間帯の1本として数えたままにする(予備が重ねて出さないように)
        state["posted"][item]["slot"] = old["slot"]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    # Googleマイビジネス用(画像 4:3 + ハッシュタグ無しの本文)を Google ドライブへ保存(失敗しても投稿結果には影響させない)
    # 2026-11-03〜 API 自動投稿に切り替えたのでドライブ保存は止めた(ユーザー指示)。戻すなら state.json に "gbp_drive": true
    gbp = ""
    try:
        if not state.get("gbp_drive", False):
            raise StopIteration
        import gbp_export
        gurl = gbp_export.save_for_gbp(item, state, state["posted"][item]["date"])
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        gbp = f" | マイビジネス用をドライブに保存: {gurl}"
        log(f"マイビジネス用をドライブに保存: {gurl}")
    except StopIteration:
        pass
    except Exception as e:
        gbp = f" | ⚠ マイビジネス用のドライブ保存に失敗: {str(e)[:120]}"
        log(f"⚠ マイビジネス用のドライブ保存に失敗(投稿は完了): {e}")
    # ブログ(~/kitano_blog/post_blog.py)で先にマイビジネス・新着情報へ出してあるネタは、ここでは重ねて出さない
    # (state.json の posted[slug]["manual_blog"] に記事URLを入れておく。2026-11-09〜)
    manual_blog = old.get("manual_blog") or state["posted"][item].get("manual_blog")
    if manual_blog:
        state["posted"][item]["manual_blog"] = manual_blog
        state["posted"][item]["wp"] = manual_blog
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"マイビジネス・新着情報はブログ側で投稿済みなので省略: {manual_blog}")
    # Googleビジネスプロフィール(マイビジネス)へ同じ内容を API で自動投稿(接続キーと投稿先がある時だけ。失敗しても止めない)
    try:
        import gbp_post
        if manual_blog:
            raise StopIteration
        if gbp_post.configured() and state.get("gbp_location") and state.get("gbp_auto"):
            purl = gbp_post.post_for(item, state)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            gbp += f" | マイビジネスに投稿: {purl}"
            log(f"マイビジネスに投稿: {purl}")
        else:
            log("マイビジネスAPI 自動投稿はオフ(state.json の gbp_auto が true で、キーと投稿先がある時だけ動く)")
    except StopIteration:
        pass
    except Exception as e:
        gbp += f" | ⚠ マイビジネス投稿に失敗: {str(e)[:160]}"
        log(f"⚠ マイビジネス投稿に失敗(Instagram は完了): {e}")
    # ホームページの「新着情報」(ブログ)にも同じ内容を投稿(2026-10-29〜。鍵がある時だけ。失敗しても止めない)
    try:
        import wp_post
        if manual_blog:
            raise StopIteration
        if wp_post.configured() and state.get("wp_auto", True):
            wurl = wp_post.post_for(item, state)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            gbp += f" | 新着情報に投稿: {wurl}"
            log(f"ホームページの新着情報に投稿: {wurl}")
        else:
            log("新着情報への自動投稿はオフ(Secrets KITANO_WP_APP_PASS が無い、または state.json の wp_auto が false)")
    except StopIteration:
        pass
    except Exception as e:
        gbp += f" | ⚠ 新着情報への投稿に失敗: {str(e)[:160]}"
        log(f"⚠ 新着情報への投稿に失敗(Instagram は完了): {e}")
    todo =[s for s in all_items() if s not in state["posted"]]
    stock = " ".join(f"{CATEGORY_NAMES[c]}{n}" for c, n in
                     sorted(((c, len([s for s in todo if category(s) == c])) for c in set(map(category, todo))), key=lambda x: -x[1]))
    web = web_waiting(state)
    webnote = f" | 次はWEB施工実績を優先: {' '.join(web[:3])}" if web else ""
    log(f"RESULT: POSTED {item} [{cat}] | {title} | {url} | 残り{len(todo)}本(1日2本なので約{len(todo) // 2}日分、内訳: {stock}){warn}{gbp}{webnote}")


if __name__ == "__main__":
    main()
