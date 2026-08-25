# -*- coding: utf-8 -*-
# ==========================================================
#  出退勤検索くん — 5アプリの配布ファイルを作る
#
#  作るもの（1アプリにつき4つ）
#    index.html     ← master.html
#    manifest.json  ← master-manifest.json
#    sw.js          ← master-sw.js
#    share.html     ← master-share.html
#
#  使い方
#    python3 build.py         版番号はそのまま作り直す
#    python3 build.py bump    版番号を1つ繰り上げてから作る（更新を配るとき）
#
#  版番号（sw.js の v112 など）は各リポジトリの sw.js から自動で読みます。
#  bump を付ければこの中で繰り上げるので、
#  「sw.js を先に手で上げてから生成する」という手順はもう要りません。
# ==========================================================
import io, json, re, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = "/home/claude/work"        # cloneしたリポジトリの置き場

# 生成するファイル（雛形 → 出来上がりの名前）
TEMPLATES = [
    ("master.html",          "index.html"),
    ("master-manifest.json", "manifest.json"),
    ("master-sw.js",         "sw.js"),
    ("master-share.html",    "share.html"),
]

BUMP = len(sys.argv) > 1 and sys.argv[1] == "bump"

apps = json.load(io.open(os.path.join(HERE, "apps.json"), encoding="utf-8"))

# 雛形をまとめて読み込む
src = {}
for tpl, out in TEMPLATES:
    path = os.path.join(HERE, tpl)
    if not os.path.exists(path):
        print("!! 雛形が見つかりません:", tpl)
        sys.exit(1)
    src[tpl] = io.open(path, encoding="utf-8").read()

for repo, cfg in apps.items():
    cfg = dict(cfg)
    cfg["REPO"] = repo

    # --- 版番号を決める -------------------------------------
    # 既存の sw.js から 'a-shukkin-v112' の v112 を取り出す
    swpath = os.path.join(WORK, repo, "sw.js")
    num = 0
    if os.path.exists(swpath):
        m = re.search(r"shukkin-v(\d+)", io.open(swpath, encoding="utf-8").read())
        if m:
            num = int(m.group(1))
    if BUMP:
        num += 1
    if num == 0:
        num = 1
    cfg["SWVER"] = "v" + str(num)

    # --- 雛形に値を差し込む ---------------------------------
    outdir = os.path.join(HERE, "out-" + repo)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    for tpl, out in TEMPLATES:
        text = src[tpl]
        for key, val in cfg.items():
            text = text.replace("{{" + key + "}}", val)

        left = set(re.findall(r"\{\{[A-Z_]+\}\}", text))
        if left:
            print(repo, tpl, "!! 未置換:", left)
            sys.exit(1)

        io.open(os.path.join(outdir, out), "w", encoding="utf-8").write(text)

    print(repo, "生成OK  版=" + cfg["SWVER"], "→ out-" + repo + "/")

print("")
print("できたフォルダの中身を、そのまま各リポジトリの直下に上書きしてください。")
if not BUMP:
    print("※ 版番号は据え置きです。更新を配るときは python3 build.py bump を使ってください。")
