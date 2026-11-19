"""白板速写：一行画一个元素，编译成新播放器的场景（page.board）。

    == 振幅越大，听起来越响。 | push
    振幅越大，**听起来越响**。 | 7,18 l light w:40
    w 58,20 36x22 3 pink @soft
    w 58,56 36x36 3 orange w4 flow @loud
    i ear 90,84 7 pink pulse
    分贝越高 | below:@loud s muted

坐标 0–100：x 为舞台宽度 %，y 为高度 %（舞台 16:10）。字号和半径按高度 %。
完整说明见 references/sketch.md。
"""
import math
import random
import re
import zlib
import difflib

import shapes
import scene as scenes

SX, SY = 16.0, 10.0                     # 百分比 → 舞台像素（1600×1000）
ASPECT = 1.6
STEP = 0.15
COLORS = {'ink': 'ink', 'muted': 'muted', 'line': 'line', 'paper': 'paper', 'white': 'white', 'black': 'black',
          'orange': 'orange', 'pink': 'pink', 'rose': 'pink', 'peach': 'peach',
          '墨': 'ink', '黑': 'ink', '灰': 'muted', '橙': 'orange', '粉': 'pink', '杏': 'peach', '白': 'white'}
SIZES = {'xs': 2.4, 's': 3.2, 'm': 4.5, 'l': 7, 'xl': 10, 'xxl': 15, 'huge': 22}
WEIGHTS = {'thin': 200, 'light': 300, 'regular': 400, 'medium': 500, 'bold': 600, 'heavy': 800, '细': 300, '粗': 600}
FONTS = {'sans', 'serif', 'kai', 'hand', 'round', 'mono'}
ENTRIES = {'rise', 'fade', 'pop', 'slide', 'draw', 'none', 'left', 'right', 'up', 'down', 'drop', 'zoom', 'spin', 'blur',
           'wipe', 'grow', 'stretch', 'bounce', 'type', 'chars'}
LOOPS = {'float', 'pulse', 'sway', 'turn', 'spinfast', 'blink', 'breathe', 'shake', 'orbit', 'bob', 'flow'}
TRANSITIONS = {'blend', 'push', 'lift', 'cut', 'zoom'}
EASES = {'out', 'back', 'smooth', 'linear', 'in', 'spring'}
SIGILS = {'o': 'circle', 'b': 'box', '-': 'line', '->': 'arrow', '<-': 'arrow_start', '<->': 'arrow_both', '~': 'curve',
          '~>': 'carrow', '<~': 'carrow_start', '<~>': 'carrow_both', 'w': 'wave', 'p': 'poly', 'blob': 'blob', 'arc': 'arc',
          'i': 'icon', 'img': 'image', 'cam': 'cam'}
RELS = {'below', 'above', 'left', 'right', 'on'}

POINT = re.compile(r'^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$')
BOX = re.compile(r'^(\d+(?:\.\d+)?)[x×](\d+(?:\.\d+)?)$')
NUM = re.compile(r'^-?\d*\.?\d+$')
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')

HELP = ('速写每行一个元素：「文字 | 参数」，或 o 圆、b 方框、- 线、-> 箭头、~ 曲线、~> 曲线箭头、w 波、p 多边形、blob 有机形、'
        'arc 弧、i 图标、img 图片、cam 镜头。文字恰好以这些记号加空格开头时，用引号包住。完整说明见 references/sketch.md。')


class SketchError(ValueError):
    pass


def err(ln, msg):
    return SketchError(('第 %d 行：' % ln if ln else '') + msg)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def r1(v):
    return round(v, 2)


def vlen(s):
    return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in s) or 1.0


def crc(s):
    return '%04x' % (zlib.crc32(s.encode('utf-8')) & 0xFFFF)


def color(tok):
    low = tok.lower()
    if low in COLORS:
        return COLORS[low]
    if HEX.match(tok):
        return tok
    return None


def fill_color(tok):
    if '>' in tok:
        parts = [color(p) for p in tok.split('>')]
        if all(parts) and 2 <= len(parts) <= 4:
            return '>'.join(parts)
        return None
    return color(tok)


# ---------- 解析 ----------

