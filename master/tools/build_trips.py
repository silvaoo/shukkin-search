# 勤務系統表から trips-<code>.json を作る（今日のナビの行程データ）
# 使い方（各リポジトリを並べて置いた場所で）:
#   python3 build_trips.py <code> <勤務系統表.pdf> <dia-*.json> <改正日 YYYY-MM-DD> <出力 trips-<code>.json>
#   例) python3 build_trips.py ba ../../shukkin-search-ba/pdf/kinmu-keitou-1001.pdf \
#          ../../shukkin-search-ba/dia-ba-1001.json 2026-10-01 ../../shukkin-search-ba/trips-ba.json
# 出力の最後に「実車一致／不一致」と「名前の分からない略号」が出る。不一致の行は画像で確かめること
# 中身: kk2.py が帯（黒＝便、白抜き・点線＝回送）を基準に分と場所を読み、
#       系統表の「実車」の合計で検算し、合わない行は1本だけ別の読み方に替えて合えば直す
import sys, json, re, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import kk2
mm = kk2.mm
BASE_PLACES = {"南": "学園前駅（南口）", "北": "学園前駅（北口）", "東": "東生駒駅", "ふ": "ふれあいセンター",
               "さ": "さつき台休憩所", "営": "営業所", "い": "学研北生駒駅", "富": "富雄駅", "傍": "傍示",
               "ス": "生駒北スポーツセンター"}
# ダイヤごとの場所の名前（乗務員さんに教えてもらったもの。同じ略号でもダイヤで意味が違うことがある）
EXTRA_PLACES = {
    'a': {"近": "近畿大学", "Ｕ": "富雄UT場", "U": "富雄UT場", "T": "富雄UT場", "セ": "奈良県総合医療センター",
          "サ": "高山サイエンスタウン", "チ": "西千代ケ丘二丁目", "鹿": "鹿ノ台北二丁目", "赤": "赤膚山",
          "登": "学研奈良登美ケ丘駅", "大": "学園大和町五丁目", "若": "若草台", "ヒ": "帝塚山ヒルズ",
          "帝": "帝塚山西二丁目", "西": "西登美ケ丘五丁目", "中": "中登美ケ丘団地経由", "な": "奈良学園"},
    'ikoma': {"田": "田原台一丁目", "住": "帝塚山住宅", "小": "小瀬保健福祉ゾーン", "あ": "あすかのセンター",
              "ひ": "ひかりが丘住宅", "中": "中菜畑二丁目", "き": "北田原", "帝": "帝塚山大学", "翠": "翠光台",
              "白": "白庭台駅", "九": "田原台九丁目西", "新": "新生駒台北口", "近": "近畿大学",
              "西": "西白庭台二丁目", "稲": "稲倉", "さ": "さつき台住宅", "宛": "宛の木",
              "北": "生駒駅（北口）", "南": "生駒駅（南口）", "生": "生駒台", "Ｕ": "富雄UT場", "U": "富雄UT場", "T": "富雄UT場"},
    'ba': {"緑": "緑ヶ丘循環", "六": "六条西二丁目", "中": "中菜畑", "育": "育英西校", "青": "青葉公園",
           "高": "高山学校", "尼": "尼ヶ辻駅止め", "若": "若草台", "轉": "朝日町循環"},
    'yobi': {"競": "競輪", "同": "同志社", "京": "京都駅", "祝": "祝園駅", "七": "光台7丁目"},
}
# ダイヤによっては当てはまらない場所の決まり（生駒の「さ」はさつき台住宅で、さつき台休憩所ではない）
NO_MOVES = {'ikoma': [('さ', '東')]}
MOVES = [{"from": "営", "to": "い", "prep": 10, "near": True, "note": "営業所のすぐ下"},
         {"from": "さ", "to": "東", "prep": 15}]

def tsum(s):
    return sum(mm(x) for x in re.findall(r'\d{1,2}:\d{2}', s))

