# 和紙の手帳カレンダー用の文様を SVG で作り、CSS の data URI にする
import math, random, urllib.parse, json
def uri(svg):
    svg = ' '.join(svg.split())
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg, safe=" =:/,'.-();") + '")'

# --- 和紙の繊維（細い繊維を散らす。薄く） ---
def washi(seed=7, size=260, n=70, col='120,95,55'):
    r = random.Random(seed); paths=[]
    for i in range(n):
        x=r.uniform(0,size); y=r.uniform(0,size); L=r.uniform(14,46); a=r.uniform(0,math.pi)
        x2=x+L*math.cos(a); y2=y+L*math.sin(a)
        cx=(x+x2)/2+r.uniform(-8,8); cy=(y+y2)/2+r.uniform(-8,8)
        op=r.uniform(.10,.24); w=r.uniform(.35,.8)
        paths.append(f"<path d='M{x:.1f} {y:.1f}Q{cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}' stroke='rgba({col},{op:.2f})' stroke-width='{w:.2f}' fill='none'/>")
    dots=''.join(f"<circle cx='{r.uniform(0,size):.1f}' cy='{r.uniform(0,size):.1f}' r='{r.uniform(.3,.9):.2f}' fill='rgba({col},{r.uniform(.08,.18):.2f})'/>" for _ in range(50))
    return f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}'>{''.join(paths)}{dots}</svg>"

# --- 青海波（1周期のタイル） ---
def seigaiha(stroke, bg, W=36, sw=1):
    R=W/2; H=R/2
    out=[f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H*1:.0f}' viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='{bg}'/>"]
    for row in range(-3,5):
        y=row*H/1
        off=0 if row%2==0 else R
        for k in range(-1,3):
            x=k*W+off
            out.append(f"<circle cx='{x}' cy='{y}' r='{R}' fill='{bg}'/>")
            for rr in (R*0.92, R*0.68, R*0.44, R*0.2):
                out.append(f"<circle cx='{x}' cy='{y}' r='{rr:.2f}' fill='none' stroke='{stroke}' stroke-width='{sw}'/>")
    out.append("</svg>")
    return ''.join(out)

# --- 麻の葉（三角の格子と、頂点から重心への線） ---
def asanoha(stroke, a=24, sw=.7):
    h=a*math.sqrt(3)/2; W=a; H=2*h
    lines=[]
    def tri(p,q,r_):
        g=((p[0]+q[0]+r_[0])/3,(p[1]+q[1]+r_[1])/3)
        for A,B in ((p,q),(q,r_),(r_,p)): lines.append((A,B))
        for A in (p,q,r_): lines.append((A,g))
    for row in range(-1,3):
        y0=row*h; off=(a/2 if row%2 else 0)
        for k in range(-1,2):
            x0=k*a+off
            tri((x0,y0),(x0+a,y0),(x0+a/2,y0+h))
            tri((x0+a/2,y0+h),(x0+a*1.5,y0+h),(x0+a,y0))
    s=''.join(f"<line x1='{A[0]:.2f}' y1='{A[1]:.2f}' x2='{B[0]:.2f}' y2='{B[1]:.2f}'/>" for A,B in lines)
    return f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H:.2f}' viewBox='0 0 {W} {H:.2f}'><g stroke='{stroke}' stroke-width='{sw}' fill='none'>{s}</g></svg>"