def parse_flags(tokens, ln, header=False):
    f = {}
    for tok in tokens:
        low = tok.lower()
        m = POINT.match(tok)
        if m:
            f.setdefault('pts', []).append([float(m.group(1)), float(m.group(2))])
            continue
        m = BOX.match(low)
        if m:
            f['box'] = [float(m.group(1)), float(m.group(2))]
            continue
        if low.endswith('%') and NUM.match(low[:-1]):
            f['alpha'] = clamp(float(low[:-1]) / 100, 0, 1)
            continue
        if low.endswith('deg') and NUM.match(low[:-3]):
            f['rot'] = clamp(float(low[:-3]), -720, 720)
            continue
        if low.startswith('+') and NUM.match(low[1:]):
            f['at'] = clamp(float(low[1:]), 0, 59)
            continue
        if low.startswith('+') and fill_color(tok[1:]):
            f['fill'] = fill_color(tok[1:])
            continue
        if color(tok):
            f['color'] = color(tok)
            continue
        if re.match(r'^w\d+(\.\d+)?$', low):
            f['stroke'] = clamp(float(low[1:]), 0.5, 20)
            continue
        if tok.startswith('@') and re.match(r'^@[A-Za-z0-9_\-]{1,40}$', tok):
            f['id'] = tok[1:]
            continue
        if ':' in low:
            key, _, val = low.partition(':')
            raw_val = tok.split(':', 1)[1]
            if key == 'to' and POINT.match(val):
                mm = POINT.match(val)
                f['to'] = [float(mm.group(1)), float(mm.group(2))]
                continue
            if key in RELS and raw_val.startswith('@'):
                f['rel'] = {'side': key, 'to': raw_val[1:]}
                continue
            if key == 'along' and raw_val.startswith('@'):
                f['along'] = raw_val[1:]
                continue
            if key == 'dot':
                c = color(raw_val)
                if not c:
                    raise err(ln, 'dot:颜色 里的颜色看不懂：%s' % raw_val)
                f['dot'] = c
                continue
            if key == 'glow':
                c = color(raw_val)
                if not c:
                    raise err(ln, 'glow:颜色 里的颜色看不懂：%s' % raw_val)
                f['glow'] = c
                continue
            if key in ('w', 'gap', 'lh', 'ls', 'dur', 'round', 'size') and NUM.match(val):
                v = float(val)
                f[{'w': 'tw', 'size': 'size'}.get(key, key)] = v
                continue
            if key == 'ease' and val in EASES:
                f['ease'] = val
                continue
            if key == 'bg' and header and color(raw_val):
                f['bg'] = color(raw_val)
                continue
            raise err(ln, '看不懂「%s」。%s' % (tok, HELP))
        if low in SIZES:
            f['size'] = SIZES[low]
            continue
        if NUM.match(low):
            f.setdefault('nums', []).append(float(low))
            continue
        if low in WEIGHTS:
            f['weight'] = WEIGHTS[low]
        elif low in FONTS:
            f['font'] = low
        elif low in ('c', 'center'):
            f['align'] = 'c'
        elif low in ('r',):
            f['align'] = 'r'
        elif low in ('u', 'underline'):
            f['underline'] = True
        elif low == 'glow':
            f['glow'] = True
        elif low == 'shadow':
            f['shadow'] = True
        elif low in ('dash', 'dots'):
            f['dash'] = low
        elif low == 'round':
            f['round'] = 1.6
        elif low == 'count':
            f['count'] = True
        elif low == 'nowrap':
            f['nowrap'] = True
        elif low == 'top':
            f['top'] = True
        elif low == 'dot':
            f['dot'] = True
        elif low == 'reset':
            f['reset'] = True
        elif low == 'loop':
            f['loopit'] = True
        elif low in ENTRIES:
            f['motion'] = low
        elif low in LOOPS:
            f.setdefault('loop', [])
            if low not in f['loop']:
                f['loop'].append(low)
        elif low in ('slow', 'fast'):
            f['speed'] = low
        elif low == '&':
            f['with'] = True
        elif header and low in TRANSITIONS:
            f['transition'] = low
        elif header and low == 'plain':
            f['plain'] = True
        else:
            hint = difflib.get_close_matches(low, list(ENTRIES | LOOPS | set(WEIGHTS) | FONTS | set(COLORS) | set(SIZES)), 1)
            raise err(ln, '看不懂「%s」%s。%s' % (tok, '（是不是 %s？）' % hint[0] if hint else '', HELP))
    return f


def strip_quotes(s):
    s = s.strip()
    if len(s) >= 2 and s[0] + s[-1] in ('""', '“”', "''", '「」'):
        return s[1:-1]
    return s


def uncomment(raw):
    line = raw.strip()
    if line.startswith('//'):
        return ''
    return re.split(r'\s+//', line, 1)[0].strip()


