# -*- coding: utf-8 -*-
# master.html に apps.json の値を差し込んで、各アプリの index.html を作る
# SWVER（通知用の版番号）は各リポジトリの sw.js から自動で読み取る
import io, json, re, sys, os

master = io.open("master.html", encoding="utf-8").read()
apps   = json.load(io.open("apps.json", encoding="utf-8"))
WORK   = "/home/claude/work"      # cloneしたリポジトリの置き場

for repo, cfg in apps.items():
    cfg = dict(cfg)
    cfg["REPO"] = repo
    # sw.js のキャッシュ版番号（例 a-shukkin-v110）から v110 を取り出す
    swpath = os.path.join(WORK, repo, "sw.js")
    if os.path.exists(swpath):
        sw = io.open(swpath, encoding="utf-8").read()
        m = re.search(r"shukkin-(v\d+)", sw)
        cfg["SWVER"] = m.group(1) if m else "v1"
    else:
        cfg["SWVER"] = "v1"

    out = master
    for key, val in cfg.items():
        out = out.replace("{{" + key + "}}", val)
    left = set(re.findall(r"\{\{[A-Z_]+\}\}", out))
    if left:
        print(repo, "!! 未置換:", left); sys.exit(1)
    io.open("out-" + repo + ".html", "w", encoding="utf-8").write(out)
    print(repo, "生成OK  SWVER=" + cfg["SWVER"], len(out), "文字")
