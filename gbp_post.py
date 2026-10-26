#!/usr/bin/env python3
"""Instagram に投稿したネタを、同じ内容で Googleビジネスプロフィール(マイビジネス)にも自動投稿する。

post_ig.py が投稿に成功したあと(ドライブ保存のあと)に post_for() を呼ぶ。
  本文  … gbp_export.gbp_text()(ハッシュタグ無し・ホームページURL入り、1500字以内)
  写真  … gbp_img/NN_slug.jpg(1200×900 横長。gbp_export.py --images が作り、リポジトリに commit 済みのもの)を
           raw.githubusercontent.com の公開URLで渡す(Google 側が取りに来る)
  ボタン … 「詳細」→ ホームページ
投稿の種類は「最新情報」(STANDARD)。

認証: Google 広告・ドライブと同じ OAuth クライアント + business.manage 権限。
  環境変数 GBP_CLIENT_ID / GBP_CLIENT_SECRET / GBP_REFRESH_TOKEN(GitHub Secrets)
  手元では 〜/google_ads/gbp_creds.json(get_token_gbp.py が作る)
投稿先の店舗は state.json の "gbp_location" に記録({"account": "accounts/…", "location": "locations/…", "title": "北野工作所"})。
無いときは --setup で一覧から選んで記録する。

※ ビジネスプロフィール API は Google に申請して承認されるまで使えない(未承認だと 403/429 で「quota」や
  「not enabled」と返ってくる)。承認前でも post_ig.py は止まらない(⚠ を付けて Instagram だけ続ける)。

使い方:
  python gbp_post.py --check              # つながるか・見える店舗の一覧
  python gbp_post.py --setup [北野]        # 投稿先の店舗を state.json に記録(名前の一部で絞る)
  python gbp_post.py --test 13_amadoi     # 送る内容を表示するだけ
  python gbp_post.py --one 13_amadoi      # その1本を今すぐ投稿
  python gbp_post.py --list               # 最近の投稿(API 経由で見えるもの)
"""
import json, os, sys, time
from pathlib import Path

HERE = Path(__file__).parent
STATE = HERE / "state.json"
IMG_DIR = HERE / "gbp_img"
RAW_IMG = "https://raw.githubusercontent.com/fujimori-ui/kitano-ig-post/main/gbp_img/"
SITE_URL = "https://kashiba-yanereform.com/"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCT = "https://mybusinessaccountmanagement.googleapis.com/v1"
INFO = "https://mybusinessbusinessinformation.googleapis.com/v1"
V4 = "https://mybusiness.googleapis.com/v4"


def _creds():
    cid, sec, rt = (os.environ.get("GBP_CLIENT_ID"), os.environ.get("GBP_CLIENT_SECRET"),
                    os.environ.get("GBP_REFRESH_TOKEN"))
    if not (cid and sec and rt):
        f = Path.home() / "google_ads" / "gbp_creds.json"
        if f.exists():
            j = json.loads(f.read_text())
            cid, sec, rt = j["client_id"], j["client_secret"], j["refresh_token"]
    if not (cid and sec and rt):
        return None
    return cid, sec, rt


def configured():
    """接続キーがあるか(無ければ post_ig.py は何もしない)"""
    return _creds() is not None


class ApiError(RuntimeError):
    pass


class GBP:
    def __init__(self):
        import requests
        self.rq = requests
        c = _creds()
        if not c:
            raise ApiError("ビジネスプロフィールの接続情報(GBP_CLIENT_ID/SECRET/REFRESH_TOKEN)がありません")
        r = requests.post(TOKEN_URL, data={"client_id": c[0], "client_secret": c[1], "refresh_token": c[2],
                                           "grant_type": "refresh_token"}, timeout=30).json()
        if "access_token" not in r:
            raise ApiError(f"トークン取得に失敗: {r}")
        self.h = {"Authorization": f"Bearer {r['access_token']}"}

    def _call(self, method, url, **kw):
        r = self.rq.request(method, url, headers=self.h, timeout=60, **kw)
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:300]}
        if r.status_code >= 300:
            msg = j.get("error", {}).get("message", "") if isinstance(j, dict) else ""
            hint = ""
            if r.status_code in (403, 429) and ("quota" in msg.lower() or "not been used" in msg.lower()
                                                or "not enabled" in msg.lower() or "PERMISSION" in msg):
                hint = "(ビジネスプロフィール API がまだ未承認・未有効の可能性。README_GBP.md の申請手順を確認)"
            raise ApiError(f"HTTP {r.status_code} {method} {url.split('?')[0]}: {msg or j} {hint}")
        return j

    def accounts(self):
        return self._call("GET", f"{ACCT}/accounts", params={"pageSize": 20}).get("accounts", [])

    def locations(self, account):
        """account = 'accounts/123'。店舗の一覧(名前・住所)"""
        out, token = [], None
        while True:
            p = {"readMask": "name,title,storefrontAddress,metadata", "pageSize": 100}
            if token:
                p["pageToken"] = token
            j = self._call("GET", f"{INFO}/{account}/locations", params=p)
            out += j.get("locations", [])
            token = j.get("nextPageToken")
            if not token:
                return out

    def create_post(self, account, location, summary, image_url, cta_url=SITE_URL):
        """account='accounts/123', location='locations/456'。最新情報(STANDARD)+写真+「詳細」ボタン"""
        body = {"languageCode": "ja", "summary": summary, "topicType": "STANDARD",
                "callToAction": {"actionType": "LEARN_MORE", "url": cta_url},
                "media": [{"mediaFormat": "PHOTO", "sourceUrl": image_url}]}
        return self._call("POST", f"{V4}/{account}/{location}/localPosts", json=body)

    def list_posts(self, account, location, n=10):
        j = self._call("GET", f"{V4}/{account}/{location}/localPosts", params={"pageSize": n})
        return j.get("localPosts", [])


