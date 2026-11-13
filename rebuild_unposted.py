#!/usr/bin/env python3
"""まだ投稿していない画像を、投稿予定の順に全部作り直す(構図・写真の形・箇条書きの形を決め直す)。
使い方: python rebuild_unposted.py            # 記録(layout_log / style_log)を消して決め直し、画像を作り直す
このあと python make_videos.py --unposted --renew で動画(アニメーション)も作り直す。
(2026-11-10 ユーザー「投稿ごとに画像のカタチやアニメーションをかえる」。順番が変わったとき・形を増やしたときに使う)"""
import json
import build_auto, post_ig
import make_posts as mp

state = post_ig.load_state()
order = post_ig.planned_order(state)
todo = [x for x in order if x not in state["posted"]]
for path in (mp.LAYOUT_LOG, mp.STYLE_LOG):
    if path.exists():
        log = json.loads(path.read_text(encoding="utf-8"))
        for x in todo:
            log.pop(x, None)
        path.write_text(json.dumps(dict(sorted(log.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
auto = {f"{it['n']:02d}_{it['slug']}": it for it in build_auto.load_items() if it.get("n")}
skipped = []
for name in todo:
    if name in auto:
        build_auto.build(auto[name], mp)
    elif hasattr(mp, f"post{int(name.split('_')[0]):02d}") if name.split("_")[0].isdigit() else False:
        getattr(mp, f"post{int(name.split('_')[0]):02d}")()
    else:
        skipped.append(name)
warn = [m for m in mp.FACE_LOG if m.startswith("⚠")]
print("REBUILT", len(todo) - len(skipped), "本")
if skipped:
    print("作り直せなかった(元データなし):", " ".join(skipped))
if warn:
    print("\n".join(warn))
