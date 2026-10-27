#!/usr/bin/env python3
"""香芝市周辺の週間天気を Instagram にリールで投稿する(通常の1日3本とは別の追加投稿)。

3日に1回、朝6時(ユーザー指示 2026-10-28)。ルーティンは毎朝6時に weather.yml を起動し、
ここで「前回の天気投稿から3日たったか」を判定する(たっていなければ何もしない)。
画像・動画は make_weather.py が weather/ に作る(posts/ に置くと通常の順番待ちに混ざるため別フォルダ)。
投稿の記録は state.json の "weather"(日付→URL)。

使い方: python post_weather.py --check [--backup] [--force]   投稿する日なら DUE を表示
        python post_weather.py --post weather_YYYYMMDD [--dry-run]
        python post_weather.py --cleanup                      weather/ の古いファイルを消す(新しい2回分だけ残す)
"""
import datetime, json, os, sys, time
from pathlib import Path
from post_ig import load_state, log, publish, STATE

HERE = Path(__file__).parent
WDIR = HERE / "weather"
RAW = "https://raw.githubusercontent.com/fujimori-ui/kitano-ig-post/main/weather/"
EVERY = 3                    # 何日に1回か
WINDOW = (6 * 60, 9 * 60)    # GitHub の予備起動はこの時間内(6:00〜9:00)だけ動く(遅れて昼や夜に出さない)


def due(state, force=False, backup=False):
    today = datetime.date.today()
    done = sorted(state.get("weather", {}))
    if done and done[-1] == today.isoformat():
        return False, "今日の天気は投稿済みです"
    if backup:
        m = time.localtime().tm_hour * 60 + time.localtime().tm_min
        if not WINDOW[0] <= m < WINDOW[1]:
            return False, f"予備起動が時間外です({time.strftime('%H:%M')})"
    if force or not done:
        return True, ""
    gap = (today - datetime.date.fromisoformat(done[-1])).days
    if gap < EVERY:
        return False, f"前回({done[-1]})から{gap}日。{EVERY}日に1回なので今日はお休みです"
    return True, ""


def main():
    state = load_state()
    if "--check" in sys.argv:
        ok, why = due(state, "--force" in sys.argv, "--backup" in sys.argv)
        print("DUE" if ok else f"RESULT: SKIP {why}")
        return
    if "--cleanup" in sys.argv:
        names = sorted({p.stem for p in WDIR.glob("weather_*.jpg")})
        for n in names[:-2]:
            for p in list(WDIR.glob(f"{n}.*")) + list((WDIR / "cover").glob(f"{n}.*")):
                p.unlink()
            print("removed", n)
        return
    name = sys.argv[sys.argv.index("--post") + 1]
    caption = (WDIR / f"{name}.txt").read_text(encoding="utf-8").strip()
    image_url, video_url, cover_url = RAW + f"{name}.jpg", RAW + f"{name}.mp4", RAW + f"cover/{name}.jpg"
    log(f"天気の投稿: {name}\n動画: {video_url}")
    if "--dry-run" in sys.argv:
        log("RESULT: DRY_RUN " + name)
        print(caption)
        return
    import requests
    for u in (image_url, video_url, cover_url):   # push 直後は公開URLに出るまで少しかかる
        for _ in range(12):
            if requests.head(u, timeout=30).status_code == 200:
                break
            time.sleep(10)
    mid, url = publish(os.environ["KITANO_IG_USER_ID"], os.environ["KITANO_IG_ACCESS_TOKEN"],
                       image_url, caption, video_url, cover_url)
    state.setdefault("weather", {})[datetime.date.today().isoformat()] = {
        "name": name, "time": time.strftime("%H:%M"), "media_id": mid, "url": url}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"RESULT: POSTED 天気 {name} | {url} | 次回は{EVERY}日後の朝6時")


if __name__ == "__main__":
    main()
