# 勤務系統表の読み取り（帯を基準にする版）
# 帯1本 = 1区間。帯の左端の上に「発の分」とその上に「発の場所」、
# 右端の下に「着の分」とその下に「着の場所」が書いてある。
#   黒い帯 = 営業の便 / 白抜きの帯・点線 = 回送
import re, sys, json
import pdfplumber
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from kkparse import words_of, DAY

def chars_of(pg):
    cs = []
    for c in sorted(pg.chars, key=lambda c: (round(c['top'], 1), c['x0'])):
        if not c['text'].strip():
            continue
        if any(o['text'] == c['text'] and abs(o['x0'] - c['x0']) < 0.4 and abs(o['top'] - c['top']) < 0.4 for o in cs[-8:]):
            continue
        cs.append(c)
    return cs

def mm(s):
    h, m = s.split(':'); return int(h) * 60 + int(m)

def jissha(items):
    return sum(mm(x['a']) - mm(x['d']) for x in items if not x.get('k'))


def parse_page(pg):
    W = words_of(pg)
    C = chars_of(pg)
    hdr = {}
    for w in W:
        if w['top'] < 130 and re.fullmatch(r'\d{1,2}', w['text']) and 4 <= int(w['text']) <= 24 and w['size'] > 7:
            hdr.setdefault(int(w['text']), w['x0'])
    if 4 not in hdr or 10 not in hdr:
        return []
    hs = sorted(hdr)
    span = (hdr[hs[-1]] - hdr[hs[0]]) / (hs[-1] - hs[0])
    X4 = hdr[4] - 2.2 * span / 39.5
    XEND = X4 + span * 21
    def est(x): return (x - X4) / span * 60 + 240
    def pick(m, x):
        e = est(x); h = round((e - m) / 60); return h * 60 + m
    colx = {}
    for w in W:
        if w['text'] in ('出勤', '退勤', '実車', '労働') and w['text'] not in colx and w['x0'] > XEND - 20:
            colx[w['text']] = (w['x0'] + w['x1']) / 2
    labels = sorted([w for w in W if re.fullmatch(r'\d{1,3}-\d', w['text']) and w['x0'] < X4], key=lambda w: w['top'])
    # 帯（黒・白）と点線
    bars = []
    for r in pg.rects:
        if not r['fill'] or r['x1'] - r['x0'] < 0.8 or r['bottom'] - r['top'] > 3 or not (X4 - 2 < r['x0'] < XEND):
            continue
        col = r.get('non_stroking_color')
        if isinstance(col, (list, tuple)): col = col[0] if len(col) == 1 else (1 if all(v > .9 for v in col) else 0)
        white = (col is not None and col > 0.5)
        if any(abs(b['x0'] - r['x0']) < .3 and abs(b['x1'] - r['x1']) < .3 and abs(b['top'] - r['top']) < .5 for b in bars):
            continue
        bars.append({'x0': r['x0'], 'x1': r['x1'], 'top': r['top'], 'bottom': r['bottom'], 'k': '回送' if white else 'trip'})
    for l in pg.lines:
        if l.get('dash') and l['dash'][0] and abs(l['top'] - l['bottom']) < .3 and l['x1'] - l['x0'] > 0.8 and X4 - 2 < l['x0'] < XEND:
            bars.append({'x0': l['x0'], 'x1': l['x1'], 'top': l['top'] - 0.9, 'bottom': l['top'] + 0.9, 'k': '回送'})
    rows = []
    for i, L in enumerate(labels):
        Y = L['top']
        nextY = labels[i + 1]['top'] if i + 1 < len(labels) else Y + 60
        dayw = [w for w in W if abs(w['top'] - Y) < 2 and L['x1'] < w['x0'] < X4 and w['text'] in DAY]
        day = DAY[dayw[0]['text']] if dayw else None
        rb = sorted([b for b in bars if Y + 3.5 < (b['top'] + b['bottom']) / 2 < Y + 9.5], key=lambda b: b['x0'])
        items, warn = [], []
        def chars_line(lo, hi):
            return [c for c in C if lo <= c['top'] - Y <= hi and c['size'] < 6 and X4 - 4 < c['x0'] < XEND + 4]
        SM = [c for c in chars_line(-0.8, 3.8) if c['text'].isdigit()]
        SC = [c for c in chars_line(-6.5, -1.2) if not c['text'].isdigit()]
        EM = [c for c in chars_line(5.6, 11) if c['text'].isdigit()]
        EC = [c for c in chars_line(11.2, 16.8) if not c['text'].isdigit()]
        def adj(c, pool, right=True):
            for d in pool:
                if abs(d['top'] - c['top']) < .8 and (abs(d['x0'] - c['x1']) < .15 if right else abs(d['x1'] - c['x0']) < .15):
                    return d
            return None
        def run(c, pool):  # 文字が続いていれば場所の名前として足す
            s = c['text']; d = c
            while True:
                d2 = adj(d, pool, True)
                if not d2: break
                s += d2['text']; d = d2
            return s
        for b in rb:
            s = [c for c in SM if -1.0 <= c['x0'] - b['x0'] <= 2.0]
            e = [c for c in EM if -1.4 <= c['x1'] - b['x1'] <= 1.4]
            if not s or not e:
                warn.append('分が読めない %.1f-%.1f %s' % (est(b['x0']) / 60, est(b['x1']) / 60, b['k']))
                continue
            # 候補ごとに数字を組み立て、端の位置が合うものを選ぶ。2桁を少し優先する
            def sc_s(c):
                n = adj(c, SM, True); return abs(c['x0'] - b['x0'] - 0.6) - (0.5 if n else 0)
            def sc_e(c):
                n = adj(c, EM, False); return abs(c['x1'] - b['x1'] - 0.5) - (0.5 if n else 0)
            c0 = min(s, key=sc_s)
            n2 = adj(c0, SM, True)
            sm = c0['text'] + (n2['text'] if n2 else '')
            c1 = min(e, key=sc_e)
            p2 = adj(c1, EM, False)
            em = (p2['text'] if p2 else '') + c1['text']
            if int(sm) > 59: sm = c0['text']
            if int(em) > 59: em = c1['text']
            sc = [c for c in SC if abs(c['x0'] - c0['x0']) < 3.0]
            ec = [c for c in EC if abs(c['x1'] - c1['x1']) < 3.0 or abs(c['x0'] - (p2 or c1)['x0']) < 3.0]
            # 場所は1文字。短い便が並ぶと隣の便の場所とくっつくので、いちばん近い1文字だけ取る
            sc = [c for c in sc if c['text'] not in ('外', '内')]
            fc = min(sc, key=lambda c: abs(c['x0'] - c0['x0'])) if sc else None
            f = fc['text'] if fc else ''
            t = min(ec, key=lambda c: abs(c['x1'] - c1['x1']))['text'] if ec else ''
            d = pick(int(sm), b['x0']); a = pick(int(em), b['x1'])
            if a < d: a += 60
            it = {'d': '%d:%02d' % divmod(d, 60), 'f': f, 'a': '%d:%02d' % divmod(a, 60), 't': t}
            # 発の場所の右に「外」「内」があれば、循環の外回り・内回り（生駒駅北口の循環などに付いている）
            if fc:
                rr = [c for c in SC if c['text'] in ('外', '内') and abs(c['top'] - fc['top']) < 0.8 and fc['x1'] - 0.5 < c['x0'] < fc['x1'] + 8]
                if rr and f == t: it['r'] = min(rr, key=lambda c: c['x0'])['text']
            # 読み違いに備えて、ほかの読み方も控えておく（実車の合計が合わないときに使う）
            alts = set()
            for cs_ in s:
                for two in (True, False):
                    nn = adj(cs_, SM, True) if two else None
                    if two and not nn: continue
                    v1 = cs_['text'] + (nn['text'] if nn else '')
                    if int(v1) > 59: continue
                    for ce_ in e:
                        for two2 in (True, False):
                            pp = adj(ce_, EM, False) if two2 else None
                            if two2 and not pp: continue
                            v2 = (pp['text'] if pp else '') + ce_['text']
                            if int(v2) > 59: continue
                            dd = pick(int(v1), b['x0']); aa = pick(int(v2), b['x1'])
                            if aa < dd: aa += 60
                            if abs(dd - est(b['x0'])) < 6 and abs(aa - est(b['x1'])) < 6:
                                alts.add((dd, aa))
            it['_alts'] = sorted(alts)
            if b['k'] == '回送':
                it = {'k': '回送', **it}
            elif not f or not t:
                warn.append('場所が欠けている %s' % it)
            items.append(it)
        items.sort(key=lambda x: mm(x['d']))
        brk = []
        for w in W:
            t = w['text'].strip('()（）')
            if w['size'] > 8 and len(t) == 1 and not t.isdigit() and Y - 14 < w['top'] < Y + 34 and X4 < w['x0'] < XEND:
                brk.append({'t': est((w['x0'] + w['x1']) / 2), 'p': t, 'dy': abs(w['top'] - (Y + 8))})
        notes = [w['text'] for w in W if Y - 7 < w['top'] < min(Y + 19, nextY - 7) and X4 - 3 < w['x0'] < XEND
                 and w['size'] >= 6 and len(w['text'].strip('()（）')) >= 2 and not re.fullmatch(r'[\d:()（）～〜]+', w['text'])]
        vals = {}
        for k, cx in colx.items():
            v = [w for w in W if Y - 4 < w['top'] < min(Y + 30, nextY - 3) and abs((w['x0'] + w['x1']) / 2 - cx) < 9 and re.fullmatch(r'\d{1,2}:\d{2}', w['text'])]
            if v:
                v = sorted(v, key=lambda w: w['top'])
                vals[k] = v[-1]['text']          # 下の値（従来どおり）
                vals[k + '_all'] = [w['text'] for w in v]
        rows.append({'label': L['text'], 'day': day, 'items': items, 'brk': brk, 'notes': notes, 'vals': vals, 'warn': warn})
    return rows

