"""常用图形宏：把 wave / curve / flow / cycle / bars 展开成播放器认识的基础图元。

纯数据进、纯数据出，在校验之前运行；原生播放器永远只看到
text / line / polyline / rect / circle / arrow / bezier。
坐标与 canvas 一致：0–1 归一化，左上角为原点，y 向下。
"""
import math

STYLE = ('color', 'stroke', 'motion', 'delay', 'duration', 'timeline', 'marker', 'fill')
TEXT_STYLE = ('size', 'weight', 'color', 'motion', 'effect')


def _r(v):
    return round(v, 4)


def _pt(x, y):
    return [_r(min(1.0, max(0.0, x))), _r(min(1.0, max(0.0, y)))]


def _num(n, key, default, lo, hi, kind):
    v = n.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError('%s 的 %s 应为 %g–%g 的数字' % (kind, key, lo, hi))
    return float(v)


def _box(n, kind, dx=0.5, dy=0.3, dw=0.45, dh=0.4):
    x = _num(n, 'x', dx, 0, 1, kind)
    y = _num(n, 'y', dy, 0, 1, kind)
    w = _num(n, 'w', dw, 0.02, 1, kind)
    h = _num(n, 'h', dh, 0.02, 1, kind)
    return x, y, min(w, 1 - x) or w, min(h, 1 - y) or h


def _items(n, kind, lo, hi):
    items = n.get('items')
    if not isinstance(items, list) or not lo <= len(items) <= hi or not all(isinstance(t, str) and 1 <= len(t.strip()) <= 40 for t in items):
        raise ValueError('%s 的 items 应为 %d–%d 个短文字（每个 ≤40 字）' % (kind, lo, hi))
    return [t.strip() for t in items]


def _only(n, kind, allowed):
    extra = set(n) - set(allowed) - {'type', 'id'}
    if extra:
        raise ValueError('%s 不支持字段：%s' % (kind, '、'.join(sorted(extra))))


def _style(n, keys=STYLE):
    return {k: n[k] for k in keys if k in n}


def _delay(v):
    return _r(min(1.0, max(0.0, v)))


def wave(n):
    """正弦波。cycles 个完整周期（0.5–5），amp 为占半高的比例，decay 每半周衰减。"""
    _only(n, 'wave', ('x', 'y', 'w', 'h', 'cycles', 'amp', 'decay', 'flip') + STYLE)
    x, y, w, h = _box(n, 'wave')
    halves = int(round(_num(n, 'cycles', 2, 0.5, 5, 'wave') * 2))
    amp = _num(n, 'amp', 1, 0, 1, 'wave') * h / 2
    decay = _num(n, 'decay', 1, 0.1, 1, 'wave')
    mid, seg = y + h / 2, w / halves
    first = 1 if n.get('flip') else -1          # 默认第一段向上（y 变小）
    pts = [_pt(x, mid)]
    for i in range(halves):
        k = 4 / 3 * amp * decay ** i * (first if i % 2 == 0 else -first)
        x0 = x + i * seg
        pts += [_pt(x0 + seg * 0.33, mid + k), _pt(x0 + seg * 0.67, mid + k), _pt(x0 + seg, mid)]
    out = {'type': 'bezier', 'points': pts}
    if 'id' in n:
        out['id'] = n['id']
    out.update(_style(n))
    out.setdefault('motion', 'draw')
    return [out]


def _head(base_id, tip, tail, n, extra_delay):
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    d = math.hypot(dx, dy) or 1.0
    start = [tip[0] - dx / d * 0.03, tip[1] - dy / d * 0.03]
    head = {'type': 'arrow', 'points': [_pt(*start), _pt(*tip)], 'motion': 'fade',
            'delay': _delay(n.get('delay', 0) + extra_delay)}
    if base_id:
        head['id'] = base_id + '-head'
    for k in ('color', 'stroke'):
        if k in n:
            head[k] = n[k]
    return head


def curve(n):
    """从 from 到 to 的弧线；bend 为弯曲量（相对长度，正负决定方向）；head=true 加箭头。"""
    _only(n, 'curve', ('from', 'to', 'bend', 'head') + STYLE)
    ends = []
    for key in ('from', 'to'):
        p = n.get(key)
        if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in p)):
            raise ValueError('curve 需要 from 和 to，各为 0–1 的 [x, y]')
        ends.append([float(p[0]), float(p[1])])
    (x1, y1), (x2, y2) = ends
    bend = _num(n, 'bend', 0.25, -1, 1, 'curve')
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 0.01:
        raise ValueError('curve 的起点和终点太近')
    nx, ny = -dy / length * bend * length, dx / length * bend * length
    c1 = (x1 + dx / 3 + nx, y1 + dy / 3 + ny)
    c2 = (x1 + 2 * dx / 3 + nx, y1 + 2 * dy / 3 + ny)
    body = {'type': 'bezier', 'points': [_pt(x1, y1), _pt(*c1), _pt(*c2), _pt(x2, y2)]}
    if 'id' in n:
        body['id'] = n['id']
    body.update(_style(n))
    body.setdefault('motion', 'draw')
    out = [body]
    if n.get('head'):
        out.append(_head(n.get('id'), (x2, y2), c2, n, n.get('duration', 0.9)))
    return out


