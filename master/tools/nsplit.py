# 予備・北大和Ｂの「北」「南」を、学園前駅か生駒駅かに分ける（2026-10-10）
#
# 予備・北大和Ｂは学園前駅と生駒駅の両方へ行くので、同じ「北」「南」でも駅が違う。
# 乗務員さんは「その日の前後の路線」で見分けている。それを次の手がかりでまねる。
#
#  手がかり1: 同じ行き先・同じ所要分（±2分）の便が、学園前（学園前Ａ・Ｃ）と生駒の
#             どちらの系統表にあるか。片方にだけあれば、その駅とする。
#             行き先は名前でくらべる（「中」は学園前Ａでは中登美ケ丘、生駒では中菜畑二丁目のように
#             略号が同じでも場所が違うため）。名前が分からない略号は、学園前Ａ・Ｃ・生駒で
#             名前が1つにそろっているときだけ使う。
#  手がかり2: 乗務員さんに教えてもらった行き先ごとの駅（NS_ROUTE）
#             それでも見分けられないところは、番号ごとに教えてもらった駅（NS_DIAL）
#  手がかり3: ある便で着いた場所から次の便が出るなら、同じ駅（休憩をはさんでも）。
#             環状の便（北→北）は出た駅に戻るので、発と着は同じ駅。
#             1つの勤務の中で、つながっている所はまとめて同じ駅にする。
#             回送の「北→北」は駅をまたぐかもしれないので、つながりにしない。
#             行って戻る便（南→中、中→南 のように同じ相手と往復）は、出た駅に戻ってくる。
#             北口⇔南口の短い回送（10分以内）は、同じ駅の中の移動。
#             着いてから回送なしで15分以内に反対の口から出るときも、同じ駅
#             （学園前駅と生駒駅の間は15分では動けないため）。
#
# 見分けた「北」「南」は「北学」「北生」「南学」「南生」という略号に置きかえる。
# 見分けられなかったもの・手がかりが食い違うものは「北」「南」のまま。画面では「北口」「南口」と出す。
# 環状の便（北→北）の所要分は、学園前Ａに無いだけで学園前にもあり得るので手がかり1には使わない。
# ただし系統表で「外」「内」（外回り・内回り）が付いた循環は、生駒の系統表にだけ出てくるので手がかりにする
# （kk2.py が便に r:"外" / r:"内" を付ける）。北大和Ｂ 29番の昼の循環がこれ。
import json, os, collections

NS_NAME = {'北学': '学園前駅（北口）', '南学': '学園前駅（南口）',
           '北生': '生駒駅（北口）', '南生': '生駒駅（南口）'}
# 乗務員さんに教えてもらった、行き先ごとの駅。{dia: {(北/南, 相手の略号): '学' か '生'}}
# 環状（北→北）は (北, '環')。例: {'ba': {('北', '緑'): '学', ('北', '環'): '学'}}
# 2026-10-10 北大和Ｂ: 北口の循環・緑ヶ丘・轉輪王・青葉公園前は朝日町循環、
#   南口の循環・六条西三丁目は六条西二丁目行き、近鉄奈良駅行き（最終は尼ヶ辻駅止め）。どれも学園前駅
NS_ROUTE = {'ba': {('北', '環'): '学', ('北', '緑'): '学', ('北', '轉'): '学', ('北', '青'): '学',
                   ('南', '環'): '学', ('南', '六'): '学', ('南', '近'): '学', ('南', '尼'): '学'},
            'yobi': {}}
# 手がかりで見分けられなかったところを、番号ごとに教えてもらったもの（見分けられたところは変えない）
# 2026-10-10: 予備 7・8・19番は前後の路線から生駒駅、23番は学園前駅
NS_DIAL = {'yobi': {'7': '生', '8': '生', '19': '生', '23': '学'}}

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
SOURCES = [os.path.join(WORK, 'shukkin-search', 'trips-a.json'),
           os.path.join(WORK, 'shukkin-search-c', 'trips-c.json'),
           os.path.join(WORK, 'shukkin-search-ikoma', 'trips-ikoma.json')]


