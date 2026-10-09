# 勤務系統表PDFから行程を取り出す
# 文字の位置（pdfplumber）と、帯・点線の描き方から読む。
#  ・黒い帯 = 営業の便（太い帯・細い帯とも）
#  ・点線 / 白抜きの帯 = 回送
#  ・帯の左上に「場所」、その下に「分」。右下に「分」、その下に「場所」
#  ・(営)(東) など大きい字 = 休憩の場所
import re, sys, json
import pdfplumber

DAY = {'平': '平', '土': '土', '日': '日祝', '全': '全'}


def near(a, b, tol):
    return abs(a - b) <= tol


def words_of(pg):
    """文字を自分でつないで語にする。重ね書きの文字は1つにし、すき間があれば分ける"""
    cs = []
    for c in sorted(pg.chars, key=lambda c: (round(c['top'], 1), c['x0'])):
        if not c['text'].strip():
            continue
        if any(o['text'] == c['text'] and abs(o['x0'] - c['x0']) < 0.4 and abs(o['top'] - c['top']) < 0.4 for o in cs[-6:]):
            continue
        cs.append(c)
    # 数字や文字は、右隣の字の左端が自分の右端とぴったり合う。それでつなぐ。
    # 重なって印刷された「44」「47」のようなものも、正しく分けられる
    nxt = {}
    taken = set()
    for i, c in enumerate(cs):
        best = None
        for j, d in enumerate(cs):
            if j == i or j in taken:
                continue
            if abs(d['top'] - c['top']) < 0.8 and abs(d['size'] - c['size']) < 0.4 and abs(d['x0'] - c['x1']) < 0.15:
                if best is None or abs(d['x0'] - c['x1']) < abs(cs[best]['x0'] - c['x1']):
                    best = j
        if best is not None:
            nxt[i] = best
            taken.add(best)
    out = []
    for i, c in enumerate(cs):
        if i in taken:
            continue
        w = {'text': c['text'], 'x0': c['x0'], 'x1': c['x1'], 'top': c['top'], 'size': c['size']}
        k = i
        while k in nxt:
            k = nxt[k]
            w['text'] += cs[k]['text']; w['x1'] = cs[k]['x1']
        out.append(w)
    return out


def parse_page(pg, verbose=False):
    W = words_of(pg)
    # 時刻の目盛り。見出しの「4」〜「24」
    hdr = {}
    for w in W:
        if w['top'] < 130 and re.fullmatch(r'\d{1,2}', w['text']) and 4 <= int(w['text']) <= 24 and w['size'] > 7:
            hdr.setdefault(int(w['text']), w['x0'])
    if 4 not in hdr or 10 not in hdr:
        return []
    hs = sorted(hdr)
    span = (hdr[hs[-1]] - hdr[hs[0]]) / (hs[-1] - hs[0])   # 1時間の幅
    off = 2.2 * span / 39.5                                 # 見出しの数字は線より少し右にある
    X4 = hdr[4] - off

    def est(x):  # x の位置の時刻（分）
        return (x - X4) / span * 60 + 240

    def pick(m, x):  # 「分」と位置から、いちばん近い時刻を選ぶ
        e = est(x)
        h = round((e - m) / 60)
        return h * 60 + m

    # 出勤・退勤・実車の列
    colx = {}
    for w in W:
        if w['text'] in ('出勤', '退勤', '実車') and w['text'] not in colx and w['x0'] > hdr[hs[-1]]:
            colx[w['text']] = (w['x0'] + w['x1']) / 2

    labels = [w for w in W if re.fullmatch(r'\d{1,3}-\d', w['text']) and w['x0'] < X4]
    labels.sort(key=lambda w: w['top'])
    rows = []
    for i, L in enumerate(labels):
        Y = L['top']
        nextY = labels[i + 1]['top'] if i + 1 < len(labels) else Y + 60
        dayw = [w for w in W if near(w['top'], Y, 2) and L['x1'] < w['x0'] < X4 and w['text'] in DAY]
        day = DAY[dayw[0]['text']] if dayw else None
        band = [w for w in W if Y - 7 < w['top'] < min(Y + 19, nextY - 7) and X4 - 3 < w['x0'] < X4 + span * 21]

        def line(lo, hi):
            out = []
            for w in band:
                if lo <= w['top'] - Y <= hi and w['size'] < 6:
                    if not any(near(w['x0'], o['x0'], .3) and o['text'] == w['text'] for o in out):
                        out.append(w)
            return sorted(out, key=lambda w: w['x0'])
        sc = [w for w in line(-6, -1.5) if not w['text'].isdigit()]
        sm = [w for w in line(-0.5, 3.5) if w['text'].isdigit()]
        em = [w for w in line(5.5, 11) if w['text'].isdigit()]
        ec = [w for w in line(11.2, 16.5) if not w['text'].isdigit()]
        starts = []
        for w in sm:
            c = [k for k in sc if abs(k['x0'] - w['x0']) < 3.2]
            starts.append({'x': w['x0'], 'm': int(w['text']), 'c': c[0]['text'] if c else None})
        ends = []
        for w in em:
            c = [k for k in ec if abs(k['x1'] - w['x1']) < 3.2 or abs(k['x0'] - w['x0']) < 3.2]
            ends.append({'x': w['x1'], 'm': int(w['text']), 'c': c[0]['text'] if c else None, 'used': False})
        # 帯と点線
        bars = [r for r in pg.rects if r['fill'] and Y + 4 < r['top'] < Y + 9 and r['x1'] - r['x0'] > 1]
        dashes = [l for l in pg.lines if Y + 4 < l['top'] < Y + 9 and l.get('dash') and l['dash'][0]]

        items = []
        warn = []
        for s in starts:
            cand = [e for e in ends if not e['used'] and e['x'] > s['x'] + 0.5]
            if not cand:
                warn.append('着が見つからない %s%d' % (s['c'] or '', s['m']))
                continue
            e = min(cand, key=lambda e: e['x'])
            e['used'] = True
            d = pick(s['m'], s['x'])
            a = pick(e['m'], e['x'])
            if a < d:
                a += 60
            x0, x1 = s['x'], e['x']
            mid = (x0 + x1) / 2
            black = [r for r in bars if r['x0'] - 1 < mid < r['x1'] + 1 and (r.get('non_stroking_color') in (0, 0.0, (0,), [0], None) or r.get('non_stroking_color') == (0, 0, 0))]
            white = [r for r in bars if r['x0'] - 1 < mid < r['x1'] + 1 and r not in black]
            dsh = [l for l in dashes if l['x0'] - 1 < mid < l['x1'] + 1]
            kind = 'trip'
            if dsh or (white and not black):
                kind = '回送'
            elif not black:
                kind = '?'
            it = {'d': '%d:%02d' % divmod(d, 60), 'f': s['c'] or '', 'a': '%d:%02d' % divmod(a, 60), 't': e['c'] or ''}
            if kind == '回送':
                it = {'k': '回送', **it}
            elif kind == '?':
                warn.append('帯が無い %s' % it)
                it = {'k': '回送', **it}
            if kind == 'trip' and (not s['c'] or not e['c']):
                warn.append('場所が欠けている %s' % it)
            items.append(it)
        for e in ends:
            if not e['used']:
                warn.append('発が見つからない %d%s' % (e['m'], e['c'] or ''))
        items.sort(key=lambda x: (int(x['d'].split(':')[0]) * 60 + int(x['d'].split(':')[1])))
        # 休憩の場所（大きい字）。前後の行のどちらかに入るので、位置で近いほうに
        brk = []
        for w in W:
            t = w['text'].strip('()（）')
            if w['size'] > 8 and len(t) == 1 and not t.isdigit() and Y - 12 < w['top'] < min(Y + 30, nextY + 6) and X4 < w['x0'] < X4 + span * 21:
                brk.append({'x': (w['x0'] + w['x1']) / 2, 'p': t, 'y': w['top']})
        # 文字の注記（ふれあい運休日 など）
        notes = [w['text'] for w in W if Y - 7 < w['top'] < min(Y + 19, nextY - 7) and X4 - 3 < w['x0'] < X4 + span * 21
                 and w['size'] >= 6 and len(w['text'].strip('()（）')) >= 2 and not re.fullmatch(r'[\d:()（）]+', w['text'])]
        # 右の列の値
        vals = {}
        for k, cx in colx.items():
            v = [w for w in W if Y - 4 < w['top'] < min(Y + 30, nextY - 3) and abs((w['x0'] + w['x1']) / 2 - cx) < 9 and re.fullmatch(r'\d{1,2}:\d{2}', w['text'])]
            if v:
                vals[k] = sorted(v, key=lambda w: w['top'])[-1]['text']
        rows.append({'label': L['text'], 'day': day, 'Y': Y, 'items': items, 'brk': brk, 'notes': notes,
                     'vals': vals, 'warn': warn, 'x2t': (X4, span)})
    return rows


