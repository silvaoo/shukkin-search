# 私のカレンダー（和紙の手帳・豪華版）の文様を SVG で作り、CSS の data URI にする（2026-11-07）
# 使い方: python3 washi_gen.py → washi-uris.json（master.html の #resCalModal の CSS に貼る）
# 画像ファイルは使わない。形はすべてここで描く。
import math, random, json, urllib.parse

def uri(svg):
    svg = ' '.join(svg.split())
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg, safe=" =:/,'.-();") + '")'

# 和紙の繊維（細い繊維を薄く散らす）
def washi(seed=9, size=260, n=60, col='140,110,60'):
    r = random.Random(seed); paths=[]
    for i in range(n):
        x=r.uniform(0,size); y=r.uniform(0,size); L=r.uniform(14,46); a=r.uniform(0,math.pi)
        x2=x+L*math.cos(a); y2=y+L*math.sin(a)
        cx=(x+x2)/2+r.uniform(-8,8); cy=(y+y2)/2+r.uniform(-8,8)
        paths.append(f"<path d='M{x:.1f} {y:.1f}Q{cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}' stroke='rgba({col},{r.uniform(.10,.24):.2f})' stroke-width='{r.uniform(.35,.8):.2f}' fill='none'/>")
    dots=''.join(f"<circle cx='{r.uniform(0,size):.1f}' cy='{r.uniform(0,size):.1f}' r='{r.uniform(.3,.9):.2f}' fill='rgba({col},{r.uniform(.08,.18):.2f})'/>" for _ in range(50))
    return f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}'>{''.join(paths)}{dots}</svg>"

# 季節の形
def sakura(cx,cy,r,fill,center,rot=0):
    ps=[]
    for i in range(5):
        a=math.radians(rot+i*72-90)
        def P(rr,da):
            t=a+math.radians(da); return (cx+rr*math.cos(t), cy+rr*math.sin(t))
        t1=P(r*1.02,-16); n=P(r*0.86,0); t2=P(r*1.02,16); c1=P(r*0.9,-34); c2=P(r*0.9,34)
        ps.append(f"<path d='M{cx:.1f} {cy:.1f}Q{c1[0]:.1f} {c1[1]:.1f} {t1[0]:.1f} {t1[1]:.1f}L{n[0]:.1f} {n[1]:.1f}L{t2[0]:.1f} {t2[1]:.1f}Q{c2[0]:.1f} {c2[1]:.1f} {cx:.1f} {cy:.1f}Z'/>")
    return f"<g fill='{fill}'>{''.join(ps)}</g><circle cx='{cx:.1f}' cy='{cy:.1f}' r='{r*0.18:.1f}' fill='{center}'/>"
def momiji(cx,cy,r,fill,rot=0):
    pts=[]; N=7*6
    for i in range(N):
        t=2*math.pi*i/N
        tip=1.0 if (i%6)==0 else (0.62 if (i%6) in (2,4) else (0.42 if (i%6)==3 else 0.78))
        lob=i//6; sc=0.62 if lob in (3,4) else (0.85 if lob in (2,5) else 1.0)
        ang=t+math.radians(rot); rr=r*tip*sc
        pts.append((cx+rr*math.sin(ang), cy-rr*math.cos(ang)))
    d='M'+'L'.join(f"{x:.1f} {y:.1f}" for x,y in pts)+'Z'
    st=(cx+r*0.7*math.sin(math.radians(rot+180)), cy-r*0.7*math.cos(math.radians(rot+180)))
    return f"<path d='{d}' fill='{fill}'/><path d='M{cx:.1f} {cy:.1f}L{st[0]:.1f} {st[1]:.1f}' stroke='{fill}' stroke-width='1.2'/>"
def yukiwa(cx,cy,R,fill,stroke):
    pts=[]
    for i in range(240):
        t=2*math.pi*i/240; rr=R*(1-0.16*abs(math.cos(3*t))**10)
        pts.append((cx+rr*math.cos(t), cy+rr*math.sin(t)))
    return f"<path d='M{'L'.join(f'{x:.1f} {y:.1f}' for x,y in pts)}Z' fill='{fill}' stroke='{stroke}' stroke-width='1'/>"
def ume(cx,cy,r,fill,center):
    g=''.join(f"<circle cx='{cx+r*0.55*math.cos(math.radians(a-90)):.1f}' cy='{cy+r*0.55*math.sin(math.radians(a-90)):.1f}' r='{r*0.5:.1f}' fill='{fill}'/>" for a in range(0,360,72))
    return g+f"<circle cx='{cx}' cy='{cy}' r='{r*0.3:.1f}' fill='{center}'/>"

NAVY='#1c2a4f'; GOLD='#c9a24a'; GOLD2='#e2c47a'
def seig_mound(cx, cy, R, fill, ring1, ring2, sw=1.4):
    g=[f"<circle cx='{cx}' cy='{cy}' r='{R}' fill='{fill}'/>"]
    for i,k in enumerate((0.96,0.76,0.56,0.36,0.16)):
        g.append(f"<circle cx='{cx}' cy='{cy}' r='{R*k:.1f}' fill='none' stroke='{ring1 if i%2==0 else ring2}' stroke-width='{sw}'/>")
    return ''.join(g)
def brush(d, w=3, col=GOLD2, op=.8):
    return f"<path d='{d}' stroke='{col}' stroke-width='{w}' fill='none' stroke-linecap='round' opacity='{op}'/>"