def variants_from_dia(slot):
    """出退勤表のデータから、形の名前と（出勤, 退勤, 労働の合計）を取り出す"""
    if not slot or slot.get('o') in (None, '—'):
        base = None
    else:
        ts = re.findall(r'\d{1,2}:\d{2}', slot['o'])
        base = (ts[0], ts[-1], tsum(slot.get('w', '')))
    out = []
    n = (slot or {}).get('n', '') or ''
    parts = [p.strip() for p in n.split('／')] if '／' in n or re.search(r'[A-F]:', n) else []
    # 奈良学園のような A:… B:… の書き方
    if re.search(r'(^|\s|）)[A-F]:', n):
        for m in re.finditer(r'([A-F]):([\d:/〜]+)\(([\d:/]+)\)', n):
            ts = re.findall(r'\d{1,2}:\d{2}', m.group(2))
            out.append((m.group(1), (ts[0], ts[-1], tsum(m.group(3)))))
        return out
    if not parts:
        return out
    if base:
        out.append((parts[0], base))
    for p in parts[1:]:
        if ':' not in p or not re.search(r'\D:', p):
            continue
        lab, rest = re.split(r'(?<=\D):', p, maxsplit=1)
        lab = lab.strip()
        if not base:
            continue
        st, en, lab_sum = base
        body = re.sub(r'\(.*?\)', '', rest)
        par = re.findall(r'\((.*?)\)', rest)
        if par:
            lab_sum = tsum(par[0])
        elif re.fullmatch(r'[\d:/]+', body.strip()):
            lab_sum = tsum(body); body = ''
        if '〜' in body:
            a, b = body.split('〜', 1)
            if a.strip(): st = re.findall(r'\d{1,2}:\d{2}', a)[0]
            if b.strip(): en = re.findall(r'\d{1,2}:\d{2}', b)[-1]
        elif re.findall(r'\d{1,2}:\d{2}', body):
            st = re.findall(r'\d{1,2}:\d{2}', body)[0]
        out.append((lab, (st, en, lab_sum)))
    return out