def flow(n):
    """一排（或一列）步骤，中间自动加箭头。items 2–5 个。"""
    _only(n, 'flow', ('items', 'x', 'y', 'w', 'h', 'direction', 'size', 'weight', 'color', 'arrow_color', 'stroke', 'motion'))
    items = _items(n, 'flow', 2, 5)
    x, y, w, h = _box(n, 'flow', 0.04, 0.38, 0.92, 0.24)
    column = n.get('direction', 'row') == 'column'
    if n.get('direction', 'row') not in ('row', 'column'):
        raise ValueError('flow 的 direction 为 row 或 column')
    base = n.get('id', 'flow')
    k = len(items)
    gap = 0.5
    span = h if column else w
    cell = span / (k + (k - 1) * gap)
    stagger = min(0.22, 0.9 / k)
    size = _num(n, 'size', min(0.14, (cell if column else h) * 0.8), 0.03, 0.6, 'flow')
    out = []
    for i, text in enumerate(items):
        start = (y if column else x) + i * cell * (1 + gap)
        if column:
            box = dict(x=_r(x), y=_r(start), w=_r(w), h=_r(cell))
        else:
            box = dict(x=_r(start), y=_r(y), w=_r(cell), h=_r(h))
        node = {'id': '%s-%d' % (base, i), 'type': 'text', 'text': text, 'size': _r(size), 'align': 'center',
                'motion': n.get('motion', 'rise'), 'delay': _delay(i * stagger)}
        node.update(box)
        for key in ('weight', 'color'):
            if key in n:
                node[key] = n[key]
        out.append(node)
        if i < k - 1:
            a, b = start + cell + cell * gap * 0.15, start + cell + cell * gap * 0.85
            mid = (x + w / 2) if column else (y + h / 2)
            pts = [_pt(mid, a), _pt(mid, b)] if column else [_pt(a, mid), _pt(b, mid)]
            out.append({'id': '%s-to%d' % (base, i + 1), 'type': 'arrow', 'points': pts,
                        'color': n.get('arrow_color', 'orange'), 'stroke': n.get('stroke', 3),
                        'motion': 'draw', 'delay': _delay(i * stagger + stagger * 0.6)})
    return out


def _arc(cx, cy, rx, ry, a0, a1):
    k = 4 / 3 * math.tan((a1 - a0) / 4)
    p0 = (cx + rx * math.cos(a0), cy + ry * math.sin(a0))
    p1 = (cx + rx * math.cos(a1), cy + ry * math.sin(a1))
    d0 = (-rx * math.sin(a0), ry * math.cos(a0))
    d1 = (-rx * math.sin(a1), ry * math.cos(a1))
    c1 = (p0[0] + k * d0[0], p0[1] + k * d0[1])
    c2 = (p1[0] - k * d1[0], p1[1] - k * d1[1])
    return p0, c1, c2, p1


