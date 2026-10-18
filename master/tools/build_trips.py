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
import nsplit
mm = kk2.mm
BASE_PLACES = {"南": "学園前駅（南口）", "北": "学園前駅（北口）", "東": "東生駒駅", "ふ": "ふれあいセンター",
               "さ": "さつき台休憩所", "営": "営業所", "い": "学研北生駒駅", "富": "富雄駅", "傍": "傍示",
               "ス": "生駒北スポーツセンター"}
# ダイヤごとの場所の名前（乗務員さんに教えてもらったもの。同じ略号でもダイヤで意味が違うことがある）
EXTRA_PLACES = {
    'a': {"近": "近畿大学", "Ｕ": "富雄UT場", "U": "富雄UT場", "T": "富雄UT場", "セ": "奈良県総合医療センター",
          "サ": "高山サイエンスタウン", "チ": "西千代ケ丘二丁目", "鹿": "鹿ノ台北二丁目", "赤": "赤膚山",
          "登": "学研奈良登美ケ丘駅", "大": "学園大和町五丁目", "若": "若草台", "ヒ": "帝塚山ヒルズ",
          "帝": "帝塚山南四丁目", "西": "西登美ケ丘五丁目", "中": "中登美ケ丘四丁目", "な": "奈良学園",
          "塚": "帝塚山西二丁目",
          # 2026-10-18 乗務員さんより: 校＝奈良北高校（19系統）、育＝育英西高校（系統は不明。北大和Ｂの「育」と同じ学校）、
          #   公＝公団管理事務所（61系統）、シ＝ショッピングセンター（61系統）
          "校": "奈良北高校", "育": "育英西高校", "公": "公団管理事務所", "シ": "ショッピングセンター"},
    # 2026-10-16: 「塚」も富雄駅から帝塚山西二丁目行き（乗務員さんより）。「帝」（7分）と「塚」（11・14分）は経由が違う。
    #   2026-10-18: 「塚」は 45系統（帝塚山ヒルズ経由 14分）・47系統（11分）と分かった（20番日祝のダイヤ表）。
    #   「帝」（富雄駅から7分）は帝塚山西二丁目ではなく、消去法で帝塚山南四丁目（46系統）。乗務員さんの了承済み
    # 2026-10-15: 「中」は中登美ケ丘四丁目（83番平日 8:16 学北→奈良学園登美ヶ丘→中四 の実物のダイヤ表で確認。
    #   以前は「中登美ケ丘団地経由」としていたが、中登美ケ丘団地は中四の次の停留所）
    'ikoma': {"田": "田原台一丁目", "住": "帝塚山住宅", "小": "小瀬保健福祉ゾーン", "あ": "あすかのセンター",
              "ひ": "ひかりが丘住宅", "中": "中菜畑二丁目", "き": "北田原", "帝": "帝塚山大学", "翠": "翠光台",
              "白": "白庭台駅", "九": "田原台九丁目西", "新": "新生駒台北口", "近": "近畿大学",
              "西": "西白庭台二丁目", "稲": "稲倉", "さ": "さつき台住宅", "宛": "宛の木",
              "北": "生駒駅（北口）", "南": "生駒駅（南口）", "生": "生駒台", "Ｕ": "富雄UT場", "U": "富雄UT場", "T": "富雄UT場"},
    'ba': {"緑": "緑ヶ丘", "六": "六条西三丁目", "中": "中菜畑二丁目", "近": "近鉄奈良駅", "育": "育英西高校",
           "青": "青葉公園前", "き": "北田原", "高": "高山学校", "尼": "尼ヶ辻駅", "若": "若草台",
           "芝": "芝辻操作場", "轉": "轉輪王"},
    'yobi': {"競": "競輪", "同": "同志社", "京": "京都駅", "祝": "祝園駅", "七": "光台7丁目"},
}
# 同じダイヤの中でも、番号によって場所が違う略号。{dia: {番号: {略号: 名前}}}
# 2026-10-11: 予備 10番の「西」は大和西大寺駅（北口）（競輪との往復）。1番・12番の「西」は別の場所かもしれないので未定
PLACE_BY_DIAL = {'yobi': {'10': {'西': '大和西大寺駅（北口）'}}}