def parse_line(line, ln):
    head = line.split(None, 1)
    if head and head[0] in SIGILS:
        kind = SIGILS[head[0]]
        rest = head[1] if len(head) > 1 else ''
        tokens = rest.split()
        spec = {'kind': kind, 'ln': ln}
        if kind == 'icon':
            if not tokens:
                raise err(ln, 'i 后面写图标名，例如 i heart 50,50 10')
            spec['name'] = tokens.pop(0).lower()
        elif kind == 'image':
            if not tokens:
                raise err(ln, 'img 后面写图片路径，例如 img ~/Pictures/a.png 10,10 40x30')
            spec['src'] = tokens.pop(0)
        spec['f'] = parse_flags(tokens, ln)
        return spec
    if '|' in line:
        text, params = line.split('|', 1)
    else:
        text, params = line, ''
    text = strip_quotes(text)
    if not text:
        raise err(ln, '文字是空的')
    plain = re.sub(r'\*\*|__|~~|\{[a-z#0-9]+:|\}', '', text).replace('\\n', '')
    if len(plain) > 200:
        raise err(ln, '一段文字最多 200 字（现在 %d 字）。白板上只留关键句，解释写在聊天里。' % len(plain))
    return {'kind': 'text', 'text': text, 'f': parse_flags(params.split(), ln), 'ln': ln}


def is_sketch(src):
    if not isinstance(src, str):
        return False
    lines = [x.strip() for x in src.strip().splitlines() if x.strip()]
    if not lines:
        return False
    if len(lines) > 1 or lines[0].startswith('==') or '|' in lines[0]:
        return True
    return lines[0].split(None, 1)[0] in SIGILS


def parse_pages(src):
    pages, cur = [], None
    for ln, raw in enumerate(src.splitlines(), 1):
        line = uncomment(raw)
        if not line:
            continue
        if line.startswith('=='):
            body = line[2:].strip()
            text, params = (body.split('|', 1) + [''])[:2] if '|' in body else (body, '')
            text = strip_quotes(text)
            if not text:
                raise err(ln, '== 后面要写这一页要说的话')
            cur = {'text': text, 'head': parse_flags(params.split(), ln, header=True), 'specs': [], 'ln': ln}
            pages.append(cur)
            continue
        if cur is None:
            cur = {'text': None, 'head': {}, 'specs': [], 'ln': ln}
            pages.append(cur)
        cur['specs'].append(parse_line(line, ln))
    for p in pages:
        if p['text'] is None:
            texts = [plain_text(s['text']) for s in p['specs'] if s['kind'] == 'text']
            p['text'] = '，'.join(texts)[:120] if texts else '（图）'
    return pages


# ---------- 富文本 ----------

RUN = re.compile(r'\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\{([a-z]+|#[0-9a-fA-F]{6}):(.+?)\}')


def plain_text(t):
    return RUN.sub(lambda m: next(g for g in m.groups()[::-1] if g is not None) if m.group(5) is None else m.group(5), t).replace('\\n', '\n')


def runs_of(text, accent):
    out, pos = [], 0
    text = text.replace('\\n', '\n')
    for m in RUN.finditer(text):
        if m.start() > pos:
            out.append({'t': text[pos:m.start()]})
        if m.group(1) is not None:
            out.append({'t': m.group(1), 'b': 1, 'c': accent})
        elif m.group(2) is not None:
            out.append({'t': m.group(2), 'hl': 'pink' if accent != 'pink' else 'peach'})
        elif m.group(3) is not None:
            out.append({'t': m.group(3), 'st': 1})
        else:
            c = color(m.group(4))
            if not c:
                raise SketchError('文字里的 {颜色:…} 颜色看不懂：%s' % m.group(4))
            out.append({'t': m.group(5), 'c': c})
        pos = m.end()
    if pos < len(text):
        out.append({'t': text[pos:]})
    return [r for r in out if r['t']] or [{'t': ' '}]


# ---------- 几何 ----------

def px(pt):
    return (pt[0] * SX, pt[1] * SY)


def fmt(*pts):
    return ' '.join('%.1f %.1f' % p for p in pts)


def smooth_d(points):
    """Catmull-Rom 穿过所有点；首尾同点时闭合。points 为舞台像素。"""
    closed = len(points) > 3 and math.dist(points[0], points[-1]) < 0.5
    if closed:
        pts = points[:-1]
        n = len(pts)
        d = 'M' + fmt(pts[0])
        for i in range(n):
            p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += ' C' + fmt(c1, c2, p2)
        return d + ' Z'
    p = [points[0]] + points + [points[-1]]
    d = 'M' + fmt(points[0])
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += ' C' + fmt(c1, c2, p2)
    return d