def mm(s):
    h, m = s.split(':'); return int(h) * 60 + int(m)


def lists_of(dials):
    for n, v in dials.items():
        for day, ent in v.items():
            for vi, var in enumerate(ent.get('vars') or [ent]):
                yield n, day, vi, var.get('label', ''), var.get('list', [])


def _evidence():
    ev = collections.defaultdict(set)
    names = collections.defaultdict(set)     # 略号 → 学園前Ａ・Ｃ・生駒での名前
    srcs = []
    for p in SOURCES:
        if not os.path.exists(p):
            print('  !! 手がかりの系統表が見つかりません:', p); continue
        d = json.load(open(p, encoding='utf-8'))
        pl = {k: v['name'] for k, v in d.get('places', {}).items()}
        st = pl.get('北') or pl.get('南') or ''
        tag = '学' if '学園前' in st else ('生' if '生駒' in st else None)
        if not tag: continue
        srcs.append((tag, d, pl))
        for _, _, _, _, L in lists_of(d['dials']):
            for x in L:
                for c in (x.get('f'), x.get('t')):
                    if c and c not in ('北', '南'): names[c].add(pl.get(c))
    for tag, d, pl in srcs:
        for _, _, _, _, L in lists_of(d['dials']):
            for x in L:
                if x.get('k') or 'd' not in x: continue          # 営業の便だけ
                # 外回り・内回りの印がある循環（生駒駅北口の循環など）
                if x.get('r') and x['f'] in ('北', '南') and x['f'] == x['t']:
                    ev[(x['f'], '環' + x['r'])].add(tag)
                for end, other, dr in ((x['f'], x['t'], '発'), (x['t'], x['f'], '着')):
                    if end in ('北', '南') and other and other not in ('北', '南') and pl.get(other):
                        ev[(end, dr, pl[other], mm(x['a']) - mm(x['d']))].add(tag)
    return ev, names


def _comps(L):
    slots = [(i, f) for i, x in enumerate(L) for f in ('f', 't', 'p') if x.get(f) in ('北', '南')]
    parent = {s: s for s in slots}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def join(a, b):
        if a in parent and b in parent: parent[find(a)] = find(b)
    for i, x in enumerate(L):
        if x.get('k') == '休' or 'd' not in x: continue
        # 環状の便（北→北）は出た駅に戻ってくるので、発と着は同じ駅
        if not x.get('k') and x.get('f') in ('北', '南') and x.get('f') == x.get('t'):
            join((i, 't'), (i, 'f'))
        # 北口⇔南口の短い回送は同じ駅の中
        if x.get('k') == '回送' and {x.get('f'), x.get('t')} == {'北', '南'} and mm(x['a']) - mm(x['d']) <= 10:
            join((i, 't'), (i, 'f'))
        y = L[i + 1] if i + 1 < len(L) else None
        if not y or y.get('k') == '休' or 'd' not in y: continue
        # 行って戻る便: 南→中 のすぐ後に 中→南
        if not x.get('k') and not y.get('k') and x.get('f') in ('北', '南') and x.get('f') == y.get('t') \
                and x.get('t') and x.get('t') == y.get('f') and x.get('t') not in ('北', '南'):
            join((i, 'f'), (i + 1, 't'))
        # 着いてから回送なしで、15分以内に反対の口から出る
        if x.get('t') in ('北', '南') and y.get('f') in ('北', '南') and x.get('t') != y.get('f') \
                and not y.get('k') and 0 <= mm(y['d']) - mm(x['a']) <= 15:
            join((i, 't'), (i + 1, 'f'))
    for i, x in enumerate(L):
        isr = x.get('k') == '休'
        code = x.get('p') if isr else x.get('t')
        if code not in ('北', '南'): continue
        end = (i, 'p' if isr else 't')
        for j in range(i + 1, len(L)):
            y = L[j]
            if y.get('k') == '休':
                if y.get('p') == code:
                    parent[find((j, 'p'))] = find(end); end = (j, 'p'); continue
                break
            if y.get('f') == code:
                parent[find((j, 'f'))] = find(end)
            break
    return slots, find