def apply_place_by_dial(code, data):
    """番号ごとの名前を付ける。略号を「西_10」のように番号付きに置きかえて places に入れる"""
    for n, rule in PLACE_BY_DIAL.get(code, {}).items():
        for ent in data['dials'].get(n, {}).values():
            for var in ent.get('vars', [ent] if 'list' in ent else []):
                for x in var['list']:
                    for f in ('f', 't', 'p'):
                        if x.get(f) in rule:
                            x[f] = x[f] + '_' + n
        for c, name in rule.items():
            data['places'][c + '_' + n] = {'name': name}
    # もう使われていない略号の名前は消す
    used = {x.get(f) for dd in data['dials'].values() for ent in dd.values()
            for var in ent.get('vars', [ent] if 'list' in ent else []) for x in var['list'] for f in ('f', 't', 'p')}
    for c in list(data['places']):
        if c not in used: data['places'].pop(c)


# ダイヤによっては当てはまらない場所の決まり（生駒の「さ」はさつき台住宅で、さつき台休憩所ではない）
NO_MOVES = {'ikoma': [('さ', '東')]}
# 経由（系統）。同じ区間でも経由が違う便がある（学園前駅南口⇔西千代ケ丘二丁目の22系統・26系統など）。
# 系統表には経由が書いていないので、所要分で見分ける。どの所要分がどの経由かは乗務員さんに聞いて書く。
#   {dia: [{'pair': (発, 着), 'both': True（逆向きも同じ）, 'min': {所要分: 系統}, 'other': '?'（どれでもない分）}]}
#   'other' を '?' にすると、ナビで「経由を確認」と出す
#   循環で印（kk2.py の MARKS）が付くものは 'mark': {印: 系統}（印が無いものは None）
# 2026-10-14: 富雄駅→富雄駅は、印なし＝60系統 富雄団地循環、三＝58系統 三松ヶ丘経由、て＝43系統 帝塚山南循環
_FUJI = {'pair': ('富', '富'), 'mark': {None: '60', '三': '58', 'て': '43'}}
# 2026-10-15: 学園前駅（南口）⇔西千代ケ丘二丁目は、9分＝26系統 学園大和町経由、11分＝22系統 学園中三丁目経由。
#   （2026-10-14 に逆で入れていた。83番平日の実物のダイヤ表で確認: 幕22 14:09→14:20 中三経由、幕26 14:55→15:04 大三）
#   10分の便（朝晩 29本）は別の路線かもしれないので、系統は付けず勤務系統表のとおりに出す（乗務員さんより）
_CHIYO = {'pair': ('南', 'チ'), 'both': True, 'min': {9: '26', 11: '22'}}
# 2026-10-15: 学園前駅（北口）→中登美ケ丘四丁目は、3系統 快速 奈良学園経由（朝だけ。乗務員さんより・83番平日 8:16 で確認）。
#   'all' はその向きの便すべてに付ける。逆向き（中→北）は未確認なので付けない
_KAISOKU3 = {'pair': ('北', '中'), 'all': '3'}
# 2026-10-16: 18番平日の実物のダイヤ表（幕の番号）から。所要分が同じ帯の便は、時間帯もほぼ同じなので同じ系統とみなす。
#   確かめていない所要分（夕方の鹿ノ台20〜22分、学研北生駒駅の15・17・19分 など）は付けない（勤務系統表のとおりに出す）
#   'm' … 系統表の発の場所の右の印（kk2.py の VIA_MARKS）。'中'＝中登美ケ丘経由、''＝印なし。書いていなければ印は問わない
_A_KEI = [
    # 鹿ノ台北二丁目⇔学園前駅（北口）: 103系統 急行・102系統 各停（どちらも登美ヶ丘駅南経由。朝だけ）、112系統
    {'pair': ('鹿', '北'), 'min': {15: '103', 16: '103', 22: '112'}},   # 6:55・7:42＝103、9:30＝112
    # 2026-10-16 乗務員さんより: 17時以降の学園前駅→鹿ノ台は113系統 急行（急行は21時まで）。曜日の区別は聞いていないので全部に付ける
    {'pair': ('北', '鹿'), 'from': '17:00', 'to': '21:00', 'all': '113'},
    {'pair': ('北', '鹿'), 'min': {18: '102', 23: '112'}},              # 7:17＝102、9:00＝112
    # 学研北生駒駅⇔学園前駅（北口）: 印「中」＝中登美ケ丘経由（20分＝129系統 急行・朝だけ、21分＝130系統）、印なし＝128系統
    {'pair': ('い', '北'), 'm': '中', 'min': {20: '129', 21: '130'}},   # 83番 7:49＝129、18番 12:41＝130
    {'pair': ('い', '北'), 'm': '', 'min': {20: '128'}},                # 83番 9:10・18番 11:40＝128
    {'pair': ('北', 'い'), 'm': '', 'min': {21: '128'}},                # 9:56・12:11・19:12＝128
    # 学園前駅（南口）⇔赤膚山＝23系統、⇔学園大和町五丁目＝21系統（どちらも所要は1つだけ）
    {'pair': ('南', '赤'), 'both': True, 'all': '23'},
    {'pair': ('南', '大'), 'both': True, 'all': '21'},
    # 学園前駅（南口）⇔奈良県総合医療センター: 28系統 若草台経由（南→セ 24分）、29系統（セ→南 19分）
    {'pair': ('南', 'セ'), 'min': {24: '28'}},                          # 14:25＝28
    {'pair': ('セ', '南'), 'min': {19: '29'}},                          # 14:58＝29
    # 学園前駅（北口）⇔高山サイエンスタウン（学研北生駒駅経由）＝138系統
    {'pair': ('北', 'サ'), 'min': {30: '138'}},                         # 17:52＝138
    {'pair': ('サ', '北'), 'min': {30: '138'}},                         # 18:35＝138
    # 2026-10-16 乗務員さんより: 富雄駅⇔若草台＝50系統、学園前駅（南口）⇔若草台＝27系統（逆向きも同じ系統として付ける）
    {'pair': ('富', '若'), 'both': True, 'all': '50'},
    {'pair': ('南', '若'), 'both': True, 'all': '27'},
    # 2026-10-16: 富雄駅⇔帝塚山ヒルズ＝44系統（公開の路線一覧「44 富雄駅ー奈良帝塚山ヒルズ」。乗務員さんの了承済み）
    {'pair': ('富', 'ヒ'), 'both': True, 'all': '44'},
    # 2026-10-18 20番日祝の実物のダイヤ表から（写真の12便すべて一致）:
    #   富雄駅⇔帝塚山西二丁目（系統表の「塚」）は 14分＝45系統 帝塚山ヒルズ経由（行き 16:59・21:05、帰り 17:16）、
    #   11分＝47系統（帰り 21:22。帝塚山ヒルズを通らない）。富→塚 11分は写真に無いが、同じ道なので47系統とする
    {'pair': ('富', '塚'), 'both': True, 'min': {14: '45', 11: '47'}},
    #   富雄駅⇔学研北生駒駅 19分＝155系統（行き 21:48。三松橋・二名・生駒上町・真弓橋 経由）
    {'pair': ('富', 'い'), 'both': True, 'min': {19: '155'}},
    # 2026-10-18: 富雄駅⇔帝塚山南四丁目（系統表の「帝」7分）＝46系統（公開の路線一覧「46 富雄駅ー帝塚山南四丁目」から消去法。乗務員さんの了承済み）
    {'pair': ('富', '帝'), 'both': True, 'min': {7: '46'}},
    # 2026-10-18 乗務員さんより: 学園前駅（北口）⇔奈良北高校＝19系統、富雄駅⇔公団管理事務所・ショッピングセンター＝61系統
    {'pair': ('北', '校'), 'both': True, 'all': '19'},
    {'pair': ('公', '富'), 'both': True, 'all': '61'},
    {'pair': ('富', 'シ'), 'both': True, 'all': '61'},
]
# 2026-10-17 生駒の乗務員さんより（30番土曜の実物のダイヤ表で確認）:
#   生駒駅（南口）⇔田原台一丁目は 17分＝79系統 北谷公園経由、20分＝86系統 田原台八丁目経由、24分＝96系統 田原台九丁目西経由
#   （写真で確かめたのは 79 の行き・帰り、86 の帰り、96 の行き。所要分が行き帰りで同じなので両方向に付ける）
#   生駒駅（北口）の生駒台循環は 外回り＝77系統、内回り＝78系統（公開の時刻表サイトの系統一覧から。系統表の印 外・内 で見分ける）
_IK_KEI = [
    {'pair': ('北', '北'), 'mark': {'外': '77', '内': '78'}},
    {'pair': ('南', '田'), 'both': True, 'min': {17: '79', 20: '86', 24: '96'}},
]
VIA_RULES = {'a': [_FUJI, _CHIYO, _KAISOKU3] + _A_KEI,
             'ikoma': _IK_KEI,
             'yobi': [_FUJI, dict(_CHIYO, pair=('南学', 'チ'))]}   # 予備は北・南を駅ごとに分けたあと（南学）