def bend_d(a, b, bend):
    dx, dy = b[0] - a[0], b[1] - a[1]
    nx, ny = -dy * bend, dx * bend
    return 'M%s C%s' % (fmt(a), fmt((a[0] + dx / 3 + nx, a[1] + dy / 3 + ny), (a[0] + 2 * dx / 3 + nx, a[1] + 2 * dy / 3 + ny), b))


def blob_d(cx, cy, r, seed, lobes=8):
    rng = random.Random(seed)
    pts = []
    for i in range(lobes):
        a = 2 * math.pi * i / lobes + rng.uniform(-0.18, 0.18)
        rr = r * rng.uniform(0.8, 1.16)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return smooth_d(pts + [pts[0]])


def arc_d(cx, cy, R, a0, a1, wedge):
    span = (a1 - a0) % 360 or 360
    pt = lambda a: (cx + R * math.sin(math.radians(a)), cy - R * math.cos(math.radians(a)))
    if span >= 359.9:
        p0, pm = pt(a0), pt(a0 + 180)
        d = 'M%s A%.1f %.1f 0 1 1 %s A%.1f %.1f 0 1 1 %s' % (fmt(p0), R, R, fmt(pm), R, R, fmt(p0))
        return d + (' Z' if wedge else '')
    p0, p1 = pt(a0), pt(a0 + span)
    large = 1 if span > 180 else 0
    if wedge:
        return 'M%s L%s A%.1f %.1f 0 %d 1 %s Z' % (fmt((cx, cy)), fmt(p0), R, R, large, fmt(p1))
    return 'M%s A%.1f %.1f 0 %d 1 %s' % (fmt(p0), R, R, large, fmt(p1))


def wave_d(x, y, w, h, cycles, amp):
    nodes = shapes.wave({'id': 'w', 'x': clamp(x / 100, 0, 1), 'y': clamp(y / 100, 0, 1), 'w': clamp(w / 100, 0.02, 1),
                         'h': clamp(h / 100, 0.02, 1), 'cycles': clamp(cycles, 0.5, 5), 'amp': clamp(amp, 0, 1)})
    pts = [(p[0] * 1600, p[1] * 1000) for p in nodes[0]['points']]
    d = 'M' + fmt(pts[0])
    for i in range(1, len(pts), 3):
        d += ' C' + fmt(pts[i], pts[i + 1], pts[i + 2])
    return d


def path_len(d):
    nums = [float(v) for v in re.findall(r'-?\d*\.?\d+', d)]
    pts = list(zip(nums[0::2], nums[1::2]))
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) if len(pts) > 1 else 0


# ---------- 构建 ----------

def text_size(f, default):
    if 'size' in f:
        return clamp(f['size'], 1.2, 60)
    nums = f.get('nums') or []
    return clamp(nums[0], 1.2, 60) if nums else default


def estimate_text_box(e):
    """估算文字外框（%）：真机以渲染引擎测量为准，这里只用于 check 的提示和相对定位的近似。"""
    text = ''.join(r['t'] for r in e['runs'])
    lines = text.split('\n')
    size = e.get('size', 4.5)
    char_w = size * SY / SX
    al = e.get('align', 'l')
    room = (2 * min(e['x'], 100 - e['x']) if al == 'c' else e['x'] if al == 'r' else 100 - e['x']) - 3
    width_cap = e.get('w') or max(5, room)
    n_lines, widest = 0, 0
    for line in lines:
        w = vlen(line) * char_w
        if e.get('nowrap'):
            n_lines += 1
            widest = max(widest, w)
        else:
            n_lines += max(1, math.ceil(w / width_cap - 1e-9))
            widest = max(widest, min(w, width_cap))
    if e.get('w'):
        widest = e['w']
    h = n_lines * size * (e.get('lh') or (1.08 if size > 7 else 1.22))
    left = e['x'] - (widest / 2 if al == 'c' else widest if al == 'r' else 0)
    return [left, e['y'], widest, h]