def split(code, data):
    """data（trips の中身）の「北」「南」を置きかえる。見分けられなかったものの一覧を返す"""
    ev, names = _evidence()
    pl = {k: v['name'] for k, v in data['places'].items()}
    route = NS_ROUTE.get(code, {})

    def ident(c):
        if c in pl: return pl[c]
        ns = names.get(c)
        if ns and len(ns) == 1 and None not in ns: return next(iter(ns))
        return None

    left = collections.OrderedDict()
    stat = collections.Counter()
    for n, day, vi, lab, L in lists_of(data['dials']):
        slots, find = _comps(L)
        strong = collections.defaultdict(set)   # 手がかり1（学園前Ａ・Ｃ・生駒の便とくらべたもの）
        weak = collections.defaultdict(set)     # 手がかり2（教えてもらった行き先ごとの駅）
        for (i, f) in slots:
            x = L[i]
            if f == 'p' or 'd' not in x: continue
            other = x['t'] if f == 'f' else x['f']
            if not x.get('k') and other == x[f]:
                # 外回り・内回りの印がある循環は、同じ印の循環がある駅
                t = ev.get((x[f], '環' + x['r'])) if x.get('r') else None
                if t and len(t) == 1: strong[find((i, f))] |= t
                r = route.get((x[f], '環'))      # 環状（北→北）は (北, '環') で教えてもらう
                if r: weak[find((i, f))].add(r)
                continue
            if not other or other in ('北', '南'): continue
            r = route.get((x[f], other))
            if r: weak[find((i, f))].add(r)
            if x.get('k'): continue
            nm = ident(other)
            if not nm: continue
            dur = mm(x['a']) - mm(x['d'])
            tags = set()
            for dd in range(-2, 3):
                tags |= ev.get((x[f], '発' if f == 'f' else '着', nm, dur + dd), set())
            if len(tags) == 1: strong[find((i, f))] |= tags
        # 便とくらべた手がかりがあればそれを使い、無いときだけ教えてもらった行き先の駅を使う
        # （北大和Ｂの「北→北」の循環は、ふだんは学園前の朝日町循環だが、生駒の便の間に入ることもある）
        decided = {}
        for (i, f) in slots:
            c = find((i, f))
            v = strong.get(c) or weak.get(c) or set()
            if not v and n in NS_DIAL.get(code, {}):
                v = {NS_DIAL[code][n]}
            if len(v) == 1:
                decided[(i, f)] = next(iter(v))
        # 休憩の場所だけ分からないとき: 前に着いた駅と次に出る駅が同じなら、その駅の反対の口で休憩
        for (i, f) in slots:
            if f != 'p' or (i, f) in decided: continue
            pv = next(((j, 't') for j in range(i - 1, -1, -1) if L[j].get('k') != '休'), None)
            nx = next(((j, 'f') for j in range(i + 1, len(L)) if L[j].get('k') != '休'), None)
            a = decided.get(pv); b = decided.get(nx)
            if a and a == b:
                decided[(i, f)] = a
        for (i, f) in slots:
            if (i, f) in decided:
                L[i][f] = L[i][f] + decided[(i, f)]; stat[decided[(i, f)]] += 1
            else:
                c = find((i, f))
                stat['食い違い' if (strong.get(c) or weak.get(c)) else '分からない'] += 1
                x = L[i]
                left.setdefault((n, day), []).append(x.get('d') or '休憩')
    for k, v in NS_NAME.items():
        data['places'][k] = {'name': v}
    # 見分けられなかったものは、駅の名前を付けずに「北口」「南口」とだけ出す
    data['places']['北'] = {'name': '北口'}; data['places']['南'] = {'name': '南口'}
    # 使っていない北学などは消す
    used = set()
    for _, _, _, _, L in lists_of(data['dials']):
        for x in L:
            for c in (x.get('f'), x.get('t'), x.get('p')):
                if c: used.add(c)
    for k in list(NS_NAME) + ['北', '南']:
        if k not in used: data['places'].pop(k, None)
    return stat, left
