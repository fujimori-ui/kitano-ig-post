#!/usr/bin/env python3
"""ホームページの「施工実績」(https://www.kashiba-yanereform.com/works/)を定期的に見て、
新しい記事があれば Instagram 用のストーリー動画(make_story.py)を自動で作り、優先的に投稿する(2026-11-14〜 ユーザー指示
「施工実績も投稿。WEBを定期的に見て優先的に投稿する仕組みにしたい」)。

流れ(works.yml が毎日 5:30 / 18:30 JST に実行。post.yml も投稿前に --check で新着を見つけたら works.yml を起動):
  1. WordPress の REST API(/wp-json/wp/v2/works)で施工実績の一覧を取る
  2. state.json の works.seen(見た記事のID)に無いものが「新着」。
     ただし ~/kitano_blog(別PC)のブログツールがすでに Instagram に出した記事(state の manual_blog / wp に同じ slug がある)は作らない
  3. 記事の写真(アイキャッチ＋本文の写真。-300x225 の縮小版は元のサイズに直す)を content/works_photos/<記事slug>/ に保存
  4. 記事の文章から場面(施工前→作業中→施工後)を組み立てて content/story_web_YYYYMMDD_<slug>.json に書き、
     make_story.py で posts/NN_jirei_web_<slug>_story.{mp4,jpg,txt} と posts/cover/ を作る
  5. 投稿名に "_web_" が入っているものは post_ig.py がチラシの次に優先して出す(次の朝7時/夜20時の枠)
  6. state.json の works に記録(seen / made)。初回は導入日(2026-11-14)までの記事を「見た」ことにして何も作らない
     (それ以前の施工実績は 03〜 や 130〜136 でもう投稿してある)

使い方:
  python works_watch.py                 # 新着を全部作る。最後に「MADE slug …」(works.yml が commit に使う)
  python works_watch.py --check         # 新着の数だけ表示(「NEW 2」)。作らない・state も変えない(post.yml 用)
  python works_watch.py --force 310     # 記事ID(または記事slug)を指定して作り直す(見た記事でも作る)
  python works_watch.py --force 310 --test   # 試しに作るだけ(state を変えない。works.yml の test でも使う)
必要: requests, Pillow, numpy, ffmpeg(make_story.py が使う)
"""
import datetime, html, json, re, sys, time
from pathlib import Path

import requests

HERE = Path(__file__).parent
STATE = HERE / "state.json"
POSTS = HERE / "posts"
CONTENT = HERE / "content"
PHOTOS = CONTENT / "works_photos"
SITE = "https://www.kashiba-yanereform.com"
# /wp-json/ はサーバーの設定で海外IP(GitHub Actions)から 403 になる(2026-11-14 に判明)ので、
# wp_post.py と同じ ?rest_route= の形で取る(こちらは通る)。だめなら /wp-json/ も試し、鍵(KITANO_WP_APP_PASS)があれば認証付きでも試す
API_URLS = [SITE + "/wp/?rest_route=/wp/v2/works", SITE + "/wp-json/wp/v2/works"]
INSTALL_DATE = "2026-11-14"      # この日までの記事は初回に「見た」扱い(すでに投稿してある)
MAX_SCENES = 4                   # 写真の場面は最大4つ(＋最後の一言)
TITLE_MAX = 15                   # 黄色帯の見出し(make_story.py の目安)
SUB_MAX = 56                     # 見出しの下の説明(34px で2行)
CAP_MAX = 900                    # Instagram 本文(CTA・ハッシュタグは別に付く)
UA = {"User-Agent": "kitano-ig-post works_watch (GitHub Actions)"}


def log(msg):
    print(msg, flush=True)


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"posted": {}}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 記事を取る ----------------
def fetch_works():
    import os
    params = {"per_page": 50, "_embed": 1, "orderby": "date", "order": "asc"}
    auth = None
    if os.environ.get("KITANO_WP_APP_PASS"):
        auth = (os.environ.get("KITANO_WP_USER", "admin_kitano"), os.environ["KITANO_WP_APP_PASS"])
    last = None
    for a in ([None, auth] if auth else [None]):
        for url in API_URLS:
            try:
                r = requests.get(url, params=params, headers=UA, auth=a, timeout=60)
                if r.status_code == 200:
                    return r.json()
                last = f"{url} → {r.status_code}"
                log(f"  取れず: {last}{' (認証付き)' if a else ''}")
            except Exception as e:
                last = f"{url} → {str(e)[:100]}"
                log(f"  取れず: {last}")
    raise RuntimeError(f"施工実績の一覧が取れません: {last}")


