#!/usr/bin/env python3
"""Instagram に投稿したネタを、同じ内容でホームページの「新着情報」(ブログ)にも自動投稿する。

post_ig.py が Instagram への投稿に成功したあとに post_for() を呼ぶ(2026-10-29〜)。
  投稿先   … https://www.kashiba-yanereform.com/news/ (WordPress の投稿タイプ news、カテゴリ「ブログ」)
  題名     … content/auto_*.json の title(自動生成ネタ)。無ければ本文の1行目(絵文字を外して40字まで)
  本文     … ハッシュタグ無しの本文(連絡先の定型ブロックより前)＋ Instagram の埋め込み＋ Instagram へのリンク
  アイキャッチ … gbp_img/NN_slug.jpg(1200×900 横長。無ければ gbp_export.gbp_image() で作る)
  URL      … /news/ig-NN-slug/

認証: WordPress の REST API + アプリケーションパスワード(管理画面 > ユーザー > プロフィール で発行)。
  環境変数 KITANO_WP_USER(省略時 admin_kitano) / KITANO_WP_APP_PASS(GitHub Secrets)
  ※このサイトは /wp-json/ が 404 なので ?rest_route= 形式で呼ぶ。

使い方:
  python wp_post.py --check              # つながるか(ログインユーザーとカテゴリ一覧)
  python wp_post.py --test 13_amadoi     # 送る内容(題名・本文HTML)を表示するだけ
  python wp_post.py --one 13_amadoi      # その1本を今すぐ投稿(Instagram 投稿済みのもの)
  python wp_post.py --backfill           # Instagram 投稿済みで新着情報にまだ無いものを古い順に全部
  python wp_post.py --weather weather_YYYYMMDD  # 天気の投稿を新着情報へ(Instagram 投稿済みのもの)
  python wp_post.py --auto on|off        # 毎回の自動投稿のオン/オフ(state.json の wp_auto。初期はオン)
"""
import json, os, re, sys, time
from pathlib import Path

HERE = Path(__file__).parent
STATE = HERE / "state.json"
POSTS = HERE / "posts"
IMG_DIR = HERE / "gbp_img"
CONTENT = HERE / "content"
WP = "https://www.kashiba-yanereform.com/wp/?rest_route="
IG_PROFILE = "https://www.instagram.com/kashiba_yanereform/?hl=ja"
CATEGORY_NAME = "ブログ"       # category_news のカテゴリ名
CATEGORY_FALLBACK = 10          # 見つからないときの ID(2026-10-29 時点で「ブログ」=10)
TITLE_MAX = 40

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0001F900-\U0001F9FF"
    "←-⇿⌀-⏿■-◿✀-➿️‍⃣™ℹ〰〽㊗㊙]+")


def log(msg):
    print(msg, flush=True)


def configured():
    return bool(os.environ.get("KITANO_WP_APP_PASS"))


def _auth():
    return (os.environ.get("KITANO_WP_USER", "admin_kitano"), os.environ["KITANO_WP_APP_PASS"])