def place_breaks(rows):
    """休憩の場所を、その時刻に便の無い行へ入れる（上下の行のどちらに書いてあるか分からないため）"""
    def mm(s):
        h, m = s.split(':'); return int(h) * 60 + int(m)
    for r in rows:
        X4, span = r['x2t']
        for b in r['brk']:
            t = (b['x'] - X4) / span * 60 + 240
            busy = any(mm(it['d']) - 3 <= t <= mm(it['a']) + 3 for it in r['items'])
            r.setdefault('brkc', [])
            if not busy and r['items'] and mm(r['items'][0]['d']) - 30 < t < mm(r['items'][-1]['a']) + 30:
                r['brkc'].append((t, b['p'], abs(b['y'] - r['Y'])))


def finish(rows):
    place_breaks(rows)
    out = []
    for r in rows:
        items = list(r['items'])
        # 同じ休憩が2行に入りそうなら、近い行だけに
        for t, p, dy in r.get('brkc', []):
            # 休憩の印は、その時刻の直前の便のあとに置く
            items.append({'k': '休', 'p': p, '_t': t})
        def key(x):
            if x.get('k') == '休':
                return x['_t']
            h, m = x['d'].split(':'); return int(h) * 60 + int(m)
        items.sort(key=key)
        for x in items:
            x.pop('_t', None)
        out.append({**r, 'items': items})
    return out


def parse(path):
    pdf = pdfplumber.open(path)
    allrows = []
    for pi, pg in enumerate(pdf.pages):
        rows = parse_page(pg)
        for r in rows:
            r['page'] = pi + 1
        allrows += finish(rows)
    return allrows


def jissha(items):
    def mm(s):
        h, m = s.split(':'); return int(h) * 60 + int(m)
    return sum(mm(x['a']) - mm(x['d']) for x in items if not x.get('k'))


if __name__ == '__main__':
    rows = parse(sys.argv[1])
    for r in rows:
        js = jissha(r['items'])
        want = r['vals'].get('実車')
        ok = ''
        if want:
            h, m = want.split(':'); ok = 'OK' if int(h) * 60 + int(m) == js else 'ずれ %+d' % (js - int(h) * 60 - int(m))
        print('p%d %s %s 便%d 実車 %d:%02d / 表 %s %s %s %s' % (r['page'], r['label'], r['day'], len([x for x in r['items'] if not x.get('k')]),
              js // 60, js % 60, want, ok, r['notes'], r['warn'][:3]))
