#!/usr/bin/env python3
"""Instagram に投稿したネタを「Googleマイビジネス(ビジネスプロフィール)用」に整えて Google ドライブへ保存する。

post_ig.py が投稿に成功するたびに save_for_gbp() を呼び、ドライブの
  北野工作所_マイビジネス投稿用/
    使い方.txt
    2026-10-26_1230_13_amadoi/
      画像.jpg   … 1200×900(マイビジネス推奨の横長 4:3)。投稿画像を中央に置き、まわりはぼかした同じ画像
      本文.txt   … ハッシュタグを外し、リンク行をホームページURLに替えた本文(1500字以内)
を作る。ユーザーはスマホの Google ドライブ → 画像と本文をコピー → ビジネスプロフィールの「投稿を追加」に貼る。

認証は Google 広告 API と同じ OAuth クライアント(〜/google_ads/client_secret.json)に
ドライブ権限(drive.file = このアプリが作ったファイルだけ)を足したもの。
環境変数 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN(GitHub Secrets)。
手元では 〜/google_ads/gdrive_creds.json(get_token_gdrive.py が作る)を読む。
保存先フォルダの ID は state.json の "gbp_folder_id" に記録(無ければマイドライブ直下に作る。
ユーザーがフォルダをドライブ内で移動しても ID は変わらないので追従する)。

使い方:
  python gbp_export.py --test 13_amadoi        # 画像と本文を gbp_preview/ に書き出すだけ(ドライブに送らない)
  python gbp_export.py --one 13_amadoi         # その1本をドライブへ保存
  python gbp_export.py --backfill              # 投稿済みでまだドライブに無いものを全部保存
"""
import datetime, io, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).parent
POSTS = HERE / "posts"
STATE = HERE / "state.json"
ROOT_NAME = "北野工作所_マイビジネス投稿用"
SITE_URL = "https://kashiba-yanereform.com/"
GBP_MAX = 1500          # ビジネスプロフィールの投稿本文の上限(文字)
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

GUIDE = """【北野工作所 Googleビジネスプロフィール(マイビジネス)投稿用フォルダ】

Instagram に自動投稿されるたびに、同じ内容の「マイビジネス用」がここに1フォルダずつ増えます。
フォルダ名 = 投稿した日付_時刻_ネタ名(例 2026-10-26_1230_13_amadoi)

■ 中身
・画像.jpg … マイビジネス推奨の横長(1200×900)に整えた画像
・本文.txt … ハッシュタグを外し、リンク行をホームページURLに替えた本文(そのまま貼れます)

■ スマホからの投稿手順(約1分)
1. このフォルダの「本文.txt」を開く → 文章を全部コピー
2. Google マップのアプリ(またはビジネスプロフィールの管理画面)で 北野工作所 → 「投稿を追加」→「最新情報」
3. 「写真を追加」→ Google ドライブ → このフォルダの「画像.jpg」を選ぶ
4. 本文を貼り付け
5. ボタンを追加 → 「詳細」→ https://kashiba-yanereform.com/ (電話なら「今すぐ電話」でもOK)
6. 投稿

※ 1日3本すべて出す必要はありません。1日1本、目についたものだけでも十分効果があります。
※ 古いフォルダは消して構いません(Instagram 側には影響しません)。
"""


# ---------------- 本文 ----------------
def gbp_text(slug):
    """IG の本文(txt)をマイビジネス用に。ハッシュタグ行を外し、プロフィールリンクの行をURLに替える。1500字に収める"""
    raw = (POSTS / f"{slug}.txt").read_text(encoding="utf-8").strip()
    lines = []
    for ln in raw.split("\n"):
        s = ln.strip()
        if s.startswith("#"):                       # ハッシュタグの行は丸ごと外す
            continue
        if "プロフィールのリンク" in s:              # IG だけの言い回し → ホームページURL
            ln = f"🔗 ホームページ {SITE_URL}"
        lines.append(ln)
    # 末尾の空行・区切り線の整理
    text = "\n".join(lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if len(text) > GBP_MAX:
        # 長すぎるときは区切り線より前(本文)を詰める
        head, sep, tail = text.partition("────────────")
        room = GBP_MAX - len(sep + tail) - 2
        text = head[:max(room, 0)].rstrip() + "…\n" + sep + tail if sep else text[:GBP_MAX - 1] + "…"
    return text


# ---------------- 画像 ----------------
def gbp_image(slug, size=(1200, 900)):
    """投稿画像(4:5)を 4:3 の横長に。中央に元画像、まわりは同じ画像をぼかして敷く(左右が切れない)"""
    from PIL import Image, ImageFilter, ImageEnhance
    src = Image.open(POSTS / f"{slug}.jpg").convert("RGB")
    W, H = size
    # 背景: 元画像を画面いっぱいに拡大 → ぼかし → 少し明るく
    scale = max(W / src.width, H / src.height)
    bg = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(28))
    bg = ImageEnhance.Brightness(bg).enhance(1.12)
    bg = Image.blend(bg, Image.new("RGB", (W, H), (219, 247, 254)), 0.35)   # 薄い水色を重ねてやわらかく
    # 前景: 元画像を高さいっぱい(白ふち付き)
    pad = 10
    fh = H - pad * 2
    fw = round(src.width * fh / src.height)
    fg = src.resize((fw, fh), Image.LANCZOS)
    x = (W - fw) // 2
    from PIL import ImageDraw
    d = ImageDraw.Draw(bg)
    d.rectangle([x - pad, 0, x + fw + pad, H], fill=(255, 255, 255))
    bg.paste(fg, (x, pad))
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


