# -*- coding: utf-8 -*-
"""HP(新着情報 news)とGoogleマイビジネスの投稿を消す(手動用)。
  python delete_posts.py --wp 326,321 --gbp "テント倉庫,軒先" [--dry]
  --dry なら消さずに対象を表示するだけ。WP はゴミ箱へ(復元可)。GBP は削除(復元不可)。
"""
import argparse, os, sys, json
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbp_post, wp_post

ap = argparse.ArgumentParser()
ap.add_argument("--wp", default="")
ap.add_argument("--gbp", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()

if a.wp:
    for pid in [x.strip() for x in a.wp.split(",") if x.strip()]:
        r = requests.get(wp_post.WP + f"/wp/v2/news/{pid}&_fields=id,slug,status,title", timeout=60)
        if r.status_code != 200:
            print(f"WP {pid}: 見つかりません HTTP {r.status_code}"); continue
        p = r.json()
        print(f"WP {pid}: [{p['status']}] {p['slug']} / {p['title']['rendered']}")
        if a.dry:
            continue
        r = wp_post._req("DELETE", f"/wp/v2/news/{pid}")
        print(f"  -> ゴミ箱へ: status={r.get('status')}")

if a.gbp:
    keys = [k.strip() for k in a.gbp.split(",") if k.strip()]
    g = gbp_post.GBP()
    st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"), encoding="utf-8"))
    gl = st["gbp_location"]  # 北野工作所の店舗(state.json に設定済み)
    acct, loc = gl["account"], gl["location"]
    print(f"GBP account={acct} location={loc} ({gl.get('title')})")
    posts, token = [], None
    while True:
        prm = {"pageSize": 100}
        if token:
            prm["pageToken"] = token
        j = g._call("GET", f"{gbp_post.V4}/{acct}/{loc}/localPosts", params=prm)
        posts += j.get("localPosts", [])
        token = j.get("nextPageToken")
        if not token or len(posts) >= 300:
            break
    print(f"GBP 投稿 {len(posts)} 件")
    hit = []
    for p in posts:
        s = (p.get("summary") or "").replace("\n", " ")
        mark = any(k in s for k in keys)
        if a.dry or mark:
            print(f"{'★' if mark else '  '} {p.get('createTime','')[:16]} {p['name'].split('/')[-1]} {s[:70]}")
        if mark:
            hit.append(p)
    print(f"対象 {len(hit)} 件")
    if not a.dry:
        for p in hit:
            g._call("DELETE", f"{gbp_post.V4}/{p['name']}")
            print(f"  -> 削除: {p['name'].split('/')[-1]}")