def build(page, prior=None):
    """page: {'text','head','specs'} → (scene 或 None, specs)。"""
    head, specs = page['head'], page['specs']
    if head.get('plain'):
        return None, specs
    if not any(s['kind'] == 'text' for s in specs):
        specs = auto_text(page['text'], head) + specs
    els, used, counters = [], set(), {}
    cams = []
    clock = last_delay = 0.0
    last_text = None
    lead_group = []
    for s in specs:
        if s['kind'] != 'text':
            continue
        if s['f'].get('pts') or s.get('_pos') or s['f'].get('rel'):
            break
        lead_group.append(s)
    total = 0
    for s in lead_group:
        size = text_size(s['f'], 4.5)
        est = estimate_text_box({'x': 8, 'y': 0, 'size': size, 'runs': [{'t': plain_text(s['text'])}], 'w': s['f'].get('tw'),
                                 'lh': s['f'].get('lh')})
        total += est[3] + 2.5
    flow_y = max(5.0, (100 - total) / 2)
    for s in specs:
        f, kind = s['f'], s['kind']
        if '_t' in s:
            delay = s['_t']
        elif 'at' in f:
            delay = f['at']
        elif f.get('with'):
            delay = last_delay
        else:
            delay = clock
        s['_t'] = delay
        clock, last_delay = max(clock, delay + STEP), delay
        speed = {'slow': 1.8, 'fast': 0.55}.get(f.get('speed'), 1.0)
        if kind == 'cam':
            nums = f.get('nums') or []
            c = {'at': r1(delay)}
            if f.get('reset'):
                c['reset'] = True
            else:
                if not f.get('pts'):
                    raise err(s.get('ln'), 'cam 需要中心点和倍数，例如 cam 70,40 1.8 +2')
                c.update(x=f['pts'][0][0], y=f['pts'][0][1], z=clamp(nums[0] if nums else 1.6, 0.3, 6))
            c['dur'] = r1(f.get('dur', 1.3) * speed)
            cams.append(c)
            continue
        nid = f.get('id') or s.get('id')
        if not nid:
            if kind == 'text':
                nid = 't' + crc(s['text'])
            else:
                letter = {'circle': 'o', 'box': 'b', 'line': 'l', 'arrow': 'a', 'arrow_start': 'a', 'arrow_both': 'a', 'curve': 'c',
                          'carrow': 'c', 'carrow_start': 'c', 'carrow_both': 'c', 'wave': 'w', 'poly': 'p', 'blob': 'blob',
                          'arc': 'arc', 'icon': 'i', 'image': 'img'}[kind]
                counters[letter] = counters.get(letter, 0) + 1
                nid = '%s%d' % (letter, counters[letter])
                while nid in used or (prior and nid in prior):
                    counters[letter] += 1
                    nid = '%s%d' % (letter, counters[letter])
        base, n = nid, 2
        while nid in used:
            nid = '%s-%d' % (base, n)
            n += 1
        s['id'] = nid
        used.add(nid)
        e = {'id': nid, 'at': r1(delay)}
        if s.get('ln'):
            e['line'] = s['ln']
        pts = f.get('pts') or []
        nums = f.get('nums') or []
        if kind == 'text':
            accent = f.get('accent') or ('pink' if f.get('color') == 'orange' else 'orange')
            size = text_size(f, 4.5)
            if '_pos' in s:
                x, y = s['_pos']
                align = s.get('_align', 'l')
            elif pts:
                x, y = pts[0]
                align = f.get('align', 'l')
            elif f.get('rel'):
                x, y, align = 50, 50, 'c'
            elif last_text is not None:
                x, y, align = last_text['x'], last_text['y'] + last_text['h'] + 2.5, last_text['align']
                align = f.get('align', align)
            else:
                x, y, align = 8, flow_y, f.get('align', 'l')
            s['_pos'], s['_align'] = [r1(x), r1(y)], align
            e.update(k='text', x=r1(x), y=r1(y), size=size, runs=runs_of(s['text'], accent))
            if align != 'l':
                e['align'] = align
            for key, out in (('weight', 'weight'), ('font', 'font'), ('color', 'color'), ('tw', 'w'), ('lh', 'lh'), ('ls', 'ls'),
                             ('nowrap', 'nowrap'), ('count', 'count'), ('glow', 'glow')):
                if key in f:
                    e[out] = f[key]
            if f.get('underline'):
                for r in e['runs']:
                    r['hl'] = r.get('hl') or 'peach'
            if f.get('rel'):
                e['rel'] = dict(f['rel'], gap=f.get('gap', 2))
            box = estimate_text_box(e)
            last_text = {'x': x, 'y': y, 'h': box[3], 'align': align}
            anchor = (x, y)
        elif kind == 'circle':
            if not pts:
                raise err(s.get('ln'), 'o 需要圆心，例如 o 30,50 12')
            e.update(k='circle', x=pts[0][0], y=pts[0][1], r=clamp(nums[0] if nums else 2, 0.2, 120))
            anchor = tuple(pts[0])
        elif kind == 'box':
            if not pts or not f.get('box'):
                raise err(s.get('ln'), 'b 需要左上角和宽x高，例如 b 10,20 30x40')
            e.update(k='rect', x=pts[0][0], y=pts[0][1], w=f['box'][0], h=f['box'][1])
            if 'round' in f:
                e['rx'] = clamp(f['round'], 0, 50)
            anchor = tuple(pts[0])
        elif kind == 'icon':
            if not pts:
                raise err(s.get('ln'), 'i 需要中心点，例如 i heart 50,50 10')
            names = scenes.icon_names()
            if names and s['name'] not in names:
                close = difflib.get_close_matches(s['name'], list(names), 4)
                raise err(s.get('ln'), '没有叫「%s」的图标。%s图标用 Lucide 的英文名（如 heart、dumbbell、chart-line）。'
                          % (s['name'], ('相近的有：%s。' % '、'.join(close)) if close else ''))
            e.update(k='icon', name=s['name'], x=pts[0][0], y=pts[0][1], size=clamp(nums[0] if nums else 8, 1, 100))
            anchor = tuple(pts[0])
        elif kind == 'image':
            if not pts or not f.get('box'):
                raise err(s.get('ln'), 'img 需要左上角和宽x高，例如 img ~/a.png 10,10 40x30')
            import os
            src = os.path.expanduser(s['src'])
            if not os.path.isfile(src):
                raise err(s.get('ln'), '找不到图片：%s' % s['src'])
            e.update(k='image', src=src, x=pts[0][0], y=pts[0][1], w=f['box'][0], h=f['box'][1])
            if 'round' in f:
                e['rx'] = f['round']
            anchor = tuple(pts[0])
        else:
            e['k'] = 'path'
            if kind == 'wave':
                if not pts or not f.get('box'):
                    raise err(s.get('ln'), 'w 需要左上角和宽x高，例如 w 10,60 80x20 3')
                e['d'] = wave_d(pts[0][0], pts[0][1], f['box'][0], f['box'][1], nums[0] if nums else 2, nums[1] if len(nums) > 1 else 1)
            elif kind == 'blob':
                if not pts:
                    raise err(s.get('ln'), 'blob 需要中心和大小，例如 blob 70,50 20')
                r = clamp(nums[0] if nums else 12, 1, 80) * SY
                e['d'] = blob_d(pts[0][0] * SX, pts[0][1] * SY, r, int(nums[1]) if len(nums) > 1 else zlib.crc32(nid.encode()))
            elif kind == 'arc':
                if not pts or len(nums) < 3:
                    raise err(s.get('ln'), 'arc 需要圆心、半径、起止角度（0 在正上方，顺时针），例如 arc 50,50 20 0 270')
                e['d'] = arc_d(pts[0][0] * SX, pts[0][1] * SY, clamp(nums[0], 0.5, 80) * SY, nums[1], nums[2], bool(f.get('fill')))
            elif kind == 'poly':
                if len(pts) < 3:
                    raise err(s.get('ln'), 'p 至少三个点，例如 p 10,80 30,40 50,80')
                e['d'] = 'M' + ' L'.join(fmt(px(p)) for p in pts) + ' Z'
            else:
                if len(pts) < 2:
                    raise err(s.get('ln'), '线至少需要两个点，例如 -> 10,50 60,50')
                if len(pts) > 24:
                    raise err(s.get('ln'), '一条线最多 24 个点')
                P = [px(p) for p in pts]
                if kind.startswith('curve') or kind.startswith('carrow'):
                    e['d'] = bend_d(P[0], P[1], nums[0]) if len(P) == 2 and nums else smooth_d(P)
                else:
                    e['d'] = 'M' + ' L'.join(fmt(p) for p in P)
                if kind in ('arrow', 'carrow'):
                    e['head'] = 'end'
                elif kind in ('arrow_start', 'carrow_start'):
                    e['head'] = 'start'
                elif kind in ('arrow_both', 'carrow_both'):
                    e['head'] = 'both'
            anchor = tuple(pts[0]) if pts else (50, 50)
            closed = e['d'].rstrip().endswith('Z')
            if f.get('fill') and closed:
                e['fill'] = f['fill']
                if f.get('color'):
                    e['stroke'] = f['color']
            else:
                e['stroke'] = f.get('color', 'orange')
                if f.get('fill') and closed:
                    e['fill'] = f['fill']
            if kind in ('blob', 'poly') and not f.get('fill') and not f.get('color'):
                e['fill'] = 'peach'
                e.pop('stroke', None)
            if 'stroke' in e:
                e['sw'] = r1((f.get('stroke') or 2) * 1.8)
            if f.get('dot'):
                e['dot'] = {'c': f['dot'] if isinstance(f['dot'], str) else 'ink'}
            if f.get('dash'):
                e['dash'] = f['dash']
        # 通用样式
        if kind in ('circle', 'box'):
            if f.get('fill'):
                e['fill'] = f['fill']
                if f.get('color'):
                    e['stroke'] = f['color']
            else:
                e['stroke'] = f.get('color', 'ink')
            if 'stroke' in e:
                e['sw'] = r1((f.get('stroke') or 1.5) * 1.8)
            if f.get('dash'):
                e['dash'] = f['dash']
        if kind == 'icon':
            e['color'] = f.get('color', 'ink')
            if f.get('fill'):
                e['fill'] = f['fill']
            if f.get('stroke'):
                e['sw'] = r1(f['stroke'] * 1.8)
        if f.get('rel') and kind != 'text':
            e['rel'] = dict(f['rel'], gap=f.get('gap', 2))
        for key in ('alpha', 'rot', 'top', 'shadow'):
            if key in f:
                e[key] = f[key]
        if 'glow' in f and kind != 'text':
            e['glow'] = f['glow']
        if f.get('motion'):
            e['in'] = f['motion']
        if f.get('loop'):
            e['loop'] = list(f['loop'])
        if f.get('dur'):
            e['dur'] = r1(clamp(f['dur'], 0.05, 30))
        elif speed != 1.0:
            e['dur'] = r1((0.7 if kind == 'text' else 1.0) * speed)
        if f.get('ease'):
            e['ease'] = f['ease']
        if f.get('to'):
            e['move'] = [r1(f['to'][0] - anchor[0]), r1(f['to'][1] - anchor[1])]
        if f.get('along'):
            e['along'] = f['along']
            if f.get('loopit') or 'flow' in (f.get('loop') or []):
                e['alongLoop'] = True
            if f.get('dur'):
                e['alongDur'] = e.pop('dur')
        els.append(e)
    for e in els:
        for ref in (e.get('rel') or {}).get('to'), e.get('along'):
            if ref and ref not in used:
                raise err(e.get('line'), '找不到 @%s（只能引用这一页里已命名的元素）' % ref)
    out = {'v': 2, 'els': els}
    if head.get('transition'):
        out['transition'] = head['transition']
    if head.get('bg'):
        out['bg'] = head['bg']
    if cams:
        out['cam'] = cams
    try:
        scenes.validate_scene(out)
    except ValueError as exc:
        raise err(page.get('ln'), str(exc))
    build.last_warnings = check_layout(els)
    return out, specs