def flecks(r, n, x0, y0, W, H, col=GOLD2):
    return ''.join(f"<rect x='{x0+r.uniform(0,W):.1f}' y='{y0+r.uniform(0,H):.1f}' width='{r.uniform(2,5):.1f}' height='{r.uniform(2,5):.1f}' fill='{col}' opacity='{r.uniform(.55,.95):.2f}' transform='rotate({r.uniform(0,90):.0f} {x0+W/2:.0f} {y0+H/2:.0f})'/>" for _ in range(n))

# 月の帯（季節の地色に、金の筆の線・金箔・左下の青海波）
def band(base, ring, seed):
    r=random.Random(seed); W,H=400,64
    g=[f"<rect width='{W}' height='{H}' fill='{base}'/>"]
    for (x,y,R) in ((-6,74,46),(40,82,38),(86,90,30)):
        g.append(seig_mound(x,y,R,base,ring,'rgba(255,255,255,.18)',1.2))
    g.append(brush("M250 8 Q300 2 350 14 T410 6",3.2)); g.append(brush("M268 20 Q320 14 372 24",1.4,op=.6))
    g.append(brush("M150 60 Q200 50 240 58",1.6,op=.5))
    g.append(flecks(r,16,120,4,270,56))
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMid slice'>{''.join(g)}</svg>"

# 空いたマスの飾り（青海波に季節のもの）
def deco(season):
    W,H=220,120; r=random.Random(5); g=[]
    pal={'shogatsu':('#e9eef6','#c9a24a','#1c2a4f'),'haru':('#f3e9ec','#c9a24a','#b98a96'),'natsu':('#e6eef4','#c9a24a','#5b7fa6'),
         'aki':('#eaeef3','#c9a24a','#7f93ad'),'fuyu':('#eef1f5','#b9c3cf','#8fa1b6')}[season]
    for (x,y,R) in ((178,132,58),(112,138,48),(232,136,44),(60,142,36)):
        g.append(seig_mound(x,y,R,pal[0],pal[1],pal[2],1.5))
    g.append(flecks(r,14,10,10,200,60))
    if season=='aki':
        g.append(brush("M222 14 Q182 26 156 50 Q136 68 112 78",2.6,'#6e4b33',1))
        g.append(momiji(176,36,20,'#d0573c',15)); g.append(momiji(138,62,15,'#e0873a',-25)); g.append(momiji(204,64,13,'#c24a33',40))
    elif season=='haru':
        g.append(brush("M222 10 Q180 22 150 46 Q130 62 104 72",2.4,'#7a5a4a',1))
        for (x,y,s,rt) in ((176,30,14,10),(140,56,11,40),(204,58,10,-20),(112,70,8,15)): g.append(sakura(x,y,s,'#f2c4cc','#c76f80',rt))
    elif season=='natsu':
        for (y,c) in ((30,'#7d9cc0'),(44,'#5b7fa6'),(58,'#94b2d0')):
            d=f"M0 {y}"+''.join(f" Q{x+12} {y-8} {x+25} {y} T{x+50} {y}" for x in range(0,220,50))
            g.append(f"<path d='{d}' stroke='{c}' stroke-width='2.2' fill='none' opacity='.9'/>")
    elif season=='fuyu':
        g.append(yukiwa(176,44,24,'#fbfcfd','#9fb1c4')); g.append(yukiwa(132,64,16,'#fbfcfd','#a9b9ca')); g.append(yukiwa(206,74,12,'#fbfcfd','#b7c5d3'))
    elif season=='shogatsu':
        g.append(brush("M222 12 Q186 22 160 44 Q142 60 118 70",2.6,'#4a3a2a',1))
        for (x,y,s) in ((178,30,10),(150,50,8),(204,52,7),(126,64,6)): g.append(ume(x,y,s,'#d8344a' if s>7 else '#fbfbf7','#e9c46a'))
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMax meet'>{''.join(g)}</svg>"
# 月の初めの空いたマス用（季節の物は入れず、青海波と金箔だけ）
def deco_lead():
    W,H=220,120; r=random.Random(21); g=[]
    for (x,y,R) in ((30,132,52),(92,138,42),(-10,128,40),(150,142,32)):
        g.append(seig_mound(x,y,R,'#eef1f5','#c9a24a','#8fa1b6',1.4))
    g.append(flecks(r,12,20,10,190,60)); g.append(brush("M10 22 Q70 10 130 24",1.6,op=.55))
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMax meet'>{''.join(g)}</svg>"
# 画面の下の隅（濃紺の青海波に金の輪）
def corner(flip=False):
    W,H=200,110; g=[]
    for (x,y,R) in ((180,118,60),(112,124,50),(48,128,40),(220,96,40)):
        g.append(seig_mound(x,y,R,NAVY,GOLD,'rgba(226,196,122,.45)',1.5))
    g.append(flecks(random.Random(3),10,20,10,160,50))
    t=" transform='translate(200,0) scale(-1,1)'" if flip else ''
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}'><g{t}>{''.join(g)}</g></svg>"

if __name__=='__main__':
    out={'washi':uri(washi()), 'corner_l':uri(corner(True)), 'corner_r':uri(corner()), 'deco_lead':uri(deco_lead()),
         'band_shogatsu':uri(band('#1c2a4f','rgba(226,196,122,.55)',1)), 'band_haru':uri(band('#5a3448','rgba(226,196,122,.5)',2)),
         'band_natsu':uri(band('#1f3f66','rgba(220,232,245,.45)',3)), 'band_aki':uri(band('#1c2a4f','rgba(226,196,122,.55)',4)),
         'band_fuyu':uri(band('#2b3445','rgba(210,220,232,.45)',5))}
    for s in ('shogatsu','haru','natsu','aki','fuyu'): out['deco_'+s]=uri(deco(s))
    json.dump(out, open('washi-uris.json','w'))
    for k,v in out.items(): print(k, len(v))