# ---------------- Google ドライブ ----------------
def _creds():
    cid, sec, rt = (os.environ.get("GDRIVE_CLIENT_ID"), os.environ.get("GDRIVE_CLIENT_SECRET"),
                    os.environ.get("GDRIVE_REFRESH_TOKEN"))
    if not (cid and sec and rt):
        f = Path.home() / "google_ads" / "gdrive_creds.json"
        if f.exists():
            j = json.loads(f.read_text())
            cid, sec, rt = j["client_id"], j["client_secret"], j["refresh_token"]
    if not (cid and sec and rt):
        return None
    return cid, sec, rt


class Drive:
    def __init__(self):
        import requests
        self.rq = requests
        c = _creds()
        if not c:
            raise RuntimeError("ドライブの接続情報(GDRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN)がありません")
        r = requests.post(TOKEN_URL, data={"client_id": c[0], "client_secret": c[1], "refresh_token": c[2],
                                           "grant_type": "refresh_token"}, timeout=30).json()
        if "access_token" not in r:
            raise RuntimeError(f"ドライブのトークン取得に失敗: {r}")
        self.h = {"Authorization": f"Bearer {r['access_token']}"}

    def exists(self, fid):
        r = self.rq.get(f"{DRIVE}/{fid}", headers=self.h, params={"fields": "id,trashed"}, timeout=30)
        return r.status_code == 200 and not r.json().get("trashed")

    def find_child(self, parent, name, folder):
        q = f"name = '{name}' and '{parent}' in parents and trashed = false"
        q += " and mimeType = 'application/vnd.google-apps.folder'" if folder else ""
        r = self.rq.get(DRIVE, headers=self.h, params={"q": q, "fields": "files(id)"}, timeout=30).json()
        return r.get("files", [{}])[0].get("id") if r.get("files") else None

    def mkdir(self, name, parent=None):
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent:
            meta["parents"] = [parent]
        r = self.rq.post(DRIVE, headers=self.h, json=meta, params={"fields": "id"}, timeout=30).json()
        if "id" not in r:
            raise RuntimeError(f"フォルダ作成に失敗: {r}")
        return r["id"]

    def upload(self, name, data, mime, parent):
        """同名があれば中身を差し替える(やり直しても増えない)"""
        old = self.find_child(parent, name, False)
        files = {"metadata": ("metadata", json.dumps({"name": name, "parents": [parent]} if not old else {"name": name}),
                              "application/json; charset=UTF-8"),
                 "file": (name, data, mime)}
        if old:
            r = self.rq.patch(f"{UPLOAD}/{old}", headers=self.h, params={"uploadType": "multipart", "fields": "id"},
                              files=files, timeout=120)
        else:
            r = self.rq.post(UPLOAD, headers=self.h, params={"uploadType": "multipart", "fields": "id"},
                             files=files, timeout=120)
        j = r.json()
        if "id" not in j:
            raise RuntimeError(f"アップロードに失敗 {name}: {j}")
        return j["id"]


def root_folder(dv, state):
    """保存先フォルダ(state.json に ID を記録)。無ければマイドライブ直下に作り、使い方.txt を置く"""
    fid = state.get("gbp_folder_id")
    if fid and dv.exists(fid):
        return fid
    fid = dv.mkdir(ROOT_NAME)
    dv.upload("使い方.txt", GUIDE.encode("utf-8"), "text/plain; charset=UTF-8", fid)
    state["gbp_folder_id"] = fid
    return fid


def folder_url(fid):
    return f"https://drive.google.com/drive/folders/{fid}"


def save_for_gbp(slug, state, when=None):
    """1本ぶんをドライブへ。state['posted'][slug]['gbp'] にフォルダURLを記録して返す"""
    dv = Drive()
    root = root_folder(dv, state)
    when = when or time.strftime("%Y-%m-%d %H:%M")
    name = f"{when[:10]}_{when[11:13]}{when[14:16]}_{slug}"
    sub = dv.find_child(root, name, True) or dv.mkdir(name, root)
    dv.upload("画像.jpg", gbp_image(slug), "image/jpeg", sub)
    dv.upload("本文.txt", gbp_text(slug).encode("utf-8"), "text/plain; charset=UTF-8", sub)
    url = folder_url(sub)
    state.setdefault("posted", {}).setdefault(slug, {})["gbp"] = url
    return url


def main():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if "--test" in sys.argv:
        slug = sys.argv[sys.argv.index("--test") + 1]
        out = HERE / "gbp_preview"; out.mkdir(exist_ok=True)
        (out / f"{slug}.jpg").write_bytes(gbp_image(slug))
        (out / f"{slug}.txt").write_text(gbp_text(slug), encoding="utf-8")
        print(f"書き出し: {out}/{slug}.jpg / .txt ({len(gbp_text(slug))}字)")
        return
    if "--one" in sys.argv:
        slug = sys.argv[sys.argv.index("--one") + 1]
        rec = state["posted"].get(slug, {})
        print("保存:", save_for_gbp(slug, state, rec.get("date")))
    elif "--backfill" in sys.argv:
        todo = [(s, v) for s, v in state["posted"].items() if not v.get("gbp") and (POSTS / f"{s}.jpg").exists()]
        todo.sort(key=lambda x: x[1].get("date", ""))
        print(f"{len(todo)}本を保存します")
        for s, v in todo:
            print(s, "→", save_for_gbp(s, state, v.get("date")), flush=True)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        print(__doc__)
        return
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print("フォルダ:", folder_url(state["gbp_folder_id"]))


if __name__ == "__main__":
    main()