build.last_warnings = []


def auto_text(sentence, head):
    """整页没写文字时，显示 == 那句话：有 **重点** 时分成两行，重点加粗上色。"""
    plain = plain_text(sentence)
    marks = re.findall(r'\*\*(.+?)\*\*', sentence)
    lead, key = '', plain
    if marks:
        key = marks[0]
        i = plain.find(key)
        lead, key = plain[:i].strip(), (key + plain[i + len(key):]).strip()
    elif len(plain) > 14:
        cut = max(plain.rfind(p) for p in '，、：；,:;')
        if 0 < cut < len(plain) - 1:
            lead, key = plain[:cut + 1], plain[cut + 1:].strip()
    x0 = head['pts'][0][0] if head.get('pts') else 8
    room = {'c': 2 * min(x0, 100 - x0), 'r': x0}.get(head.get('align'), 100 - x0) - 6
    fit = lambda t, cap: round(max(3.0, min(cap, room / (vlen(t) * SY / SX))), 1)
    size = head.get('size') or (head.get('nums') or [None])[0] or fit(key, 10 if lead else 12)
    base = {k: head[k] for k in ('pts', 'align', 'motion', 'loop', 'speed', 'at', 'font') if k in head}
    specs = []
    if lead:
        specs.append({'kind': 'text', 'text': lead, 'f': dict(base, size=min(fit(lead, 7), round(size * 0.62, 1)), weight=300), 'auto': True})
        fk = {k: v for k, v in base.items() if k not in ('pts', 'at')}
        fk.update(size=size, weight=600, color=head.get('color', 'orange'))
        specs.append({'kind': 'text', 'text': key, 'f': fk, 'auto': True})
    else:
        specs.append({'kind': 'text', 'text': key, 'f': dict(base, size=size, weight=600, color=head.get('color', 'ink')), 'auto': True})
    return specs


