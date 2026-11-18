"""Finite, pure-data drawing vocabulary; no URLs, scripts or arbitrary code."""
import math, re
PALETTE={'ink','orange','rose','muted'}
MOTIONS={'none','fade','rise','slide','pop','draw'}
def validate_canvas(canvas):
    if canvas is None:return
    if not isinstance(canvas,dict) or set(canvas)-{'nodes','transition'}:raise ValueError('canvas 仅支持 nodes/transition')
    if canvas.get('transition','crossfade') not in {'crossfade','cut','lift','push'}:raise ValueError('非法 transition')
    nodes=canvas.get('nodes')
    if not isinstance(nodes,list) or not 1<=len(nodes)<=12:raise ValueError('nodes 必须为 1–12 项')
    total=0;ids=set()
    def number(v,lo,hi):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and lo<=v<=hi
    for n in nodes:
        if not isinstance(n,dict) or set(n)-{'type','text','x','y','w','h','size','weight','align','color','fill','motion','delay','duration','points','stroke','effect','timeline','id','marker'}:raise ValueError('未知画布字段')
        if 'id' in n:
            if not isinstance(n['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',n['id']) or n['id'] in ids:raise ValueError('id 需为唯一短标识')
            ids.add(n['id'])
        if n.get('type') not in {'text','line','polyline','rect','circle','arrow','bezier'}:raise ValueError('非法图元类型')
        for k in ('x','y','w','h'):
            if k in n and not number(n[k],0,1):raise ValueError(k+' 必须归一化到 0–1')
        for k,lo,hi in [('size',0.03,0.6),('stroke',1,10),('delay',0,1),('duration',0.1,2)]:
            if k in n and not number(n[k],lo,hi):raise ValueError('非法 '+k)
        if not all(isinstance(c,str) and (c in PALETTE|{'none'} or re.fullmatch(r'#[0-9a-fA-F]{6}',c)) for c in [n.get('color','ink'),n.get('fill','none')]):raise ValueError('非法颜色')
        if n.get('motion','fade') not in MOTIONS or n.get('effect','none') not in {'none','underline','outline'}:raise ValueError('非法动效或效果')
        if n.get('weight','regular') not in {'light','regular','semibold'} or n.get('align','left') not in {'left','center','right'}:raise ValueError('非法排版')
        if 'marker' in n:
            m=n['marker']
            if (n['type'] not in {'line','polyline','bezier'} or not isinstance(m,dict)
                or set(m)!={'radius','duration','color'} or not number(m['radius'],2,18)
                or not number(m['duration'],0.1,4) or not isinstance(m['color'],str)
                or (m['color'] not in PALETTE and not re.fullmatch(r'#[0-9a-fA-F]{6}',m['color']))):
                raise ValueError('marker 需要线条、2–18pt 半径、0.1–4秒和合法颜色')
        if 'timeline' in n:
            tracks=n['timeline']
            if not isinstance(tracks,list) or not 1<=len(tracks)<=7:raise ValueError('timeline 为 1–7 条轨道')
            seen=set()
            ranges={'x':(-1,1),'y':(-1,1),'scale':(0.05,3),'rotation':(-720,720),'opacity':(0,1),'draw':(0,1)}
            for track in tracks:
                if not isinstance(track,dict) or set(track)-{'property','keys','easing'}:raise ValueError('非法时间线字段')
                prop=track.get('property')
                if prop not in ranges or prop in seen:raise ValueError('非法或重复轨道')
                seen.add(prop)
                if prop=='draw' and n['type']=='text':raise ValueError('文字不支持描边进度')
                if track.get('easing','ease') not in {'linear','ease','ease-in','ease-out'}:raise ValueError('非法缓动')
                keys=track.get('keys')
                if not isinstance(keys,list) or not 2<=len(keys)<=24:raise ValueError('轨道需 2–24 个关键帧')
                last=-1
                for key in keys:
                    if not isinstance(key,list) or len(key)!=2 or not number(key[0],0,8) or key[0]<=last or not number(key[1],*ranges[prop]):raise ValueError('关键帧为递增秒数和值，最长 8 秒')
                    last=key[0]
                if keys[0][0]!=0:raise ValueError('轨道须从 0 秒开始')
        if n['type']=='text':
            t=n.get('text')
            if not isinstance(t,str) or not 1<=len(t)<=40:raise ValueError('每段文字 1–40 字')
            total+=len(t)
        if 'points' in n:
            p=n['points']
            if not isinstance(p,list) or not 2<=len(p)<=32 or not all(isinstance(v,list) and len(v)==2 and all(number(a,0,1) for a in v) for v in p):raise ValueError('points 为 2–32 个归一化坐标')
        if n['type']=='bezier' and ('points' not in n or len(n['points'])<4 or (len(n['points'])-1)%3):raise ValueError('bezier 为起点加每段三个控制/终点')
        if n['type'] in {'line','polyline','arrow','bezier'} and 'points' not in n:raise ValueError('线图元需要 points')
    if total>80:raise ValueError('总展示文字最多 80 字；优先一句短句')

# Keyframes are bounded data, never expressions or executable code.