def blog_slugs(state):
    """ブログツール(別PC)が先に Instagram へ出した記事の slug(manual_blog / wp の URL から)"""
    out = set()
    for sec in ("posted", "replaced"):
        for v in state.get(sec, {}).values():
            for k in ("manual_blog", "wp", "works_url"):
                u = v.get(k) or ""
                m = re.search(r"/(?:news|works)/(?:blog-)?([a-z0-9-]+)/?$", u)
                if m:
                    out.add(m.group(1))
    return out


def new_works(state, works):
    ws = state.get("works")
    if ws is None:
        # 初回: 導入日までの記事は見たことにする(すでに 03〜14・130〜136・126〜129 などで投稿済み)
        ws = {"seen": [w["id"] for w in works if w["date"][:10] <= INSTALL_DATE], "made": {}}
        state["works"] = ws
        log(f"初回: {len(ws['seen'])}件の既存記事を既読にしました(導入日 {INSTALL_DATE} まで)")
    seen = set(ws["seen"])
    done = blog_slugs(state)
    out = []
    for w in works:
        if w["id"] in seen:
            continue
        if w["slug"] in done:
            log(f"skip {w['id']} {w['slug']}: ブログツール側ですでに Instagram に投稿済み")
            ws["seen"].append(w["id"])
            continue
        out.append(w)
    return out


# ---------------- 文章の整理 ----------------
MARKERS = {"施工前": "施工前", "工事前": "施工前", "ビフォー": "施工前", "Before": "施工前",
           "施工中": "作業中", "作業中": "作業中", "工事中": "作業中",
           "施工後": "施工後", "工事後": "施工後", "完成": "施工後", "アフター": "施工後", "After": "施工後"}
GREETING = re.compile(r"^(こんにちは|こんばんは|おはようございます|いつもありがとう)")
CTA_WORDS = ("専門店です", "お見積りは無料", "お気軽にご相談", "おまかせください", "全力で対応")