def check_layout(els):
    """估算排版问题（真机由渲染引擎测量后再报一次）。"""
    boxes = {}
    for e in els:
        if e['k'] == 'text' and not e.get('rel'):
            boxes[e['id']] = estimate_text_box(e)
    warns = []
    label = lambda e: ('第 %d 行' % e['line'] if e.get('line') else '自动显示的句子') + '「%s」' % plain_text(''.join(r['t'] for r in e['runs']))[:8]
    texts = [e for e in els if e['id'] in boxes]
    for i, a in enumerate(texts):
        ba = boxes[a['id']]
        if ba[0] + ba[2] > 101 or ba[0] < -1 or ba[1] + ba[3] > 101:
            warns.append('%s 可能超出画面。' % label(a))
        for b in texts[i + 1:]:
            bb = boxes[b['id']]
            ix = min(ba[0] + ba[2], bb[0] + bb[2]) - max(ba[0], bb[0])
            iy = min(ba[1] + ba[3], bb[1] + bb[3]) - max(ba[1], bb[1])
            if ix > 0.5 and iy > 0.5 and ix * iy > 0.1 * min(ba[2] * ba[3], bb[2] * bb[3]):
                warns.append('%s 和 %s 可能重叠。' % (label(a), label(b)))
    return warns[:6]