def _req(method, route, **kw):
    import requests
    kw.setdefault("timeout", 120)
    r = requests.request(method, WP + route, auth=_auth(), **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"WordPress {method} {route} → {r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------- 題名・本文 ----------------
def _auto_title(slug):
    """content/auto_*.json にそのネタの title があれば使う(改行は詰める)"""
    try:
        n, _, name = slug.partition("_")
        for f in sorted(CONTENT.glob("auto_*.json")):
            for it in json.loads(f.read_text(encoding="utf-8")):
                if it.get("slug") == name or (it.get("n") is not None and f"{int(it['n']):02d}" == n and it.get("slug") == name):
                    t = (it.get("title") or "").replace("\n", "")
                    if t:
                        return t
    except Exception:
        pass
    return ""


def clean_title(text):
    t = _EMOJI.sub("", text).strip()
    t = re.sub(r"\s+", " ", t).strip(" ・｜|")
    if len(t) > TITLE_MAX:
        m = re.match(r"^(.{8,%d}?[。！？!?])" % TITLE_MAX, t)   # 最初の文で切る
        t = m.group(1) if m else t[:TITLE_MAX - 1] + "…"
    return t


def title_for(slug):
    t = _auto_title(slug)
    if not t:
        raw = (POSTS / f"{slug}.txt").read_text(encoding="utf-8").strip()
        t = raw.split("\n", 1)[0]
    if slug.startswith("flyer_"):
        t = t or "今月のチラシ"
    return clean_title(t) or slug


def body_text(slug, folder=POSTS):
    """ハッシュタグ無し・連絡先の定型ブロック(────より後ろ)無しの本文"""
    raw = (folder / f"{slug}.txt").read_text(encoding="utf-8").strip()
    head = raw.split("────", 1)[0]
    lines = [ln for ln in head.split("\n") if not ln.strip().startswith("#")]
    text = "\n".join(lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def body_html(slug, ig_url, folder=POSTS):
    paras = [p for p in body_text(slug, folder).split("\n\n") if p.strip()]
    html = "\n".join("<p>" + "<br>\n".join(_esc(ln) for ln in p.split("\n")) + "</p>" for p in paras)
    if ig_url:
        html += (
            f'\n<div class="ig-embed-wrap"><blockquote class="instagram-media" data-instgrm-permalink="{_esc(ig_url)}" '
            f'data-instgrm-version="14" style="max-width:540px;min-width:280px;margin:24px auto;">'
            f'<a href="{_esc(ig_url)}" target="_blank" rel="noopener">この投稿をInstagramで見る</a></blockquote>'
            f'<script async src="https://www.instagram.com/embed.js"></script></div>'
            f'\n<p><a href="{_esc(ig_url)}" target="_blank" rel="noopener">▶ この投稿をInstagramで見る</a></p>'
        )
    html += (
        f'\n<p>Instagramでも工事の様子や屋根の豆知識を毎日更新しています → '
        f'<a href="{IG_PROFILE}" target="_blank" rel="noopener">@kashiba_yanereform</a></p>'
    )
    return html


def wp_slug(slug):
    return "ig-" + re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")


# ---------------- 画像 ----------------
def image_path(slug, folder=POSTS):
    p = IMG_DIR / f"{slug}.jpg"
    if not p.exists():
        import gbp_export
        IMG_DIR.mkdir(exist_ok=True)
        p.write_bytes(gbp_export.gbp_image(slug, folder=folder))
    return p


def upload_image(slug, title, folder=POSTS):
    p = image_path(slug, folder)
    data = p.read_bytes()
    import requests
    r = requests.post(WP + "/wp/v2/media", auth=_auth(), data=data, timeout=180, headers={
        "Content-Type": "image/jpeg",
        "Content-Disposition": f'attachment; filename="{wp_slug(slug)}.jpg"',
    })
    if r.status_code >= 400:
        raise RuntimeError(f"画像アップロード失敗 {r.status_code}: {r.text[:300]}")
    mid = r.json()["id"]
    _req("POST", f"/wp/v2/media/{mid}", json={"alt_text": title, "title": title})
    return mid


# ---------------- 投稿 ----------------
def category_id():
    try:
        for t in _req("GET", "/wp/v2/category_news&per_page=100"):
            if t["name"] == CATEGORY_NAME:
                return t["id"]
    except Exception:
        pass
    return CATEGORY_FALLBACK


def find_existing(slug):
    """同じ投稿名の記事が既にあれば、そのURLを返す(二重投稿しない)"""
    try:
        for p in _req("GET", f"/wp/v2/news&slug={wp_slug(slug)}&status=publish,draft"):
            return p["link"]
    except Exception:
        pass
    return None


def post_for(slug, state, when=None):
    rec = state["posted"].get(slug, {})
    if rec.get("wp"):
        return rec["wp"]
    existing = find_existing(slug)
    if existing:
        rec["wp"] = existing
        return existing
    ig_url = rec.get("url", "")
    if not when and rec.get("date"):
        when = rec["date"].replace(" ", "T") + ":00"   # サイトの日付は必ず Instagram の投稿日時に合わせる
    title = title_for(slug)
    mid = upload_image(slug, title)
    payload = {
        "title": title,
        "content": body_html(slug, ig_url),
        "status": "publish",
        "slug": wp_slug(slug),
        "featured_media": mid,
        "category_news": [category_id()],
    }
    if when:
        payload["date"] = when
    p = _req("POST", "/wp/v2/news", json=payload)
    link = p["link"]
    state["posted"].setdefault(slug, {})["wp"] = link
    state["posted"][slug]["wp_id"] = p["id"]
    return link


def post_weather(name, ig_url, when=None):
    """天気の投稿(weather/weather_YYYYMMDD)も新着情報へ(ユーザー指示 2026-10-30「Webへの投稿反映もいっしょに」)。
    post_weather.py が Instagram 投稿のあとに呼ぶ。題名は本文の1行目(例: 香芝市周辺の週間天気（11/1発表）)"""
    existing = find_existing(name)
    if existing:
        return existing
    folder = HERE / "weather"
    title = clean_title((folder / f"{name}.txt").read_text(encoding="utf-8").strip().split("\n", 1)[0]) or name
    mid = upload_image(name, title, folder)
    payload = {"title": title, "content": body_html(name, ig_url, folder), "status": "publish",
               "slug": wp_slug(name), "featured_media": mid, "category_news": [category_id()]}
    if when:
        payload["date"] = when
    return _req("POST", "/wp/v2/news", json=payload)["link"]


# ---------------- CLI ----------------
def main():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    args = sys.argv[1:]
    if "--auto" in args:
        v = args[args.index("--auto") + 1]
        state["wp_auto"] = (v == "on")
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"新着情報への自動投稿: {'オン' if state['wp_auto'] else 'オフ'}")
        return
    if "--check" in args:
        me = _req("GET", "/wp/v2/users/me")
        log(f"ログイン OK: {me.get('name')} (id {me.get('id')})")
        for t in _req("GET", "/wp/v2/category_news&per_page=100"):
            log(f"  カテゴリ {t['id']}: {t['name']} ({t['count']}件)")
        log(f"投稿先カテゴリ: {CATEGORY_NAME} = {category_id()}")
        return
    if "--test" in args:
        slug = args[args.index("--test") + 1]
        ig_url = state["posted"].get(slug, {}).get("url", "(未投稿)")
        log(f"題名: {title_for(slug)}\nURL: /news/{wp_slug(slug)}/\n画像: {image_path(slug)}\nInstagram: {ig_url}\n---\n{body_html(slug, ig_url if ig_url.startswith('http') else '')}")
        return
    if "--one" in args:
        slug = args[args.index("--one") + 1]
        link = post_for(slug, state)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"投稿しました: {link}")
        return
    if "--weather" in args:
        name = args[args.index("--weather") + 1]
        rec = next((r for d, r in sorted(state.get("weather", {}).items()) if r.get("name") == name), {})
        link = post_weather(name, rec.get("url", ""))
        if rec:
            rec["wp"] = link
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"投稿しました: {link}")
        return
    if "--backfill" in args:
        items = sorted(state["posted"].items(), key=lambda kv: kv[1].get("date", ""))
        for slug, rec in items:
            if rec.get("wp") or not (POSTS / f"{slug}.txt").exists():
                continue
            when = rec.get("date", "").replace(" ", "T") + ":00" if rec.get("date") else None
            link = post_for(slug, state, when)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"{slug} → {link}")
            time.sleep(2)
        return
    log(__doc__)


if __name__ == "__main__":
    main()