# 系統の名前 {系統: 画面に出す名前}
VIA_NAMES = {'60': '60系統 富雄団地循環', '58': '58系統 三松ヶ丘経由 富雄団地循環', '43': '43系統 帝塚山南循環',
             '22': '22系統 学園中三丁目経由', '26': '26系統 学園大和町経由',
             '3': '3系統 快速 奈良学園経由',
             '103': '103系統 急行', '102': '102系統 各停', '112': '112系統',
             '128': '128系統 西登美ケ丘経由', '129': '129系統 急行 中登美ケ丘経由', '130': '130系統 中登美ケ丘経由',
             '23': '23系統', '21': '21系統', '28': '28系統 若草台経由', '29': '29系統',
             '138': '138系統 学研北生駒駅経由', '113': '113系統 急行', '50': '50系統', '27': '27系統', '44': '44系統', '45': '45系統 帝塚山ヒルズ経由', '47': '47系統', '155': '155系統', '46': '46系統', '19': '19系統', '61': '61系統',
             '77': '77系統 生駒台循環 外回り', '78': '78系統 生駒台循環 内回り',
             '79': '79系統 北谷公園経由', '86': '86系統 田原台八丁目経由', '96': '96系統 田原台九丁目西経由'}
# 区間に経由が1つしか無くても、必ず ⚠ で知らせる系統 {系統: 添える一言}
VIA_WARN = {'3': '朝だけの快速です。行先・経由をよく確かめてください',
            '22': '要注意！26系統（学園大和町経由）とまちがえないように'}