def image_url(slug):
    return RAW_IMG + f"{slug}.jpg"


def wait_public(url, tries=12):
    """push 直後は raw URL が 404 のことがあるので少し待つ"""
    import requests
    for _ in range(tries):
        if requests.head(url, timeout=30).status_code == 200:
            return True
        time.sleep(10)
    return False


def post_for(slug, state):
    """1本ぶんをビジネスプロフィールへ。state['posted'][slug]['gbp_post'] に記録して検索URLを返す"""
    import gbp_export
    loc = state.get("gbp_location")
    if not loc:
        raise ApiError("投稿先の店舗が未設定です(python gbp_post.py --setup)")
    if not (IMG_DIR / f"{slug}.jpg").exists():
        raise ApiError(f"gbp_img/{slug}.jpg がありません(python gbp_export.py --images で作って push)")
    url = image_url(slug)
    if not wait_public(url):
        raise ApiError(f"写真の公開URLがまだ見えません: {url}")
    text = gbp_export.gbp_text(slug)
    j = GBP().create_post(loc["account"], loc["location"], text, url)
    rec = state.setdefault("posted", {}).setdefault(slug, {})
    rec["gbp_post"] = {"name": j.get("name", ""), "state": j.get("state", ""), "url": j.get("searchUrl", ""),
                       "date": time.strftime("%Y-%m-%d %H:%M")}
    return j.get("searchUrl") or j.get("name", "")


def main():
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"posted": {}}
    if "--test" in sys.argv:
        import gbp_export
        slug = sys.argv[sys.argv.index("--test") + 1]
        print("写真:", image_url(slug), "(ローカルに有り)" if (IMG_DIR / f"{slug}.jpg").exists() else "(⚠ gbp_img に無い)")
        print("ボタン: 詳細 →", SITE_URL)
        print("投稿先:", state.get("gbp_location") or "⚠ 未設定(--setup)")
        print("---- 本文 ----")
        print(gbp_export.gbp_text(slug))
        return
    if "--check" in sys.argv:
        g = GBP()
        accs = g.accounts()
        print(f"アカウント {len(accs)}件")
        for a in accs:
            print(" ", a.get("name"), "|", a.get("accountName"), "|", a.get("type"), a.get("role", ""))
            for l in g.locations(a["name"]):
                ad = l.get("storefrontAddress", {})
                print("    店舗:", l.get("name"), "|", l.get("title"), "|", " ".join(ad.get("addressLines", [])),
                      "| 地図:", l.get("metadata", {}).get("mapsUri", ""))
        print("投稿先(state.json):", state.get("gbp_location") or "未設定")
        return
    if "--setup" in sys.argv:
        i = sys.argv.index("--setup")
        key = sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("--") else "北野"
        g = GBP()
        hits = []
        for a in g.accounts():
            for l in g.locations(a["name"]):
                if key in (l.get("title") or ""):
                    hits.append((a["name"], l))
        if len(hits) != 1:
            print(f"「{key}」に当たる店舗が {len(hits)} 件。--check で一覧を見て、名前を指定してください")
            for a, l in hits:
                print(" ", a, l.get("name"), l.get("title"))
            sys.exit(1)
        a, l = hits[0]
        state["gbp_location"] = {"account": a, "location": l["name"], "title": l.get("title")}
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print("投稿先を記録:", state["gbp_location"])
        return
    if "--list" in sys.argv:
        loc = state["gbp_location"]
        for p in GBP().list_posts(loc["account"], loc["location"]):
            print(p.get("createTime", "")[:16], p.get("state"), (p.get("summary") or "")[:40].replace("\n", " "), p.get("searchUrl", ""))
        return
    if "--one" in sys.argv:
        slug = sys.argv[sys.argv.index("--one") + 1]
        print("投稿:", post_for(slug, state))
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