def tokens(content_html):
    """本文HTMLを [("img", url) / ("text", 段落)] の順番つきリストにする"""
    out = []
    for t in re.split(r"(<img[^>]*>)", content_html):
        if t.startswith("<img"):
            m = re.search(r'src="([^"]+)"', t)
            if m:
                out.append(("img", m.group(1)))
            continue
        t = re.sub(r"<(?:p|br|h\d|li|div|figure|figcaption|tr|/p|/h\d|/li|/div|/figure|/tr)[^>]*>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
        for p in t.split("\n"):
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                out.append(("text", p))
    return out


def marker_of(text):
    """「【施工前】」「施工後の様子：…」のような見出し行なら 施工前/作業中/施工後 を返す"""
    s = text.strip("【】[]＜＞<> ")
    if len(s) > 22:
        return None
    for k, v in MARKERS.items():
        if s.startswith(k) or s.startswith("■" + k) or s.startswith("▼" + k):
            return v
    return None


def sentences(text):
    return [s for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]


def short_title(text, limit=TITLE_MAX):
    """最初の文を見出しの長さに。長ければ「、」で区切った前の部分、それでも長ければ切って…"""
    s = sentences(text)[0].strip() if text.strip() else ""
    s = re.sub(r"[。！？!?]$", "", s).strip()
    s = re.sub(r"^(こちらが|こちらは|今回は|まず|さらに|そして|また)、?", "", s)
    s = s.strip("「」")
    if len(s) <= limit:
        return s
    parts = re.split(r"[、，,]", s)
    acc = ""
    for p in parts:
        if len(acc + ("、" if acc else "") + p) <= limit:
            acc = acc + ("、" if acc else "") + p
        else:
            break
    if len(acc) >= 8:
        return acc
    return s[:limit - 1] + "…"


def short_sub(text, skip_first=False, limit=SUB_MAX):
    """説明(2行まで)。skip_first=True なら見出しに使った1文目を除いた残りから"""
    ss = sentences(text)
    if skip_first and len(ss) > 1:
        ss = ss[1:]
    acc = ""
    for s in ss:
        if len(acc + s) <= limit:
            acc += s
        else:
            break
    if not acc and ss:                      # 1文が長すぎるときは「、」までで切る(…は使わない)
        m = re.match(r"^(.{10,%d}?[、，])" % (limit - 1), ss[0])
        acc = m.group(1).rstrip("、，") + "。" if m else ss[0][:limit - 1] + "…"
    return acc.strip()


def full_image_url(u):
    """-300x225 などの縮小版は元のサイズに。http → https"""
    u = re.sub(r"^http://", "https://", u)
    return re.sub(r"-\d{2,4}x\d{2,4}(?=\.\w+$)", "", u)


def download(url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1])
    dest = folder / name
    for cand in dict.fromkeys([full_image_url(url), re.sub(r"^http://", "https://", url)]):
        try:
            r = requests.get(cand, headers=UA, timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                dest.write_bytes(r.content)
                from PIL import Image
                im = Image.open(dest); im.load()
                if im.width < 400:
                    log(f"  小さすぎる写真なので使いません: {cand} ({im.width}px)")
                    dest.unlink(missing_ok=True)
                    return None
                return dest
        except Exception as e:
            log(f"  取得できず: {cand} ({str(e)[:80]})")
    return None


def area_of(w):
    for grp in w.get("_embedded", {}).get("wp:term", []):
        for t in grp:
            if t.get("taxonomy") == "works_area":
                return t["name"]
    m = re.search(r"[（(]([^）)]{2,6}(?:市|町|村))[）)]", w["title"]["rendered"])
    return m.group(1) if m else "香芝市"


def main_title(w):
    t = html.unescape(w["title"]["rendered"])
    t = re.sub(r"[（(][^）)]*[）)]\s*$", "", t)          # 末尾の(香芝市)
    t = re.split(r"[｜|]", t)[0].strip()
    t = re.sub(r"[！!]+$", "", t).strip()
    return t


def build_story(w, n, slug):
    """1記事 → make_story.py 用の JSON(写真は content/works_photos/ に保存)"""
    toks = tokens(w["content"]["rendered"])
    area = area_of(w)
    title = main_title(w)
    folder = PHOTOS / w["slug"]
    # 写真ごとに「直前の見出し(施工前など)」と「その写真のあとの文章(次の写真まで)」を集める
    sections = []          # {"url", "marker", "before": [段落], "after": [段落]}
    intro = []             # 最初の写真より前の文章
    cur_marker = None
    pending = []
    for kind, val in toks:
        if kind == "text":
            mk = marker_of(val)
            if mk:
                cur_marker = mk
                continue
            if GREETING.match(val):
                continue
            (sections[-1]["after"] if sections else intro).append(val)
            pending.append(val)
        else:
            sections.append({"url": val, "marker": cur_marker, "after": [], "before": pending[-1:] if not sections else []})
            cur_marker = None
            pending = []
    # 文章から場面を作る
    featured = (w.get("_embedded", {}).get("wp:featuredmedia") or [{}])[0].get("source_url")
    scenes = []
    lead_src = intro or (sections[0]["after"] if sections else [])
    lead = ""
    for p in lead_src:
        if "お話です" in p or "ご紹介します" in p:   # 「〜の現場のお話です」は導入なので説明には使わない
            continue
        lead = short_sub(p)
        if lead:
            break
    first_photo = None
    if featured:
        first_photo = download(featured, folder)
    photos = []
    for sec in sections:
        p = download(sec["url"], folder)
        if p:
            photos.append((p, sec))
    if not first_photo and photos:
        first_photo = photos[0][0]
    if not first_photo:
        raise RuntimeError(f"{w['slug']}: 使える写真がありません")
    scenes.append({"photo": first_photo.relative_to(HERE).as_posix(), "pill": f"施工事例・{area}",
                   "title": short_title(title) if len(title) <= TITLE_MAX else short_title(title), "sub": lead, "sec": 3.5})
    # 施工前/作業中/施工後 の割り当て(見出しが無ければ順番で)
    k = len(photos)
    default = {1: ["工事の様子"], 2: ["施工前", "施工後"], 3: ["施工前", "作業中", "施工後"]}.get(k) or \
              ["施工前"] + ["作業中"] * (k - 2) + ["施工後"]
    fallback_title = {"施工前": "工事前の様子", "作業中": "工事の様子", "施工後": "きれいに仕上がりました", "工事の様子": "工事の様子"}
    use = photos[:MAX_SCENES - 1]
    if k > MAX_SCENES - 1:                       # 多いときは最初・途中・最後
        use = [photos[0], photos[k // 2], photos[-1]]
    for i, (p, sec) in enumerate(use):
        label = sec["marker"] or default[photos.index((p, sec))]
        src = [t for t in (sec["after"] or sec["before"]) if not t.startswith(("・", "【", "■", "▼", "☑", "✓", "「")) and len(t) >= 12]
        text = " ".join(src[:2])
        t = short_title(text) if text else fallback_title.get(label, label)
        sub = short_sub(text, skip_first=True) if text else ""
        if not sub and text:
            sub = short_sub(text)
        circled = "①②③④"[i]
        scenes.append({"photo": p.relative_to(HERE).as_posix(), "pill": f"{circled} {label}", "title": t or fallback_title.get(label, label),
                       "sub": sub, "sec": 4.5 if i == 0 else 4.0})
    # 本文(Instagram)。見出し行は【】のまま、最後の宣伝文(CTA は別に付く)は外す
    paras = []
    for kind, val in toks:
        if kind != "text" or GREETING.match(val):
            continue
        mk = marker_of(val)
        if mk:
            paras.append(f"【{mk}】")
            continue
        paras.append(val)
    while paras and (any(wd in paras[-1] for wd in CTA_WORDS) or paras[-1].startswith("【")):
        paras.pop()
    cap = f"【動画で見る 施工事例】{title}🎬({area})\n\n"
    body = ""
    for p in paras:
        if p.startswith(("・", "【", "■", "▼", "☑", "✓")) or len(p) < 12:
            add = p + "\n"
        else:
            add = p + "\n\n"
        if len(cap) + len(body) + len(add) > CAP_MAX:
            break
        body += add
    cap += body.strip() + "\n\nホームページの「施工実績」にも、この工事の写真をくわしく載せています。"
    end = {"pill": "点検・お見積りは無料", "title": "小さな工事こそ、お気軽に",
           "lines": ["「こんなことで頼んでいいのかな？」で大丈夫です。",
                     f"創業106年、{area if area.endswith(('市', '町', '村')) else '香芝市'}の屋根・雨樋・板金の専門店です。",
                     "★ 気になったら、まず無料点検をご利用ください。"],
           "note": "お電話・LINE・DM(メッセージ)でどうぞ", "sec": 5.5}
    return {"slug": slug, "n": n, "works_id": w["id"], "works_url": w["link"], "works_title": html.unescape(w["title"]["rendered"]),
            "cap": cap, "scenes": scenes, "end": end}


def next_number():
    nums = [int(m.group(1)) for p in POSTS.glob("*.jpg") for m in [re.match(r"^(\d+)_", p.stem)] if m]
    return max(nums + [0]) + 1


def ig_slug(w):
    s = re.sub(r"[^a-z0-9]+", "_", w["slug"].lower()).strip("_")
    s = re.sub(r"^post_", "post", s)
    if len(s) > 26:
        s = s[:26].rstrip("_")
    return f"jirei_web_{s}_story"


def make_one(w, state, test=False):
    n = next_number()
    slug = ig_slug(w)
    full = f"{n:02d}_{slug}"
    log(f"作成: {full} ← {w['link']} / {html.unescape(w['title']['rendered'])}")
    a = build_story(w, n, slug)
    CONTENT.mkdir(exist_ok=True)
    jpath = CONTENT / f"story_web_{time.strftime('%Y%m%d')}_{w['slug'][:30]}.json"
    jpath.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    for sc in a["scenes"]:
        log(f"  場面 [{sc['pill']}] {sc['title']} / {sc['sub']}")
    import make_story
    make_story.main(a)
    if not test:
        ws = state["works"]
        if w["id"] not in ws["seen"]:
            ws["seen"].append(w["id"])
        ws["made"][full] = {"id": w["id"], "url": w["link"], "title": a["works_title"], "date": time.strftime("%Y-%m-%d %H:%M"),
                            "json": jpath.relative_to(HERE).as_posix()}
    return full


def find_work(works, key):
    for w in works:
        if str(w["id"]) == str(key) or w["slug"] == key:
            return w
    return None


def main():
    argv = sys.argv[1:]
    test = "--test" in argv
    state = load_state()
    works = fetch_works()
    log(f"施工実績 {len(works)}件(最新: {works[-1]['date'][:10]} {html.unescape(works[-1]['title']['rendered'])})" if works else "施工実績 0件")
    if "--force" in argv:
        key = argv[argv.index("--force") + 1]
        w = find_work(works, key)
        if not w:
            log(f"RESULT: NOT_FOUND {key}"); sys.exit(1)
        state.setdefault("works", {"seen": [], "made": {}})
        full = make_one(w, state, test=test)
        if not test:
            save_state(state)
        log(f"MADE {full}")
        log(f"RESULT: MADE {full}" + (" (test: state は変えていません)" if test else ""))
        return
    fresh = new_works(state, works)
    if "--check" in argv:
        log("NEW " + str(len(fresh)) + ("  " + " / ".join(html.unescape(w["title"]["rendered"]) for w in fresh) if fresh else ""))
        return
    made = []
    for w in fresh:
        try:
            made.append(make_one(w, state, test=test))
        except Exception as e:
            log(f"⚠ {w['slug']} の作成に失敗: {e}")
            if not test:
                state["works"].setdefault("failed", {})[str(w["id"])] = {"slug": w["slug"], "error": str(e)[:200], "date": time.strftime("%Y-%m-%d %H:%M")}
    if not test:
        state.setdefault("works", {"seen": [], "made": {}})["checked"] = time.strftime("%Y-%m-%d %H:%M")
        save_state(state)
    log("MADE " + " ".join(made))
    log(f"RESULT: {'MADE ' + ' '.join(made) if made else 'NO_NEW 新しい施工実績はありません'}")


if __name__ == "__main__":
    main()