# 系統の色分け {系統: 色の名前}。ナビは vc-<色> の色で出す（2026-10-15 乗務員さんより: 22と26を色分け、22は要注意）
#   red＝要注意（⚠ 付き）、blue＝落ち着いた色。色の決まりが無い系統は、これまでどおり黄色の ⚠
VIA_COLOR = {'22': 'red', '26': 'blue',
             # 2026-10-17 生駒の乗務員さんより: 生駒台循環 外回り＝緑・内回り＝橙、田原台線 北谷公園経由＝橙・八丁目経由＝緑・九丁目西経由＝青
             '77': 'green', '78': 'orange', '79': 'orange', '86': 'green', '96': 'blue',
             # 2026-10-18 乗務員さんより「同じ区間で系統が違うものは色分けを。ダイヤ（学園前・生駒）や線（富雄線・学園前線）が違えば色が被ってよい」。
             #   実物のダイヤ表の色に合わせる: 急行の札＝赤、各停の札＝青、快速の札＝黄（ここでは橙）、「若草台経由」の箱＝緑、「中三経由」の箱＝赤
             '103': 'red', '113': 'red', '102': 'blue', '112': 'green',          # 鹿ノ台北二丁目⇔学園前駅（北口）
             '129': 'red', '128': 'blue', '130': 'green',                       # 学研北生駒駅⇔学園前駅（北口）
             '28': 'green', '29': 'blue',                                       # 学園前駅（南口）⇔奈良県総合医療センター
             '3': 'orange',                                                     # 快速（朝だけ。⚠ と一言も付く）
             '60': 'orange', '58': 'green', '43': 'blue',                      # 富雄駅→富雄駅の循環（ダイヤ表で60系統は黄色の網かけ）
             '45': 'green', '47': 'blue'}                                       # 富雄駅⇔帝塚山西二丁目