def build(code, pdf, dia, revision, places):
    rows = kk2.parse(pdf)
    D = json.load(open(dia, encoding='utf-8'))['dials']
    groups = collections.OrderedDict()
    for r in rows:
        n, v = r['label'].split('-')
        days = ['平', '土', '日祝'] if r['day'] == '全' else [r['day']]
        for d in days:
            groups.setdefault((n, d), []).append((int(v), r))
    dials = {}
    report = {'rows': 0, 'ok': 0, 'mis': [], 'labels': 0, 'labels_ok': 0, 'nolabel': []}
    for (n, d), lst in groups.items():
        lst.sort(key=lambda x: x[0])
        slot = (D.get(n) or {}).get(d)
        vlabs = variants_from_dia(slot)
        vars_ = []
        for vi, r in lst:
            report['rows'] += 1
            want = r['vals'].get('実車')
            js = kk2.jissha(r['items'])
            alls = sum(mm(x) for x in r['vals'].get('実車_all', []))
            if want and js in (mm(want), alls): report['ok'] += 1
            elif want: report['mis'].append('%s-%d %s %+d' % (n, vi, d, js - mm(want)))
            label = ''
            nara = bool(vlabs) and all(re.fullmatch(r'[A-F]', lab) for lab, _ in vlabs)
            if len(lst) > 1 or nara:
                report['labels'] += 1
                st = (r['vals'].get('出勤_all') or [None])[0]
                en = (r['vals'].get('退勤_all') or [None])[-1]
                lw = sum(mm(x) for x in r['vals'].get('労働_all', [])) or None
                key = (st, en, lw)
                hit = [lab for lab, k in vlabs if k == key]
                # 同じ時刻の形が複数あるときは、出てくる順に当てる
                same = [x for x, rr in lst if x <= vi and ((rr['vals'].get('出勤_all') or [None])[0], (rr['vals'].get('退勤_all') or [None])[-1], sum(mm(y) for y in rr['vals'].get('労働_all', [])) or None) == key]
                if len(hit) >= 1 and len(same) <= len(hit):
                    label = hit[len(same) - 1]; report['labels_ok'] += 1
                else:
                    hit2 = [lab for lab, k in vlabs if k[0] == key[0] and k[1] == key[1]]
                    if len(hit2) == 1:
                        label = hit2[0]; report['labels_ok'] += 1
                    else:
                        report['nolabel'].append('%s-%d %s %s 候補%d' % (n, vi, d, key, len(hit)))
                if not label:
                    t0 = r['vals'].get('出勤', ''); t1 = r['vals'].get('退勤', '')
                    label = '形%d（%s〜%s）' % (vi, t0, t1) if t0 else '形%d' % vi
            items = [x for x in r['items'] if not (x.get('k') == '休' and x.get('p') in ('鍵',))]
            v_ = {'label': label, 'list': items}
            ins, outs = r['vals'].get('出勤_all', []), r['vals'].get('退勤_all', [])
            if ins and outs and len(ins) == len(outs):
                v_['in'] = ins; v_['out'] = outs     # 出勤・退勤（中間解放があれば2つずつ）
            vars_.append(v_)
        # 形の名前が A〜F だけ（奈良学園）のときは、A〜F を全部並べる。
        # 系統表に無い形は行程が無いので、出退勤表の出勤・退勤だけを持たせる（nodata）
        if vlabs and all(re.fullmatch(r'[A-F]', lab) for lab, _ in vlabs):
            note = (slot or {}).get('n', '')
            have = {v['label']: v for v in vars_}
            full = []
            for m in re.finditer(r'([A-F]):([\d:/〜]+)', note):
                lab = m.group(1)
                if lab in have:
                    full.append(have[lab]); continue
                a, _, b = m.group(2).partition('〜')
                full.append({'label': lab, 'list': [], 'in': [a.split('/')[0]] + ([b.split('/')[0]] if '/' in b else []),
                             'out': ([a.split('/')[1]] if '/' in a else []) + [b.split('/')[-1]], 'nodata': True})
            if full:
                vars_ = full
        if all(not v['list'] for v in vars_) and not any(v.get('nodata') for v in vars_):
            continue  # 公休など、便の無いもの
        if len(vars_) == 1:
            ent = {k: v for k, v in vars_[0].items() if k != 'label'}
        else:
            ent = {'vars': vars_}
        dials.setdefault(n, {})[d] = ent
    used = set()
    for dd in dials.values():
        for ent in dd.values():
            for v in ent.get('vars', [ent] if 'list' in ent else []):
                for x in v['list']:
                    for c in (x.get('f'), x.get('t'), x.get('p')):
                        if c: used.add(c)
    pl = {c: {"name": places[c]} for c in sorted(used) if c in places}
    data = {"_説明": "勤務系統表（%s改正）を自動で読み取ったもの。今日のナビで使う。d=発車 f=発 a=着 t=着く場所。k=回送は回送、k=休は休憩の場所。vars は同じ番号の形違い（先頭がふだん）。places に無い略号は、そのまま表示する。moves は場所どうしの決まり（near:true はすぐ近く、prep は何分前から準備）。" % revision,
            "meta": {"code": code, "revision": revision},
            "places": pl, "moves": [m for m in MOVES if (m['from'], m['to']) not in NO_MOVES.get(code, [])], "dials": dials}
    return data, report, sorted(used - set(places))

if __name__ == '__main__':
    code, pdf, dia, rev, out = sys.argv[1:6]
    places = dict(BASE_PLACES)
    places.update(EXTRA_PLACES.get(code, {}))
    if code == 'yobi':
        places.pop('南'); places.pop('北')   # 予備は「南」「北」がどこか未確認（生駒は生駒駅の北口・南口）
    data, rep, unknown = build(code, pdf, dia, rev, places)
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(code, '行', rep['rows'], '実車一致', rep['ok'], '不一致', len(rep['mis']), rep['mis'])
    print('  形違い', rep['labels'], '名前が付いた', rep['labels_ok'], '付かない', rep['nolabel'][:12])
    print('  名前の分からない略号', unknown)
