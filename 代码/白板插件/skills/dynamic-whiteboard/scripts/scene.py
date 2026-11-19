"""白板场景（page.board）的校验，以及旧格式（canvas 图元 / 只有标题的页）到场景的转换。

场景是纯数据：
{"v": 2, "transition": "blend|push|lift|cut|zoom", "bg": 颜色?, "cam": [{"at","x","y","z","dur","reset"}]?,
 "els": [元素…]}
元素公共字段：id、k（text circle rect path icon image）、at、dur、in、ease、loop、move、moveAt、moveDur、along、alongDur、
alpha、rot、top、glow、shadow、rel、kf、line（速写行号，仅用于提示）。
坐标：x 为舞台宽度 %，y 为高度 %；字号、半径为高度 %；path.d 用 1600×1000 的舞台像素。
"""
import json
import math
import pathlib
import re

KINDS = {'text', 'circle', 'rect', 'path', 'icon', 'image'}
ENTRIES = {'none', 'fade', 'rise', 'drop', 'up', 'down', 'left', 'right', 'slide', 'pop', 'zoom', 'spin', 'blur', 'wipe',
           'grow', 'stretch', 'bounce', 'type', 'chars', 'draw'}
LOOPS = {'float', 'pulse', 'sway', 'turn', 'spinfast', 'blink', 'breathe', 'shake', 'orbit', 'bob', 'flow', 'dot'}
TRANSITIONS = {'blend', 'push', 'lift', 'cut', 'zoom'}
EASES = {'out', 'back', 'smooth', 'linear', 'in', 'spring'}
FONTS = {'sans', 'serif', 'kai', 'hand', 'round', 'mono'}
NAMED = {'ink', 'muted', 'line', 'paper', 'orange', 'peach', 'pink', 'rose', 'white', 'black', 'none'}
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
ICON_FILE = pathlib.Path(__file__).resolve().parent.parent / 'engine' / 'icons.json'
_icons = None

LIMITS = {'els': 48, 'chars': 600, 'text': 240, 'd': 20000, 'time': 60}