def compile_page(text, body=''):
    specs = []
    for ln, raw in enumerate(body.splitlines(), 1):
        line = uncomment(raw)
        if line:
            specs.append(parse_line(line, ln))
    build.last_warnings = []
    sc, specs = build({'text': text, 'head': {}, 'specs': specs})
    return {'text': plain_text(text).replace('\n', ' ').strip(), 'board': sc, 'specs': specs, 'head': {}, 'raw': text,
            'warnings': list(build.last_warnings)}


def compile_sketch(src):
    out = []
    for page in parse_pages(src):
        build.last_warnings = []
        sc, specs = build(page)
        out.append({'text': plain_text(page['text']).replace('\n', ' ').strip(), 'board': sc, 'specs': specs, 'head': page['head'],
                    'raw': page['text'], 'warnings': list(build.last_warnings)})
    return out


# ---------- 编辑 ----------

def edit_specs(record, src):
    specs = [dict(s, f=dict(s['f'])) for s in record['specs']]
    text, head = record['text'], dict(record.get('head') or {})
    fresh = 0.0
    for ln, raw in enumerate(src.splitlines(), 1):
        line = uncomment(raw)
        if not line:
            continue
        if line.startswith('=='):
            body = line[2:].strip()
            t, params = (body.split('|', 1) + [''])[:2] if '|' in body else (body, '')
            text = strip_quotes(t) or text
            if params.strip():
                head.update(parse_flags(params.split(), ln, header=True))
            if any(s.get('auto') for s in specs):
                specs = auto_text(text, head) + [s for s in specs if not s.get('auto')]
            continue
        parts = line.split()
        if parts[0] in ('x', 'del') and len(parts) == 2 and parts[1].startswith('@'):
            target = parts[1][1:]
            before = len(specs)
            specs = [s for s in specs if s.get('id') != target and s['f'].get('id') != target]
            if len(specs) == before:
                raise err(ln, '没有 @%s。现有：%s' % (target, '、'.join('@' + s['id'] for s in specs if s.get('id'))))
            continue
        if parts[0].startswith('@') and len(parts[0]) > 1:
            target = parts[0][1:]
            hit = [s for s in specs if s.get('id') == target or s['f'].get('id') == target]
            if not hit:
                raise err(ln, '没有 @%s。现有：%s' % (target, '、'.join('@' + s['id'] for s in specs if s.get('id'))))
            rest = line[len(parts[0]):].strip()
            if hit[0]['kind'] == 'text':
                if '|' in rest:
                    newtext, rest = rest.split('|', 1)
                    if newtext.strip():
                        hit[0]['text'] = strip_quotes(newtext)
                elif rest and not _parses(rest):
                    hit[0]['text'] = strip_quotes(rest)
                    rest = ''
            changes = parse_flags(rest.split(), ln)
            for key, value in changes.items():
                if key not in ('id', 'at', 'with'):
                    hit[0]['f'][key] = value
            if 'pts' in changes or 'rel' in changes:
                hit[0].pop('_pos', None)
            continue
        spec = parse_line(line, ln)
        f = spec['f']
        spec['_t'] = f['at'] if 'at' in f else (fresh - STEP if f.get('with') else fresh)
        spec['_t'] = max(0.0, spec['_t'])
        fresh = spec['_t'] + STEP
        specs.append(spec)
    return {'text': text, 'head': head, 'specs': specs}


def _parses(rest):
    try:
        parse_flags(rest.split(), 0)
        return True
    except SketchError:
        return False


def rebuild(record):
    prior = {s['id'] for s in record['specs'] if s.get('id')}
    build.last_warnings = []
    return build({'text': record['text'], 'head': record.get('head') or {}, 'specs': record['specs']}, prior)


def clean_specs(specs):
    return [dict(s) for s in specs]