def apply_via(code, data, rules=None, names=None):
    """便に経由（v）を付ける。付けた数を返す"""
    rules = VIA_RULES.get(code, []) if rules is None else rules
    names = VIA_NAMES if names is None else names
    cnt = collections.Counter()
    used = set()
    for dd in data['dials'].values():
        for ent in dd.values():
            for var in ent.get('vars', [ent] if 'list' in ent else []):
                for x in var['list']:
                    if x.get('k') or 'd' not in x: continue
                    for r in rules:
                        f, t = r['pair']
                        if 'm' in r and x.get('m', '') != r['m']:
                            continue                    # 経由の印が合わない決まりは飛ばす
                        if ('from' in r and mm(x['d']) < mm(r['from'])) or ('to' in r and mm(x['d']) > mm(r['to'])):
                            continue                    # 発車の時間帯が合わない決まりは飛ばす（'to' の時刻ちょうどは含む）
                        if (x['f'], x['t']) == (f, t) or (r.get('both') and (x['f'], x['t']) == (t, f)):
                            if 'all' in r:
                                v = r['all']
                            elif 'mark' in r:
                                v = r['mark'].get(x.get('r'), r.get('other'))
                            else:
                                v = r['min'].get(mm(x['a']) - mm(x['d']), r.get('other'))
                            if v:
                                x['v'] = v; used.add(v); cnt[v] += 1
                            break
    # 経由の印（m）は決まりを当てるためだけのもの。データには残さない
    for dd in data['dials'].values():
        for ent in dd.values():
            for var in ent.get('vars', [ent] if 'list' in ent else []):
                for x in var['list']:
                    x.pop('m', None)
    if used:
        data['vias'] = {v: names.get(v, v + '系統') for v in sorted(used, key=lambda z: (len(z), z)) if v != '?'}
        warn = {v: VIA_WARN[v] for v in sorted(used) if v in VIA_WARN}
        if warn:
            data['viawarn'] = warn
        color = {v: VIA_COLOR[v] for v in sorted(used) if v in VIA_COLOR}
        if color:
            data['viacolor'] = color
    return cnt
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
    apply_place_by_dial(code, data)
    if code in nsplit.NS_ROUTE:
        # 予備・北大和Ｂは「北」「南」が学園前駅か生駒駅かを前後の路線から見分ける（nsplit.py）
        stat, left = nsplit.split(code, data)
        print('  北・南の見分け', dict(stat))
        for (n, d), v in left.items():
            print('    見分けられない %s番 %s: %s' % (n, d, ' '.join(v)))
        unknown = sorted(set(unknown) - {'北', '南'} | ({'北', '南'} if left else set()))
    vc = apply_via(code, data)
    if vc:
        print('  経由を付けた便', dict(vc))
    # 配っている trips-*.json は詰めた形（1行）。字下げすると差分が全部の行になり、ファイルも倍になる
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(code, '行', rep['rows'], '実車一致', rep['ok'], '不一致', len(rep['mis']), rep['mis'])
    print('  形違い', rep['labels'], '名前が付いた', rep['labels_ok'], '付かない', rep['nolabel'][:12])
    print('  名前の分からない略号', unknown)