def fix_by_total(rows):
    """実車の合計が表と合わない行は、1本だけ別の読み方に替えて合うものがあれば直す"""
    for r in rows:
        want = r['vals'].get('実車')
        trips = [x for x in r['items'] if not x.get('k')]
        if not want:
            continue
        allv = r['vals'].get('実車_all', [want])
        if jissha(r['items']) in (mm(want), sum(mm(v) for v in allv)):
            r['fix'] = ''
            continue
        delta = mm(want) - jissha(r['items'])
        r['fix'] = ''
        if delta == 0:
            continue
        opts = []
        for x in trips:
            cur = mm(x['a']) - mm(x['d'])
            for dd, aa in x.get('_alts', []):
                if (aa - dd) - cur == delta:
                    opts.append((x, dd, aa))
        if len(opts) == 1 or (opts and len({(o[1], o[2]) for o in opts}) == 1 and len({id(o[0]) for o in opts}) == 1):
            x, dd, aa = opts[0]
            r['fix'] = '直した %s-%s → %d:%02d-%d:%02d' % (x['d'], x['a'], dd // 60, dd % 60, aa // 60, aa % 60)
            x['d'] = '%d:%02d' % divmod(dd, 60); x['a'] = '%d:%02d' % divmod(aa, 60)
        else:
            r['fix'] = '直せない（候補%d）' % len(opts)
    for r in rows:
        for x in r['items']:
            x.pop('_alts', None)
    return rows


def finish(rows):
    rows = fix_by_total(rows)
    # 回送の場所を前後から補う。同じ場所での待機（前後の便が同じ場所）は出さない
    for r in rows:
        its = r['items']
        # 休憩の場所：その時刻に便の無い行で、いちばん近いもの
        busy = lambda tt: any(mm(x['d']) - 2 <= tt <= mm(x['a']) + 2 for x in its)
        r['_brk'] = [b for b in r['brk'] if its and not busy(b['t']) and mm(its[0]['d']) < b['t'] < mm(its[-1]['a'])]
    # 同じ休憩の字は上下の行で取り合いになるので、近いほうだけに
    allb = {}
    for ri, r in enumerate(rows):
        for b in r['_brk']:
            k = (round(b['t']), b['p'])
            if k not in allb or b['dy'] < allb[k][1]:
                allb[k] = (ri, b['dy'])
    for ri, r in enumerate(rows):
        its = [x for x in r['items']]
        for b in r['_brk']:
            k = (round(b['t']), b['p'])
            if allb[k][0] == ri:
                its.append({'k': '休', 'p': b['p'], '_t': b['t']})
        its.sort(key=lambda x: x['_t'] if x.get('k') == '休' else mm(x['d']))
        out = []
        for j, x in enumerate(its):
            if x.get('k') == '回送':
                prev = next((y for y in reversed(its[:j]) if y.get('k') != '回送'), None)
                nxt = next((y for y in its[j + 1:] if y.get('k') != '回送'), None)
                pf = (prev['p'] if prev and prev.get('k') == '休' else (prev['t'] if prev else '')) or ''
                if not x['f']: x['f'] = pf
                if not x['t']:
                    x['t'] = (nxt['p'] if nxt and nxt.get('k') == '休' else (nxt['f'] if nxt else '営')) or ''
                # 同じ場所での待機だけの点線は出さない
                if x['f'] and x['f'] == x['t'] and (not nxt or nxt.get('k') != '休') and (not prev or prev.get('k') != '休'):
                    continue
            x.pop('_t', None)
            out.append(x)
        r['items'] = out
    # 同じ形の行（土と日祝など）で休憩の印が片方にしか無いときは写す
    for r in rows:
        if not any(x.get('k') == '休' for x in r['items']):
            core = [x for x in r['items'] if x.get('k') != '休']
            for o in rows:
                if o is r or o['label'].split('-')[0] != r['label'].split('-')[0]: continue
                oc = [x for x in o['items'] if x.get('k') != '休']
                if oc == core and any(x.get('k') == '休' for x in o['items']):
                    r['items'] = [dict(x) for x in o['items']]; break
    return rows

def parse(path):
    pdf = pdfplumber.open(path); rows = []
    for pi, pg in enumerate(pdf.pages):
        rr = parse_page(pg)
        for r in rr: r['page'] = pi + 1
        rows += rr
    return finish(rows)

if __name__ == '__main__':
    rows = parse(sys.argv[1])
    for r in rows:
        js = jissha(r['items']); want = r['vals'].get('実車'); ok = ''
        if want:
            ok = 'OK' if mm(want) == js else 'ずれ %+d' % (js - mm(want))
        print('p%d %s %s 便%d 実車 %d:%02d / 表 %s %s %s %s' % (r['page'], r['label'], r['day'], len([x for x in r['items'] if not x.get('k')]),
              js // 60, js % 60, want, ok, r['notes'][:3], r['warn'][:3]) + ('  ' + r.get('fix','') if r.get('fix') else ''))
