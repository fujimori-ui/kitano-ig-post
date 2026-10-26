#!/usr/bin/env python3
"""content/*.json(自動生成した投稿の中身)から posts/NN_slug.jpg + .txt を作る。

- 毎週のルーティン(claude.ai)が content/auto_YYYYMMDD.json を書いて push
- GitHub Actions build.yml がこのスクリプトで画像を作り、make_videos.py で動画を作って posts/ に commit
- 番号(n)は空いている番号を順に割り当て、JSON に書き戻す(2回目以降は同じ番号)

使い方:
  python build_auto.py                 # 未作成のものを全部作る(番号の無いものに番号を振る)
  python build_auto.py --force FILE    # そのJSONの分を作り直す
  python build_auto.py --check FILE    # 中身の形式チェックだけ(画像は作らない)
  python build_auto.py --stock         # 未投稿の在庫を種類ごとに表示
  python build_auto.py --titles        # 既存の投稿タイトル一覧(重複を避けるため)
JSONの形式は AUTO_GENERATE.md を参照。
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
CONTENT = HERE / "content"
POSTS = HERE / "posts"
LAYOUTS = {"list", "steps", "table", "photo", "quotes"}
SLUG_RE = re.compile(r"^(mame|chuui|company|komari|jirei|season|news|faq)_[a-z0-9_]{3,30}$")


def existing_numbers():
    nums = []
    for p in POSTS.glob("*.jpg"):
        m = re.match(r"^(\d+)_", p.name)
        if m:
            nums.append(int(m.group(1)))
    for f in CONTENT.glob("*.json"):
        for it in json.loads(f.read_text(encoding="utf-8")):
            if it.get("n"):
                nums.append(int(it["n"]))
    return nums


def check_item(it, errors, photos=None):
    slug = it.get("slug", "")
    if not SLUG_RE.match(slug):
        errors.append(f"{slug}: slug は mame_/chuui_/company_/komari_/jirei_/season_/news_/faq_ で始まる英小文字・数字・_ (例 mame_koke)")
    lay = it.get("layout", "list")
    if lay not in LAYOUTS:
        errors.append(f"{slug}: layout は {sorted(LAYOUTS)} のどれか")
    title = it.get("title", "")
    if not title or len(title) > 34:
        errors.append(f"{slug}: title は1〜34文字(改行\\nで2行まで)")
    for ln in title.split("\n"):
        if len(ln) > (14 if lay == "list" else 16):
            errors.append(f"{slug}: title の1行が長すぎます「{ln}」(list は14文字、他は16文字まで。\\nで区切る)")
    if title.count("\n") > 1:
        errors.append(f"{slug}: title は2行まで")
    cap = it.get("cap", "")
    if len(cap) < 150 or len(cap) > 900:
        errors.append(f"{slug}: cap(本文)は150〜900文字(今 {len(cap)})。CTAとハッシュタグは自動で付くので書かない")
    if "#" in cap or "0745-76-4335" in cap:
        errors.append(f"{slug}: cap にハッシュタグや電話番号を書かない(自動で付く)")
    note = it.get("note", "")
    if not note or len(note) > 28:
        errors.append(f"{slug}: note(下の帯の一言)は1〜28文字")
    ph = it.get("photo", "")
    if lay != "quotes" and not ph:
        errors.append(f"{slug}: photo(写真)は必ず入れる(AUTO_GENERATE.md の一覧から選ぶ)")
    if ph and photos is not None and ph not in photos:
        errors.append(f"{slug}: photo「{ph}」は photos_hd に無い(AUTO_GENERATE.md の一覧から選ぶ)")
    for lb in it.get("labels", []) or []:
        if len(lb) != 3 or len(lb[0]) > 14 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in lb[1:]):
            errors.append(f"{slug}: labels の各要素は [名前(14文字まで), x(0〜1), y(0〜1)]: {lb}")
    if lay == "list":
        pts = it.get("points", [])
        if not 3 <= len(pts) <= 4:
            errors.append(f"{slug}: points は3〜4個(写真を入れるので4個まで)")
        lim = 70 if len(pts) <= 3 else 38
        for p in pts:
            if len(p) != 2 or len(p[0]) > 22 or len(p[1]) > lim:
                errors.append(f"{slug}: points の各要素は [見出し(22文字まで), 説明({lim}文字まで。3個なら70、4個なら38)]: {p}")
        if not it.get("pill") or len(it["pill"]) > 14:
            errors.append(f"{slug}: pill(左上の小さなラベル)は1〜14文字")
        if it.get("stat") and (len(it["stat"]) != 2 or len(it["stat"][0]) > 6 or len(it["stat"][1]) > 12):
            errors.append(f"{slug}: stat は [大きな数字(6文字まで), 説明(12文字まで)]")
    elif lay == "steps":
        st = it.get("steps", [])
        if not 3 <= len(st) <= 4:
            errors.append(f"{slug}: steps は3〜4個")
        for p in st:
            if len(p) != 2 or len(p[0]) > 14 or len(p[1]) > 60:
                errors.append(f"{slug}: steps の各要素は [見出し(14文字まで), 説明(60文字まで)]: {p}")
    elif lay == "table":
        rows = it.get("rows", [])
        if not 4 <= len(rows) <= 7:
            errors.append(f"{slug}: rows は4〜7行")
        for p in rows:
            if len(p) != 2 or len(p[0]) > 20 or len(p[1]) > 16:
                errors.append(f"{slug}: rows の各要素は [項目(20文字まで), 値(16文字まで)]: {p}")
    elif lay == "photo":
        ck = it.get("checks", [])
        if not 3 <= len(ck) <= 5 or any(len(c) > 20 for c in ck):
            errors.append(f"{slug}: checks は3〜5個、各20文字まで")
        if not it.get("heading") or len(it["heading"]) > 24:
            errors.append(f"{slug}: heading は1〜24文字")
    elif lay == "quotes":
        qs = it.get("quotes", [])
        if not 2 <= len(qs) <= (2 if ph else 3) or any(len(q) > 95 for q in qs):
            errors.append(f"{slug}: quotes は2個(写真なしなら3個まで)、各95文字まで")


def load_items(files=None):
    files = files or sorted(CONTENT.glob("*.json"))
    out = []
    for f in files:
        try:
            items = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"NG {f}: JSONが読めません: {e}")
            sys.exit(1)
        if not isinstance(items, list):
            print(f"NG {f}: 一番外側は配列([ ... ])にしてください")
            sys.exit(1)
        for it in items:
            it["_file"] = Path(f)
        out.extend(items)
    return out


def build(it, mp):
    n, slug, lay = it["n"], it["slug"], it.get("layout", "list")
    note_yellow = it.get("note_style", "yellow" if slug.startswith("chuui_") else "blue") == "yellow"
    ph = it.get("photo"); fc = it.get("focus", 0.5)
    if lay == "list":
        mp.list_post(n, slug, it["pill"], it["title"], [tuple(p) for p in it["points"]], it["note"], it["cap"],
                     pill_bg=mp.YELLOW if slug.startswith(("mame_", "season_")) else mp.BLUE,
                     pill_fg=mp.INK if slug.startswith(("mame_", "season_")) else mp.WHITE,
                     stat=tuple(it["stat"]) if it.get("stat") else None, source=it.get("source"),
                     note_bg=mp.YELLOW if note_yellow else mp.LIGHT, note_fg=mp.INK if note_yellow else mp.BLUE,
                     photo=ph, focus=fc)
    elif lay == "steps":
        mp.steps_post(n, slug, it["title"], [tuple(p) for p in it["steps"]], it["note"], it["cap"], photo=ph, focus=fc)
    elif lay == "table":
        mp.table_post(n, slug, it["title"], [tuple(p) for p in it["rows"]], it["note"], it["cap"], footnote=it.get("footnote", ""), photo=ph, focus=fc)
    elif lay == "photo":
        mp.photo_post(n, slug, it["title"], ph, it["heading"], it["checks"], it["note"], it["cap"], focus=fc,
                      labels=[tuple(l) for l in it.get("labels", [])] or None)
    elif lay == "quotes":
        mp.quotes_post(n, slug, it["title"], it["quotes"], it["note"], it["cap"], credit=it.get("credit", ""), photo=ph, focus=fc)


def main():
    args = sys.argv[1:]
    if "--stock" in args:
        import post_ig
        st = post_ig.load_state()
        todo = [s for s in post_ig.all_items() if s not in st["posted"]]
        from collections import Counter
        c = Counter(post_ig.category(s) for s in todo)
        print(f"未投稿 {len(todo)}本(1日3本で約{len(todo) // 3}日分): " + " ".join(f"{post_ig.CATEGORY_NAMES[k]}{v}" for k, v in c.most_common()))
        return
    if "--titles" in args:
        for p in sorted(POSTS.glob("*.txt")):
            print(p.stem, "|", p.read_text(encoding="utf-8").split("\n", 1)[0][:50])
        return
    photos = {p.name for p in (HERE / "photos_hd").glob("*")} if (HERE / "photos_hd").exists() else None
    if "--check" in args:
        files = [Path(a) for a in args if a.endswith(".json")]
        items = load_items(files)
        errors = []
        slugs = [it["slug"] for it in items]
        for s in slugs:
            if slugs.count(s) > 1:
                errors.append(f"{s}: slug が重複")
            mine = {f"{it['n']:02d}_{it['slug']}" for it in items if it.get("n")}
            if any(p.stem.split("_", 1)[-1] == s and p.stem not in mine for p in POSTS.glob("*.jpg")):
                errors.append(f"{s}: 同じ slug の投稿がすでに posts/ にあります(別の名前に)")
        for it in items:
            check_item(it, errors, photos)
        if errors:
            print("NG " + str(len(errors)) + "件:")
            for e in errors:
                print(" -", e)
            sys.exit(1)
        print(f"OK {len(items)}本 形式に問題ありません")
        return
    force = "--force" in args
    files = [Path(a) for a in args if a.endswith(".json")] or None
    items = load_items(files)
    import make_posts as mp
    nums = existing_numbers()
    nxt = max(nums + [0]) + 1
    changed_files = set()
    made = []
    for it in items:
        if not it.get("n"):
            it["n"] = nxt; nxt += 1
            changed_files.add(it["_file"])
        slug = f"{it['n']:02d}_{it['slug']}"
        if (POSTS / f"{slug}.jpg").exists() and not force:
            continue
        errors = []
        check_item(it, errors, photos)
        if errors:
            print("NG", slug, errors)
            sys.exit(1)
        build(it, mp)
        made.append(slug)
    for f in changed_files:
        items_f = [{k: v for k, v in it.items() if k != "_file"} for it in items if it["_file"] == f]
        f.write_text(json.dumps(items_f, ensure_ascii=False, indent=1), encoding="utf-8")
    print("MADE " + " ".join(made))


if __name__ == "__main__":
    main()