def cycle(n):
    """首尾相接的循环：items 3–5 个绕椭圆排开（从正上方顺时针），之间用弧线连接。"""
    _only(n, 'cycle', ('items', 'x', 'y', 'w', 'h', 'size', 'weight', 'color', 'arrow_color', 'stroke', 'heads'))
    items = _items(n, 'cycle', 3, 5)
    x, y, w, h = _box(n, 'cycle', 0.25, 0.08, 0.5, 0.84)
    base = n.get('id', 'cycle')
    k = len(items)
    heads = n.get('heads', k <= 4)
    if heads and k > 4:
        raise ValueError('cycle 超过 4 项时不能加箭头（会超过 12 个图元）')
    tw, th = min(0.24, w * 0.42), min(0.16, h * 0.22)
    cx, cy = x + w / 2, y + h / 2
    rx, ry = max(0.02, w / 2 - tw / 2), max(0.02, h / 2 - th / 2)
    size = _num(n, 'size', min(0.1, th * 0.75), 0.03, 0.6, 'cycle')
    step = 2 * math.pi / k
    gap = min(0.5, step * 0.3)
    stagger = min(0.2, 0.9 / k)
    texts, arcs = [], []
    for i, text in enumerate(items):
        a = -math.pi / 2 + i * step
        px, py = cx + rx * math.cos(a), cy + ry * math.sin(a)
        node = {'id': '%s-%d' % (base, i), 'type': 'text', 'text': text, 'align': 'center', 'size': _r(size),
                'x': _r(min(1 - tw, max(0, px - tw / 2))), 'y': _r(min(1 - th, max(0, py - th / 2))),
                'w': _r(tw), 'h': _r(th), 'motion': 'pop', 'delay': _delay(i * stagger)}
        for key in ('weight', 'color'):
            if key in n:
                node[key] = n[key]
        texts.append(node)
        p0, c1, c2, p1 = _arc(cx, cy, rx, ry, a + gap, a + step - gap)
        arc = {'id': '%s-arc%d' % (base, i), 'type': 'bezier', 'points': [_pt(*p0), _pt(*c1), _pt(*c2), _pt(*p1)],
               'color': n.get('arrow_color', 'orange'), 'stroke': n.get('stroke', 3), 'motion': 'draw',
               'delay': _delay(0.3 + i * stagger), 'duration': 0.8}
        arcs.append(arc)
        if heads:
            arcs.append(_head(arc['id'], p1, c2, {'color': arc['color'], 'stroke': arc['stroke'], 'delay': arc['delay']}, 0.75))
    return texts + arcs


def bars(n):
    """柱状对比：values 1–6 个非负数，labels 可选（与 values 等长）。"""
    _only(n, 'bars', ('values', 'labels', 'x', 'y', 'w', 'h', 'max', 'color', 'colors', 'size'))
    values = n.get('values')
    if not isinstance(values, list) or not 1 <= len(values) <= 6 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in values):
        raise ValueError('bars 的 values 应为 1–6 个非负数')
    labels = n.get('labels')
    if labels is not None and (not isinstance(labels, list) or len(labels) != len(values) or not all(isinstance(t, str) and 1 <= len(t) <= 40 for t in labels)):
        raise ValueError('bars 的 labels 应与 values 等长，每个 1–40 字')
    colors = n.get('colors')
    if colors is not None and (not isinstance(colors, list) or len(colors) != len(values)):
        raise ValueError('bars 的 colors 应与 values 等长')
    x, y, w, h = _box(n, 'bars', 0.52, 0.1, 0.44, 0.8)
    top = n.get('max', max(values) or 1)
    if isinstance(top, bool) or not isinstance(top, (int, float)) or top <= 0:
        raise ValueError('bars 的 max 应为正数')
    base = n.get('id', 'bars')
    k = len(values)
    label_h = min(0.12, h * 0.18) if labels else 0
    plot = h - label_h - (0.02 if labels else 0)
    slot = w / k
    bw = slot * 0.62
    size = _num(n, 'size', label_h * 0.8 if labels else 0.06, 0.03, 0.6, 'bars')
    out = []
    for i, v in enumerate(values):
        bh = max(0.0, min(1.0, v / top)) * plot
        bx = x + i * slot + (slot - bw) / 2
        rect = {'id': '%s-%d' % (base, i), 'type': 'rect', 'x': _r(bx), 'y': _r(y + plot - bh), 'w': _r(bw),
                'h': _r(bh), 'fill': (colors[i] if colors else n.get('color', 'orange')), 'color': 'none',
                'motion': 'rise', 'delay': _delay(i * 0.12)}
        out.append(rect)
    if labels:
        for i, text in enumerate(labels):
            out.append({'id': '%s-label%d' % (base, i), 'type': 'text', 'text': text, 'align': 'center',
                        'x': _r(x + i * slot), 'y': _r(y + h - label_h), 'w': _r(slot), 'h': _r(label_h),
                        'size': _r(size), 'color': 'ink', 'motion': 'fade', 'delay': _delay(0.2 + i * 0.12)})
    return out


EXPANDERS = {'wave': wave, 'curve': curve, 'flow': flow, 'cycle': cycle, 'bars': bars}


def expand_nodes(nodes):
    if not isinstance(nodes, list):
        return nodes
    out = []
    counters = {}
    for n in nodes:
        kind = n.get('type') if isinstance(n, dict) else None
        if kind in EXPANDERS:
            n = dict(n)
            if 'id' not in n:
                counters[kind] = counters.get(kind, 0) + 1
                n['id'] = '%s%d' % (kind, counters[kind])
            out.extend(EXPANDERS[kind](n))
        else:
            out.append(n)
    return out


def expand_canvas(canvas):
    if not isinstance(canvas, dict) or not isinstance(canvas.get('nodes'), list):
        return canvas
    result = dict(canvas)
    result['nodes'] = expand_nodes(canvas['nodes'])
    return result
