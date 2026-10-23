#!/usr/bin/env python3
"""北野工作所 Instagram 自動投稿(クラウド版)

posts/ にある NN_slug.jpg + NN_slug.txt を番号順に1本ずつ投稿する。
投稿済みは state.json に記録(GitHub Actions がコミットで書き戻す)。
画像は公開リポジトリの raw URL を Instagram API(graph.instagram.com)に渡す。

使い方: python post_ig.py [--dry-run] [--slug 03_kawara]
環境変数: KITANO_IG_USER_ID, KITANO_IG_ACCESS_TOKEN
"""
import json, os, sys, time
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


def next_item(state, slug=None):
    items = sorted(p.stem for p in POSTS.glob("*.jpg") if (POSTS / f"{p.stem}.txt").exists())
    if slug:
        return slug if slug in items else None
    for s in items:
        if s not in state["posted"]:
            return s
    return None


def api_post(path, data):
    r = requests.post(f"{API}/{path}", data=data, timeout=60)
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"Instagram API error: {j['error']}")
    return j


def publish(user_id, token, image_url, caption):
    c = api_post(f"{user_id}/media", {"image_url": image_url, "caption": caption, "access_token": token})
    cid = c["id"]
    for _ in range(30):
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
    item = next_item(state, slug)
    if not item:
        log("RESULT: QUEUE_EMPTY 投稿できるネタがありません(posts/ に新しい画像と本文を追加してください)")
        return
    caption = (POSTS / f"{item}.txt").read_text(encoding="utf-8").strip()
    image_url = RAW_BASE + f"{item}.jpg"
    title = caption.split("\n", 1)[0][:40]
    log(f"次の投稿: {item} / {title}")
    log(f"画像: {image_url}")
    if dry:
        log("RESULT: DRY_RUN " + item)
        print(caption)
        return
    user_id = os.environ["KITANO_IG_USER_ID"]
    token = os.environ["KITANO_IG_ACCESS_TOKEN"]
    # 画像URLが公開されているか確認(push直後は数十秒かかることがある)
    for _ in range(12):
        if requests.head(image_url, timeout=30).status_code == 200:
            break
        time.sleep(10)
    mid, url = publish(user_id, token, image_url, caption)
    state["posted"][item] = {"date": time.strftime("%Y-%m-%d %H:%M"), "media_id": mid, "url": url}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    remaining = len([s for s in sorted(p.stem for p in POSTS.glob('*.jpg')) if s not in state["posted"]])
    log(f"RESULT: POSTED {item} | {title} | {url} | 残り{remaining}本")


if __name__ == "__main__":
    main()