def icon_names():
    global _icons
    if _icons is None:
        try:
            _icons = set(json.loads(ICON_FILE.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            _icons = set()
    return _icons


def color_ok(c, allow_grad=False):
    if not isinstance(c, str):
        return False
    if allow_grad and '>' in c:
        return all(color_ok(p.strip()) for p in c.split('>')) and 2 <= len(c.split('>')) <= 4
    return c in NAMED or bool(HEX.match(c))


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def validate_scene(scene):
    def bad(msg):
        raise ValueError('场景：' + msg)
    if not isinstance(scene, dict) or scene.get('v') != 2:
        bad('需要 {"v": 2, "els": [...]}')
    if set(scene) - {'v', 'els', 'transition', 'bg', 'cam'}:
        bad('未知字段 ' + '、'.join(sorted(set(scene) - {'v', 'els', 'transition', 'bg', 'cam'})))
    if scene.get('transition', 'blend') not in TRANSITIONS:
        bad('transition 可选 ' + '、'.join(sorted(TRANSITIONS)))
    if 'bg' in scene and not color_ok(scene['bg']):
        bad('bg 颜色无效')
    for c in scene.get('cam', []) or []:
        if not isinstance(c, dict) or set(c) - {'at', 'x', 'y', 'z', 'dur', 'reset'}:
            bad('cam 项字段为 at x y z dur reset')
        if not c.get('reset') and not (_num(c.get('x'), -50, 150) and _num(c.get('y'), -50, 150) and _num(c.get('z', 1), 0.2, 8)):
            bad('cam 需要 x、y（0–100）和 z（0.2–8）')
    els = scene.get('els')
    if not isinstance(els, list) or len(els) > LIMITS['els']:
        bad('els 为 0–%d 个元素' % LIMITS['els'])
    ids, chars = set(), 0
    for e in els:
        if not isinstance(e, dict) or e.get('k') not in KINDS:
            bad('元素类型应为 ' + '、'.join(sorted(KINDS)))
        eid = e.get('id')
        if not isinstance(eid, str) or not re.match(r'^[A-Za-z0-9_\-]{1,48}$', eid) or eid in ids:
            bad('元素 id 需唯一，只含字母数字 - _（%r）' % eid)
        ids.add(eid)
        for key in ('at', 'dur', 'moveAt', 'moveDur', 'alongDur'):
            if key in e and not _num(e[key], 0, LIMITS['time']):
                bad('%s 的 %s 应为 0–%d 秒' % (eid, key, LIMITS['time']))
        if 'in' in e and e['in'] not in ENTRIES:
            bad('%s 的出场 %r 无效' % (eid, e['in']))
        if 'loop' in e and (not isinstance(e['loop'], list) or set(e['loop']) - LOOPS):
            bad('%s 的持续动作无效' % eid)
        if 'ease' in e and e['ease'] not in EASES:
            bad('%s 的 ease 无效' % eid)
        if 'alpha' in e and not _num(e['alpha'], 0, 1):
            bad('%s 的 alpha 应为 0–1' % eid)
        if 'rot' in e and not _num(e['rot'], -720, 720):
            bad('%s 的 rot 无效' % eid)
        if 'move' in e and not (isinstance(e['move'], list) and len(e['move']) == 2 and all(_num(v, -200, 200) for v in e['move'])):
            bad('%s 的 move 应为 [dx, dy]' % eid)
        for key in ('color', 'stroke'):
            if key in e and not color_ok(e[key]):
                bad('%s 的 %s 颜色无效' % (eid, key))
        if 'fill' in e and not color_ok(e['fill'], allow_grad=True):
            bad('%s 的 fill 无效' % eid)
        k = e['k']
        if k in ('text', 'circle', 'icon', 'rect', 'image'):
            if not (_num(e.get('x'), -100, 200) and _num(e.get('y'), -100, 200)):
                bad('%s 需要 x、y' % eid)
        if k == 'text':
            runs = e.get('runs')
            if not isinstance(runs, list) or not runs or not all(isinstance(r, dict) and isinstance(r.get('t'), str) for r in runs):
                bad('%s 需要 runs' % eid)
            n = sum(len(r['t']) for r in runs)
            if n > LIMITS['text']:
                bad('%s 文字超过 %d 字' % (eid, LIMITS['text']))
            chars += n
            if not _num(e.get('size', 6), 1, 80):
                bad('%s 字号应为 1–80' % eid)
            if e.get('font', 'sans') not in FONTS:
                bad('%s 字体可选 %s' % (eid, '、'.join(sorted(FONTS))))
            for r in runs:
                if 'c' in r and not color_ok(r['c']):
                    bad('%s 文字颜色无效' % eid)
        elif k == 'circle':
            if not _num(e.get('r'), 0, 200):
                bad('%s 需要半径 r' % eid)
        elif k in ('rect', 'image'):
            if not (_num(e.get('w'), 0, 300) and _num(e.get('h'), 0, 300)):
                bad('%s 需要 w、h' % eid)
            if k == 'image':
                src = e.get('src')
                if not isinstance(src, str) or pathlib.Path(src).suffix.lower() not in IMAGE_EXT:
                    bad('%s 的图片需为 png/jpg/gif/webp/svg 路径' % eid)
        elif k == 'path':
            d = e.get('d')
            if not isinstance(d, str) or not d.strip() or len(d) > LIMITS['d'] or not re.match(r'^[MLCQZAHVSTmlcqzahvst0-9.,\-\s e]+$', d):
                bad('%s 的路径无效' % eid)
        elif k == 'icon':
            names = icon_names()
            if names and e.get('name') not in names:
                bad('%s 的图标 %r 不存在' % (eid, e.get('name')))
            if not _num(e.get('size', 8), 0.5, 120):
                bad('%s 的图标大小无效' % eid)
    if chars > LIMITS['chars']:
        bad('一页文字合计超过 %d 字' % LIMITS['chars'])
    return scene


# ---------- 旧格式转换 ----------

WEIGHT = {'light': 300, 'regular': 400, 'semibold': 600}
MOTION = {'none': 'none', 'fade': 'fade', 'rise': 'rise', 'slide': 'slide', 'pop': 'pop', 'draw': 'draw'}


def _vlen(s):
    return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in s) or 1.0


def _pts(points):
    return [(p[0] * 1600, p[1] * 1000) for p in points]


def _d(node):
    pts = _pts(node['points'])
    if node['type'] == 'bezier':
        out = 'M%.1f %.1f' % pts[0]
        for i in range(1, len(pts), 3):
            out += ' C%.1f %.1f %.1f %.1f %.1f %.1f' % (pts[i] + pts[i + 1] + pts[i + 2])
        return out
    return 'M' + ' L'.join('%.1f %.1f' % p for p in pts)


def _head(node):
    pts = _pts(node['points'])
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    L = 14 + 3 * node.get('stroke', 2)
    p1 = (x1 - L * math.cos(a - 0.42), y1 - L * math.sin(a - 0.42))
    p2 = (x1 - L * math.cos(a + 0.42), y1 - L * math.sin(a + 0.42))
    return 'M%.1f %.1f L%.1f %.1f L%.1f %.1f Z' % (p1 + (x1, y1) + p2)


def from_canvas(canvas, side=False):
    """旧 canvas（0–1 坐标的基础图元）→ 场景。side=True 时画在右侧 55% 的配图区。"""
    els = []
    ox, sx = (0.44, 0.5) if side else (0.06, 0.88)
    oy, sy = (0.14, 0.72) if side else (0.1, 0.8)
    Y = lambda v: (oy + v * sy) * 100
    for i, n in enumerate(canvas.get('nodes', [])):
        nid = n.get('id') or 'n%d' % i
        e = {'id': nid}
        if n.get('motion') in MOTION:
            e['in'] = MOTION[n['motion']]
        if n.get('delay'):
            e['at'] = n['delay']
        if n.get('duration'):
            e['dur'] = n['duration']
        X = lambda v: (ox + v * sx) * 100
        t = n['type']
        if t == 'text':
            al = {'left': 'l', 'center': 'c', 'right': 'r'}.get(n.get('align', 'left'), 'l')
            x = n.get('x', 0)
            w = n.get('w', 1 - x)
            ax = x + (w / 2 if al == 'c' else w if al == 'r' else 0)
            cap = n.get('size', 0.1) * 100 * (0.8 if side else 0.62)
            fit = w * 100 * sx / (_vlen(n['text']) * 0.625) * 0.95
            e.update(k='text', x=X(ax), y=Y(n.get('y', 0)), size=round(max(2.0, min(cap * sy, fit)), 2),
                     weight=WEIGHT.get(n.get('weight', 'regular'), 400), color=n.get('color', 'ink'), align=al,
                     runs=[{'t': n['text']}], nowrap=True, w=None)
            e.pop('w')
        elif t in ('rect', 'circle'):
            if t == 'circle':
                e.update(k='circle', x=X(n['x'] + n['w'] / 2), y=Y(n['y'] + n['h'] / 2), r=n['h'] / 2 * 100 * sy)
            else:
                e.update(k='rect', x=X(n['x']), y=Y(n['y']), w=n['w'] * 100 * sx, h=n['h'] * 100 * sy)
            if n.get('fill', 'none') != 'none':
                e['fill'] = n['fill']
            if n.get('color', 'ink') != 'none' and (n.get('fill', 'none') == 'none' or 'color' in n):
                e['stroke'] = n.get('color', 'ink')
                e['sw'] = n.get('stroke', 1.5) * 1.6
        else:
            pts = [[ox + p[0] * sx, oy + p[1] * sy] for p in n['points']]
            node = dict(n, points=pts)
            e.update(k='path', d=_d(node), stroke=n.get('color', 'ink'), sw=n.get('stroke', 2) * 1.6)
            if n.get('marker'):
                e['dot'] = {'c': n['marker'].get('color', 'ink'), 'r': n['marker'].get('radius', 5) * 1.4, 'dur': n['marker'].get('duration', 1.2)}
            if t == 'arrow':
                els.append(e)
                e = {'id': nid + '-head', 'k': 'path', 'd': _head(node), 'fill': n.get('color', 'ink'), 'in': 'fade',
                     'at': (n.get('delay', 0) or 0) + (n.get('duration', 0.8) or 0.8)}
        if n.get('timeline'):
            kf = {}
            for tr in n['timeline']:
                prop = {'x': 'x', 'y': 'y', 'scale': 'scale', 'rotation': 'rotate', 'opacity': 'opacity'}.get(tr['property'])
                if prop:
                    scale = 100 * sx if prop == 'x' else 100 * sy if prop == 'y' else 1
                    kf[prop] = [[k[0], k[1] * scale] for k in tr['keys']]
            if kf:
                e['kf'] = kf
        els.append(e)
    return {'v': 2, 'transition': {'crossfade': 'blend', 'cut': 'cut', 'lift': 'lift', 'push': 'push'}.get(canvas.get('transition'), 'blend'),
            'els': els}


def from_title(title, body=''):
    """只有一句话的页：左侧偏上，大字。"""
    text = (title or '').replace('**', '')
    size = max(5.0, min(11.0, 92 * 1.6 / max(1, len(text)) / 1.05))
    els = [{'id': 'title', 'k': 'text', 'x': 8, 'y': 34, 'size': round(size, 1), 'weight': 500, 'color': 'ink', 'runs': [{'t': text}], 'w': 84}]
    if body:
        els.append({'id': 'body', 'k': 'text', 'x': 8, 'y': 34 + size * 1.4 + 3, 'size': 3.2, 'color': 'muted', 'runs': [{'t': body}], 'w': 70, 'at': 0.2})
    return {'v': 2, 'transition': 'blend', 'els': els}


def page_scene(page):
    if isinstance(page.get('board'), dict):
        return page['board']
    if page.get('canvas'):
        try:
            side = page.get('visualStyle') == 'live-side'
            sc = from_canvas(page['canvas'], side=side)
            if side and page.get('title'):
                text = page['title'].replace('**', '')
                size = max(4.0, min(7.5, 36 * 1.6 / max(1, len(text)) * 1.9))
                sc['els'].insert(0, {'id': 'title', 'k': 'text', 'x': 6, 'y': 38, 'w': 34, 'size': round(size, 1), 'weight': 500,
                                     'runs': [{'t': text}]})
            return sc
        except (KeyError, TypeError, IndexError, ValueError):
            pass
    return from_title(page.get('title', ''), page.get('body', ''))