# --- 小さな形 ---
def sakura(cx,cy,r,fill,center,rot=0):
    ps=[]
    for i in range(5):
        a=math.radians(rot+i*72-90)
        def P(rr,da): 
            t=a+math.radians(da); return (cx+rr*math.cos(t), cy+rr*math.sin(t))
        b1=P(r*0.25,-28); t1=P(r*1.02,-16); n=P(r*0.86,0); t2=P(r*1.02,16); b2=P(r*0.25,28); c1=P(r*0.9,-34); c2=P(r*0.9,34)
        ps.append(f"<path d='M{cx:.1f} {cy:.1f}Q{c1[0]:.1f} {c1[1]:.1f} {t1[0]:.1f} {t1[1]:.1f}L{n[0]:.1f} {n[1]:.1f}L{t2[0]:.1f} {t2[1]:.1f}Q{c2[0]:.1f} {c2[1]:.1f} {cx:.1f} {cy:.1f}Z'/>")
    return f"<g fill='{fill}'>{''.join(ps)}</g><circle cx='{cx:.1f}' cy='{cy:.1f}' r='{r*0.18:.1f}' fill='{center}'/>"
def momiji(cx,cy,r,fill,rot=0):
    pts=[]; lobes=7; N=lobes*6
    for i in range(N):
        t=2*math.pi*i/N
        ph=(i%6)/6.0
        tip=1.0 if (i%6)==0 else (0.62 if (i%6) in (2,4) else (0.42 if (i%6)==3 else 0.78))
        ang=t+math.radians(rot)
        # 下の2枚は小さめ
        lob=(i//6)
        sc=0.62 if lob in (3,4) else (0.85 if lob in (2,5) else 1.0)
        rr=r*tip*sc
        pts.append((cx+rr*math.sin(ang), cy-rr*math.cos(ang)))
    d='M'+'L'.join(f"{x:.1f} {y:.1f}" for x,y in pts)+'Z'
    st=(cx+r*0.7*math.sin(math.radians(rot+180)), cy-r*0.7*math.cos(math.radians(rot+180)))
    return f"<path d='{d}' fill='{fill}'/><path d='M{cx:.1f} {cy:.1f}L{st[0]:.1f} {st[1]:.1f}' stroke='{fill}' stroke-width='1.2'/>"
def yukiwa(cx,cy,R,fill,stroke):
    pts=[]
    for i in range(240):
        t=2*math.pi*i/240
        k=abs(math.cos(3*t))**10
        rr=R*(1-0.16*k)
        pts.append((cx+rr*math.cos(t), cy+rr*math.sin(t)))
    d='M'+'L'.join(f"{x:.1f} {y:.1f}" for x,y in pts)+'Z'
    return f"<path d='{d}' fill='{fill}' stroke='{stroke}' stroke-width='1'/>"
def golddust(r, n, W, H, col='#c9a24a'):
    return ''.join(f"<rect x='{r.uniform(0,W):.1f}' y='{r.uniform(0,H):.1f}' width='{r.uniform(1,3.2):.1f}' height='{r.uniform(1,3.2):.1f}' fill='{col}' opacity='{r.uniform(.35,.8):.2f}' transform='rotate({r.uniform(0,90):.0f})'/>" for _ in range(n))

def deco(season):
    W,H=200,110; r=random.Random(11)
    g=[]
    if season=='shogatsu':
        for (x,y,R) in ((150,118,46),(95,122,40),(185,124,34),(55,128,30)):
            g.append(f"<circle cx='{x}' cy='{y}' r='{R}' fill='#f3ead6'/>")
            for k in (1.0,.78,.56,.34):
                g.append(f"<circle cx='{x}' cy='{y}' r='{R*k:.1f}' fill='none' stroke='{'#b8933a' if k in (1.0,.56) else '#2b3d66'}' stroke-width='1.3'/>")
        g.append(golddust(r,26,W,70))
    elif season=='haru':
        g.append("<path d='M200 18 Q150 30 120 62 Q100 84 70 92' stroke='#8a6a58' stroke-width='2.2' fill='none' stroke-linecap='round'/>")
        for (x,y,s,rt) in ((150,40,15,10),(112,70,12,40),(176,72,11,-20),(78,86,9,15)):
            g.append(sakura(x,y,s,'#efc3ca','#c76f80',rt))
        for (x,y,rt) in ((40,60,30),(60,30,-20),(20,92,70)):
            g.append(f"<ellipse cx='{x}' cy='{y}' rx='4' ry='2.4' fill='#efc3ca' transform='rotate({rt} {x} {y})'/>")
    elif season=='natsu':
        for i,(y,c) in enumerate(((62,'#7d9cc0'),(76,'#5b7fa6'),(90,'#94b2d0'),(104,'#5b7fa6'))):
            d=f"M0 {y}"+''.join(f" Q{x+12} {y-9+ (i%2)*3} {x+25} {y} T{x+50} {y}" for x in range(0,200,50))
            g.append(f"<path d='{d}' stroke='{c}' stroke-width='2' fill='none' opacity='.85'/>")
        for (x,y,R) in ((165,118,40),(120,124,30)):
            g.append(f"<circle cx='{x}' cy='{y}' r='{R}' fill='#eef3f6'/>")
            for k in (1.0,.72,.44):
                g.append(f"<circle cx='{x}' cy='{y}' r='{R*k:.1f}' fill='none' stroke='#5b7fa6' stroke-width='1.2'/>")
    elif season=='aki':
        g.append("<path d='M200 20 Q160 32 132 56 Q110 76 84 86' stroke='#6e4b33' stroke-width='2.2' fill='none' stroke-linecap='round'/>")
        g.append(momiji(150,46,22,'#c8553d',15)); g.append(momiji(108,74,17,'#d9893a',-25)); g.append(momiji(178,80,15,'#b84a35',40)); g.append(momiji(64,96,11,'#d9a441',-10))
    elif season=='fuyu':
        g.append(yukiwa(150,62,30,'#f4f7fa','#9fb1c4')); g.append(yukiwa(98,84,20,'#f4f7fa','#a9b9ca')); g.append(yukiwa(183,95,15,'#f4f7fa','#b7c5d3'))
        for (x,y) in ((60,50),(40,82),(78,30),(20,40)):
            g.append(f"<circle cx='{x}' cy='{y}' r='2' fill='#c5d2de'/>")
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' preserveAspectRatio='xMidYMax meet'>{''.join(g)}</svg>"

out={
 'washi': uri(washi()),
 'seig_gold': uri(seigaiha('rgba(201,162,74,.38)','#1f2d52')),
 'seig_blue': uri(seigaiha('rgba(91,127,166,.30)','#dbe6ee')),
 'asa_brown': uri(asanoha('rgba(130,92,52,.22)')),
 'asa_silver': uri(asanoha('rgba(120,135,155,.25)')),
 'petals': uri("<svg xmlns='http://www.w3.org/2000/svg' width='90' height='40'>"+sakura(18,14,6,'rgba(214,138,152,.35)','rgba(190,100,120,.4)',0)+sakura(66,28,4.5,'rgba(214,138,152,.3)','rgba(190,100,120,.35)',30)+"</svg>"),
 'yuki_small': uri("<svg xmlns='http://www.w3.org/2000/svg' width='70' height='36'>"+yukiwa(16,14,7,'rgba(255,255,255,.55)','rgba(150,165,185,.45)')+yukiwa(52,26,5,'rgba(255,255,255,.5)','rgba(150,165,185,.4)')+"</svg>"),
}
for s in ('shogatsu','haru','natsu','aki','fuyu'): out['deco_'+s]=uri(deco(s))
json.dump(out, open('washi-uris.json','w'), ensure_ascii=False)
for k,v in out.items(): print(k, len(v))
# 確認用のページ
html="<html><body style='margin:0;background:#f6f0e2'>"
for k,v in out.items():
    html+=f"<div style='display:inline-block;margin:6px;border:1px solid #999;width:220px;height:120px;background:{v};background-size:{'contain' if k.startswith('deco') else 'auto'};background-repeat:{'no-repeat' if k.startswith('deco') else 'repeat'};background-position:center bottom'><span style='font:10px sans-serif;background:#fff'>{k}</span></div>"
open('washi-preview.html','w').write(html+"</body></html>")
