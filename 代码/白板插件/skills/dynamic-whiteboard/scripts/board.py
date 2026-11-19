#!/usr/bin/env python3
"""动态白板 · 输出端命令行。任何能运行命令的大模型都可以用它把内容送到本机原生白板。

    board.py say "一句话" ["下一句" …]       显示（用户看完前面的页才跳，其余按空格看）
    board.py say < pages.json                带图的页面（JSON 从标准输入读）
    board.py ask "问题？" --choice 甲 --choice 乙   显示问题并等回答
    board.py wait [--wait 45]                继续等用户在白板上的输入
    board.py edit '@arrow pink'          原位改当前页（速写：@名字 参数 / x @名字 / 新行 / == 新句子）
    board.py close                           讲完收起
    board.py status | check | describe | doctor | demo | present --file 文稿.json | mcp

每次输出一行 JSON：ok 为 true/false，status 说明发生了什么，hint 告诉你下一步怎么做。
会话、版本号、回答事件 id 都由本程序自动维护，调用方不需要记。
"""
import argparse
import copy
import json
import os
import pathlib
import platform
import select
import subprocess
import sys
import threading
import time
import uuid

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import whiteboard as board  # noqa: E402  渲染器文件协议
import 演示文稿 as deck  # noqa: E402  文稿模型；原生播放器也会调用它
import shapes  # noqa: E402
import sketch  # noqa: E402
import scene as scene_mod  # noqa: E402
import 现场白板 as live

VERSION = '4.0.0'
DATA = board.DATA
SKILL_STATE = DATA / 'skill-state.json'
REOPEN_COOLDOWN = 20 * 60
MAX_PAGES_PER_CALL = 8


class Fail(Exception):
    def __init__(self, status, error, hint=None, **extra):
        Exception.__init__(self, error)
        self.payload = {'ok': False, 'status': status, 'error': error}
        if hint:
            self.payload['hint'] = hint
        self.payload.update(extra)


HINTS = [
    ('nodes 必须为 1–12', 'invalid', '一页最多 12 个图元（宏展开后计算）。拆成两页，或先画骨架，再用 edit 的 add 逐步补。'),
    ('总展示文字最多 80 字', 'invalid', '一页画布里的文字合计不超过 80 字。解释放在聊天正文里，白板只留关键词。'),
    ('每段文字 1–40 字', 'invalid', '单个 text 图元 1–40 字；长句拆成两个 text 或缩短。'),
    ('bezier 为起点', 'invalid', 'bezier 点数须为 4、7、10…（起点 + 每段 3 点）。画波形用 wave 宏，画弧线箭头用 curve 宏。'),
    ('points 为 2–32', 'invalid', 'points 是 2–32 个 [x, y]，每个坐标都在 0–1。'),
    ('必须归一化到 0–1', 'invalid', 'x / y / w / h 都是 0–1 的画布比例，左上角为原点，y 向下。'),
    ('非法颜色', 'invalid', '颜色用 ink / orange / rose / muted / none，或 #RRGGBB。'),
    ('未知画布字段', 'invalid', '图元可用字段见 references/canvas.md。'),
    ('非法图元类型', 'invalid', '基础类型：text line polyline rect circle arrow bezier；宏：wave curve flow cycle bars。'),
    ('id 需为唯一短标识', 'invalid', '图元 id 只用字母、数字、- 和 _，同一页内不能重复。'),
    ('选项最多三个', 'invalid', 'choices 最多 3 个，每个不超过 16 字。'),
    ('需要短 id 与主句', 'invalid', '每页都要有 text（不超过 120 字，建议 6–18 字）。'),
    ('关键帧', 'invalid', 'timeline 关键帧是 [秒, 值]，从 0 秒开始递增，最长 8 秒。'),
    ('marker', 'invalid', 'marker 只能放在 line / polyline / bezier 上，要同时给 radius(2–18)、duration(0.1–4)、color。'),
    ('canvas 仅支持', 'invalid', 'drawing / canvas 只接受 nodes 和 transition 两个字段。'),
    ('非法 transition', 'invalid', 'transition 可选 crossfade / cut / lift / push。'),
    ('非法动效', 'invalid', 'motion 可选 none / fade / rise / slide / pop / draw；effect 可选 none / underline / outline。'),
    ('请选择配图或自由画布', 'invalid', '一页只能有 drawing（文字旁配图）或 canvas（整页自由画布）其中之一。'),
    ('白板已退出', 'closed', '用户已收起白板。用文字继续；用户再次想看时用 say --new。'),
    ('会话已改变', 'closed', '白板已换成别的内容或已关闭。需要时用 say --new 重新打开。'),
    ('已切换到其他白板', 'closed', '白板正在显示别的内容。需要时用 say --new 替换。'),
    ('上一轮已结束', 'stale', '白板状态刚刚变化，请重试一次。'),
]


def explain(error):
    text = str(error)
    for needle, status, hint in HINTS:
        if needle in text:
            return Fail(status, text, hint)
    return Fail('error', text, '用 status 核对当前页，或用 check 校验本次页面。')


# ---------- 状态 ----------

def content():
    return board.read(DATA / 'content.json')


def renderer():
    return board.read(DATA / 'status.json')


def pending_event():
    return board.read(DATA / 'pending-reply.json')


def skill_state():
    return board.read(SKILL_STATE)


def save_skill(**values):
    with deck.lock():
        state = skill_state()
        state.update(values)
        board.write(SKILL_STATE, state)


def note_dismissal():
    """记录用户按 Esc 收起本技能的白板（模型主动 close 不算）。"""
    st, s = content(), renderer()
    show = s.get('showID')
    if (show and s.get('visibility') == 'dismissed' and show == st.get('showID')
            and show in (skill_state().get('showID'), skill_state().get('documentShow')) and st.get('action') != 'close'
            and skill_state().get('dismissedShow') != show):
        try:
            when = os.stat(DATA / 'status.json').st_mtime
        except OSError:
            when = time.time()
        save_skill(dismissedShow=show, dismissedAt=when)


def current_live():
    """可以继续写入的现场会话；没有则返回 None。"""
    note_dismissal()
    st, s = content(), renderer()
    if (st.get('outputSource') != 'live-tool' or not st.get('document') or st.get('action') == 'close'
            or skill_state().get('showID') != st.get('showID')):
        return None
    if s.get('showID') == st.get('showID') and s.get('visibility') == 'dismissed':
        return None
    fresh = st.get('action') == 'show' and time.time() - st.get('writtenAt', 0) < 8
    if not board.visible():
        return st if fresh else None
    if s.get('renderer') != 'engine':
        return None
    if s.get('showID') != st.get('showID') and not (st.get('action') == 'show' and st.get('writtenAt', 0) > s.get('rendererObservedAt', 0)):
        return None
    return st


def pending_for(st):
    ev = pending_event()
    if ev.get('id') and (ev.get('showID'), ev.get('turnID')) == (st.get('showID'), st.get('turnID')):
        return ev
    return None


def acknowledge(ev):
    save_skill(acked=ev.get('id'))


def event_view(ev, st=None):
    kind = ev.get('kind', 'answer')
    out = {'kind': kind}
    if kind != 'continue':
        out['answer'] = ev.get('text')
    for key in ('choice',):
        if key in ev:
            out[key] = ev[key]
    if st is not None:
        out['on_page'] = st.get('title')
    return out


def interrupted(ev, st, held='你这次的页面没有发出。'):
    acknowledge(ev)
    return dict({'ok': True, 'status': 'interrupted'}, **event_view(ev, st),
                hint='用户在白板上回了话（见 answer）。' + held + '先回应他说的内容；'
                     '下一次 say / ask 会自动接在这条回答后面，旧的待播页会被丢弃。')


def summary(st, **extra):
    pages = st['document']['pages']
    out = {'page': st['pageID'], 'index': st['pageIndex'] + 1, 'pages': len(pages),
           'queued': len(pages) - st['pageIndex'] - 1}
    out.update(extra)
    return out


# ---------- 页面 ----------

def parse_payload(raw):
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text[0] in '[{':
        try:
            return json.loads(text)
        except ValueError as exc:
            raise Fail('invalid', 'JSON 无法解析：%s' % exc, '检查引号和逗号；用 <<\'JSON\' 包住多行 JSON。')
    if text[0] == '"' and '\n' not in text:
        try:
            value = json.loads(text)
            if isinstance(value, str):
                return value
        except ValueError:
            pass
    return text


def normalize_pages(value):
    """接受：字符串 / 页对象 / 列表 / {"pages": [...]}。返回页对象列表（尚未分配 id）。"""
    if isinstance(value, dict) and 'pages' in value:
        value = value['pages']
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list) or not value:
        raise Fail('invalid', '没有要显示的页面', '传一句话，或 {"pages":[{"text":"…"}]}。')
    if len(value) > MAX_PAGES_PER_CALL:
        raise Fail('invalid', '一次最多 %d 页' % MAX_PAGES_PER_CALL, '每页一个要点；先发前几页，讲到时再追加。')
    pages = []
    for item in value:
        if isinstance(item, str):
            item = {'text': item}
        if not isinstance(item, dict):
            raise Fail('invalid', '页面应为字符串或对象')
        page = dict(item)
        if 'title' in page and 'text' not in page:
            page['text'] = page.pop('title')
        extra = set(page) - {'id', 'text', 'choices', 'drawing', 'canvas', 'sketch', 'board'}
        if extra:
            raise Fail('invalid', '页面不支持字段：' + '、'.join(sorted(extra)),
                       '页面字段：text、sketch（速写元素行）、board（场景 JSON）、choices、drawing、canvas、id（可省略）。')
        if 'board' in page:
            try:
                scene_mod.validate_scene(page['board'])
            except ValueError as exc:
                raise Fail('invalid', str(exc), '场景格式见 references/scene.md。')
        if not isinstance(page.get('text'), str) or not page['text'].strip():
            raise Fail('invalid', '每页都需要 text', 'text 是这一页要说的一句话；用整页 canvas 时它作为页标题。')
        page['text'] = page['text'].strip()
        for key in ('drawing', 'canvas'):
            if key in page:
                try:
                    page[key] = shapes.expand_canvas(page[key])
                except ValueError as exc:
                    raise Fail('invalid', str(exc), '宏参数见 references/canvas.md 的「图形宏」。')
        pages.append(page)
    return pages


def sketch_fail(exc):
    if isinstance(exc, sketch.SketchError):
        return Fail('invalid', str(exc), '速写语法见 SKILL.md「速写」；画复杂的页先用 check 试。')
    return explain(exc)


def prepare(value, plain=False):
    """输入 → 现场页列表 + 速写档案 {页 id: record}（供 edit 增量修改）。"""
    records = {}
    warnings = {}

    def keep(compiled, pid=None):
        pid = pid or 'p-' + uuid.uuid4().hex[:6]
        if compiled.get('warnings'):
            warnings[pid] = ['「%s」%s' % (compiled['text'][:10], w) for w in compiled['warnings']]
        page = {'id': pid, 'text': compiled['text']}
        if compiled['board'] is not None:
            page['board'] = compiled['board']
            records[pid] = {'text': compiled['raw'], 'head': compiled['head'], 'specs': sketch.clean_specs(compiled['specs'])}
        return page

    try:
        if isinstance(value, str) and sketch.is_sketch(value):
            pages = [keep(c) for c in sketch.compile_sketch(value)]
        else:
            pages = []
            for page in normalize_pages(value):
                if 'sketch' in page:
                    if not isinstance(page['sketch'], str):
                        raise Fail('invalid', 'sketch 应为多行字符串（每行一个元素）')
                    compiled = keep(sketch.compile_page(page['text'], page['sketch']), page.get('id'))
                    if 'choices' in page:
                        compiled['choices'] = page['choices']
                    pages.append(compiled)
                elif plain or any(k in page for k in ('choices', 'drawing', 'canvas', 'board')):
                    page['text'] = page['text'].replace('**', '').strip()
                    pages.append(page)
                else:
                    pages.append(keep(sketch.compile_page(page['text']), page.get('id')))
    except (sketch.SketchError, ValueError) as exc:
        if isinstance(exc, Fail):
            raise
        raise sketch_fail(exc)
    if not pages:
        raise Fail('invalid', '没有要显示的页面', '至少写一行 == 这一页要说的话。')
    if len(pages) > MAX_PAGES_PER_CALL:
        raise Fail('invalid', '一次最多 %d 页' % MAX_PAGES_PER_CALL, '先发前几页，讲到时再追加。')
    prepare.warnings = warnings
    return pages, records


prepare.warnings = {}

KIND_NAME = {'circle': '圆', 'box': '方框', 'line': '线', 'arrow': '箭头', 'arrow_start': '箭头', 'arrow_both': '箭头', 'curve': '曲线',
             'carrow': '曲线箭头', 'carrow_start': '曲线箭头', 'carrow_both': '曲线箭头', 'wave': '波', 'poly': '多边形',
             'blob': '色块', 'arc': '弧', 'icon': '图标', 'image': '图片', 'text': '文字'}


def label_for(eid, record):
    for spec in (record or {}).get('specs', []):
        if spec.get('id') == eid:
            where = '第 %d 行' % spec['ln'] if spec.get('ln') and not spec.get('auto') else ('自动显示的句子' if spec.get('auto') else '@' + eid)
            if spec['kind'] == 'text':
                return '%s「%s」' % (where, sketch.plain_text(spec['text']).replace('\n', ' ')[:10])
            return '%s的%s（@%s）' % (where, KIND_NAME.get(spec['kind'], '元素'), eid)
    return '@' + eid


def measured(page_id, record, timeout=1.8):
    """等渲染引擎报告这一页的真实排版。拿不到（旧播放器、窗口没开）时返回 None。"""
    if renderer().get('renderer') != 'engine':
        return None
    st = content()
    rev, show = st.get('documentRevision'), st.get('showID')
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        rep = board.read(DATA / 'layout-report.json')
        if rep.get('pageID') == page_id and rep.get('rev') == rev and rep.get('showID') == show:
            out = []
            for w in rep.get('warnings') or []:
                a, b = label_for(w.get('a'), record), label_for(w.get('b'), record) if w.get('b') else ''
                out.append({'overlap': '%s 和 %s 重叠' % (a, b), 'cross': '%s 穿过了 %s' % (a, b), 'out': '%s 超出了画面' % a,
                            'tiny': '%s 字太小，远处看不清' % a, 'contrast': '%s 和下面的 %s 颜色太接近' % (a, b)}.get(w.get('type'), str(w)))
            return out
        time.sleep(0.05)
    return None


def remember(records):
    if records:
        with deck.lock():
            ks = skill_state()
            book = ks.get('sketch', {})
            book.update(records)
            ks['sketch'] = dict(list(book.items())[-80:])
            board.write(SKILL_STATE, ks)


def assign_ids(pages, taken):
    used = set(taken)
    for page in pages:
        pid = page.get('id')
        if not isinstance(pid, str) or not pid.strip():
            pid = 'p-' + uuid.uuid4().hex[:6]
        base, n = pid, 2
        while pid in used:
            pid = '%s-%d' % (base, n)
            n += 1
        page['id'] = pid
        used.add(pid)
    return pages


def validated(pages):
    try:
        return live.make_pages(pages, deck, MAX_PAGES_PER_CALL)
    except ValueError as exc:
        raise explain(exc)


def to_live_page(page):
    """引擎页 → 现场页格式（用于把改过的当前页作为新页重发）。"""
    out = {'id': page['id'], 'text': page['title']}
    choices = (page.get('interaction') or {}).get('choices')
    if choices:
        out['choices'] = choices
    if page.get('board'):
        out['board'] = page['board']
    elif page.get('canvas'):
        out['canvas' if page.get('visualStyle') == 'live-full' else 'drawing'] = page['canvas']
    return out


# ---------- 打开窗口 ----------

def launch(show_id):
    if not (HERE.parent / 'engine' / 'board.js').exists():
        raise Fail('not-installed', '找不到渲染引擎 engine/', '把整个技能文件夹完整放好，再运行 board.py doctor。')
    try:
        board.open_app('--external', show_id)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Fail('launch-failed', '无法启动播放器：%s' % exc, '运行 board.py doctor；常见原因是隔离属性或签名。')


def wait_renderer(show_id, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        s = renderer()
        if s.get('showID') == show_id and s.get('visibility') == 'visible':
            return True
        time.sleep(0.05)
    return False


def open_board(pages, topic=None, replace=False):
    with deck.lock():
        ks = skill_state()
        if not replace and ks.get('dismissedAt') and time.time() - ks['dismissedAt'] < REOPEN_COOLDOWN:
            raise Fail('dismissed', '用户刚按 Esc 收起了白板', '用户再次要求时可用 say --new 开板。')
        previous = content()
        s = renderer()
        opening = (previous.get('action') == 'show' and previous.get('showID') != s.get('showID')
                   and time.time() - previous.get('writtenAt', 0) < 8)
        if opening:
            raise Fail('busy', '已有白板正在启动', '稍后重试。')
        visible = board.visible()
        if visible:
            if s.get('renderer') != 'engine':
                raise Fail('busy', '旧播放器仍在显示，请先按 Esc 退出。')
            if s.get('editing'):
                raise Fail('editing', '用户正在白板上输入', '先用 wait 等他把话发出来。')
            if not replace:
                raise Fail('busy', '白板正在显示别的内容（文稿或其他会话）', '确认要替换时加 --new。')
        doc = {'version': 1, 'title': (topic or '动态白板')[:80], 'pages': validated(pages)}
        state = {'showID': str(uuid.uuid4()), 'outputSource': 'live-tool', 'documentRevision': 1,
                 'liveGeneration': uuid.uuid4().hex, 'document': doc}
        try:
            deck.validate_document(doc)
        except ValueError as exc:
            raise explain(exc)
        deck.activate(state, 0, 'show')
        board.write(DATA / 'content.json', state)
        board.write(SKILL_STATE, dict(showID=state['showID'], acked=None, dismissedShow=None, dismissedAt=None))
        if not visible:
            try:
                launch(state['showID'])
            except Fail:
                state.update(action='close', writtenAt=time.time())
                board.write(DATA / 'content.json', state)
                raise
    seen = wait_renderer(state['showID'], 1.5 if visible else 5)
    st = state
    out = dict({'ok': True, 'status': 'shown' if seen else 'opening', 'opened': True}, **summary(st))
    if not seen:
        out['hint'] = '窗口还没有回应。若几秒后仍没出现，运行 board.py doctor。'
    return out


# ---------- 写入现场会话 ----------

def publish(args):
    try:
        return live.publish(args, deck, MAX_PAGES_PER_CALL)
    except ValueError as exc:
        raise explain(exc)


def push(pages, mode='auto', topic=None, replace=False):
    st = current_live()
    if st is None or replace:
        return open_board(assign_ids(pages, []), topic, replace=replace or st is not None)
    session, generation = st['showID'], st['liveGeneration']
    for attempt in range(2):
        st = current_live()
        if st is None or (st['showID'], st['liveGeneration']) != (session, generation):
            raise Fail('closed', '白板已关闭', '用户已收起白板；用文字继续，用户想看时用 say --new。')
        taken = [p['id'] for p in st['document']['pages']]
        batch = assign_ids(copy.deepcopy(pages), taken)
        args = {'session': session, 'generation': generation, 'pages': batch}
        ev = pending_for(st)
        replying = False
        effective = mode
        if ev:
            if ev.get('kind') == 'continue' or ev.get('id') == skill_state().get('acked'):
                args['eventID'] = ev['id']
                replying = True
            else:
                return interrupted(ev, st)
        else:
            behind = len(st['document']['pages']) - st['pageIndex'] - 1
            if mode == 'now' or (mode == 'auto' and behind == 0):
                args.update(show_now=True, fromPage=st['pageID'])
                effective = 'now'
            else:
                effective = 'queue'
        try:
            res = publish(args)
        except Fail as exc:
            if attempt == 0 and ('观众已翻页' in exc.payload['error'] or exc.payload['status'] == 'stale'):
                continue
            raise
        status = res.get('status')
        if status == 'interrupted':
            return interrupted(res['event'], st)
        queued_reason = None
        if status == 'editing':
            res = publish({'session': session, 'generation': generation, 'pages': batch})
            if res.get('status') == 'interrupted':
                return interrupted(res['event'], st)
            queued_reason = '用户正在白板上打字，新页已排在后面；他按空格就能看到。'
        now = content()
        out = dict({'ok': True, 'status': 'queued' if (queued_reason or effective == 'queue') and not replying else 'shown'},
                   **summary(now))
        for page, assigned in zip(pages, batch):
            page['id'] = assigned['id']
        if replying:
            out['replied_to'] = ev.get('kind')
        if queued_reason:
            out['hint'] = queued_reason
        elif out['status'] == 'queued':
            out['hint'] = '用户还没看完前面的页，新页排在后面（按空格看到）。要立刻跳到新页用 --now。'
        return out
    raise Fail('stale', '白板一直在变化，没能写入', '稍后重试。')


# ---------- 命令 ----------

def cmd_say(value, mode='auto', topic=None, replace=False, plain=False):
    if mode not in ('auto', 'now', 'queue'):
        raise Fail('invalid', 'mode 应为 auto、now 或 queue。')
    pages, records = prepare(value, plain)
    pages = validated_shape(pages)
    estimates = dict(prepare.warnings)
    original_ids = [page.get('id') for page in pages]
    out = push(pages, mode, topic, replace)
    records = {page['id']: records[pid] for pid, page in zip(original_ids, pages) if pid in records and 'id' in page}
    estimates = {page['id']: estimates[pid] for pid, page in zip(original_ids, pages) if pid in estimates and 'id' in page}
    if out.get('ok') and out.get('status') in ('shown', 'queued', 'opening'):
        remember(records)
        warnings = []
        shown = content().get('pageID')
        if out['status'] != 'queued' and shown in records:
            real = measured(shown, records[shown])
            if real is not None:
                estimates.pop(shown, None)
                warnings += real
                out['measured'] = True
                if out['status'] == 'opening':
                    out['status'] = 'shown'
                    out.pop('hint', None)
        for pid in [p['id'] for p in pages]:
            warnings += estimates.get(pid, [])
        if warnings:
            out['warnings'] = warnings[:10]
            out.setdefault('hint', '画面已显示，但有排版问题（见 warnings）。用 edit 挪位置或改字号，比如 @名字 40,60 或 @名字 m。')
    return out


def validated_shape(pages):
    # 先用临时 id 做一次完整校验，让错误在动窗口之前出现。
    validated(assign_ids(copy.deepcopy(pages), []))
    return pages


def listen(st, seconds):
    if type(seconds) not in (int, float) or not 0 <= seconds <= 120:
        raise Fail('invalid', '等待时间应为 0–120 秒')
    acked = skill_state().get('acked')
    ev = pending_for(st)
    if ev and ev.get('id') == acked:
        return dict({'ok': True, 'status': ev.get('kind', 'answer'), 'repeat': True}, **event_view(ev, st),
                    hint='这条回答之前已经交给过你。用 say 回应它，白板才会翻到新的一轮。')
    try:
        res = deck.run('live_input', {'session': st['showID'], 'seconds': seconds})
    except ValueError as exc:
        raise explain(exc)
    status = res.get('status')
    if status in ('answer', 'continue') and res.get('event'):
        ev = res['event']
        acknowledge(ev)
        out = dict({'ok': True, 'status': status}, **event_view(ev))
        out['on_page'] = res.get('question')
        if status == 'continue':
            out['hint'] = '用户按空格要你继续（没有作答）。接着讲下一个要点。'
        else:
            out['hint'] = '这是用户的原话。据此决定下一句，用 say 回应（会自动关联这条回答）。'
        return out
    if status == 'timeout':
        return {'ok': True, 'status': 'timeout', 'hint': '还没有回应。可以再 wait 一次，或者先用文字继续。'}
    note_dismissal()
    return {'ok': True, 'status': 'closed', 'hint': '用户已收起白板（Esc）。用文字继续，别再自动打开。'}


def cmd_ask(value, choices=None, seconds=45, topic=None, replace=False):
    if isinstance(value, dict) and 'pages' in value:
        raise Fail('invalid', 'ask 一次只问一页', '传 {"text":"问题？","choices":[…]}。')
    if isinstance(value, dict):
        value = dict(value)
        seconds = value.pop('seconds', seconds)
        topic = value.pop('topic', topic)
    pages = normalize_pages(value)
    if len(pages) != 1:
        raise Fail('invalid', 'ask 一次只问一页')
    pages[0]['text'] = pages[0]['text'].replace('**', '').strip()
    if choices:
        pages[0]['choices'] = choices
    if type(seconds) not in (int, float) or not 0 <= seconds <= 120:
        raise Fail('invalid', '等待时间应为 0–120 秒')
    shown = cmd_say(pages, 'auto', topic, replace, plain=True)
    if shown.get('status') == 'queued':
        shown['hint'] = '问题已排队。用 wait 接收输入，on_page 标明实际作答的页面。'
        return shown
    if shown.get('status') == 'interrupted' or not shown.get('ok'):
        return shown
    st = current_live()
    if st is None:
        return {'ok': True, 'status': 'closed', 'hint': '白板已关闭。'}
    heard = listen(st, seconds)
    if heard.get('status') in ('answer', 'continue') and heard.get('on_page') != pages[0]['text']:
        heard['status'] = 'interrupted'
        heard['hint'] = '输入来自 on_page 标出的页面，先回应这条输入。'
    else:
        heard['asked'] = pages[0]['text']
    return heard


def cmd_wait(seconds=45):
    st = current_live()
    if st is None:
        return {'ok': True, 'status': 'closed', 'hint': '白板没有打开或已被收起。'}
    return listen(st, seconds)


def json_edit(found, spec):
    if any(not isinstance(spec.get(k, []), list) for k in ('changes', 'remove')) or not all(isinstance(n, str) for n in spec.get('remove', [])):
        raise Fail('invalid', 'changes 和 remove 应为列表，remove 的每项应为图元 id。')
    if found.get('board'):
        raise Fail('invalid', '这一页是速写画的，edit 请用速写行', '例如：@名字 pink、x @名字、新的一行、== 新句子。')
    page = copy.deepcopy(found)
    canvas = copy.deepcopy(page.get('canvas') or {'nodes': []})
    nodes = canvas.get('nodes', [])
    changes = list(spec.get('changes') or [])
    if 'node' in spec:
        changes.append({'node': spec['node'], 'set': spec.get('set')})
    for change in changes:
        nid = change.get('node') if isinstance(change, dict) else None
        attrs = change.get('set') if isinstance(change, dict) else None
        if not isinstance(nid, str) or not isinstance(attrs, dict) or not attrs or set(attrs) & {'id', 'type'}:
            raise Fail('invalid', '每项修改需要 node 和非空 set（不能改 id / type）')
        targets = [n for n in nodes if n.get('id') == nid or str(n.get('id', '')).startswith(nid + '-')]
        if not targets:
            ids = [n.get('id') for n in nodes if n.get('id')]
            raise Fail('invalid', '当前页没有图元 %s' % nid, '现有图元 id：%s' % ('、'.join(ids) or '（无）'))
        for node in targets:
            node.update(attrs)
    remove = spec.get('remove') or []
    if remove:
        nodes = [n for n in nodes if not any(n.get('id') == r or str(n.get('id', '')).startswith(r + '-') for r in remove)]
    if spec.get('add'):
        add = spec['add'] if isinstance(spec['add'], list) else [spec['add']]
        try:
            fresh = shapes.expand_nodes(add)
        except ValueError as exc:
            raise Fail('invalid', str(exc))
        existing = {n.get('id') for n in nodes if n.get('id')}
        for node in fresh:
            if isinstance(node, dict) and node.get('id') in existing:
                raise Fail('invalid', '图元 id 已存在：%s' % node['id'], '换一个 id，或用 node+set 修改它。')
        nodes = nodes + fresh
    canvas['nodes'] = nodes
    if 'transition' in spec:
        canvas['transition'] = spec['transition']
    page['canvas'] = canvas if nodes else None
    if 'text' in spec:
        page['title'] = spec['text'].replace('**', '').strip()
    return page, None


def sketch_edit(found, src):
    record = skill_state().get('sketch', {}).get(found['id'])
    if record is None:
        raise Fail('invalid', '这一页不是用速写画的', '用 JSON 形式的 edit，或用 say 发一页新的。')
    try:
        new = sketch.edit_specs(record, src)
        canvas, specs = sketch.rebuild(new)
    except (sketch.SketchError, ValueError) as exc:
        raise sketch_fail(exc)
    new['specs'] = sketch.clean_specs(specs)
    sketch_edit.warnings = list(sketch.build.last_warnings)
    page = copy.deepcopy(found)
    page['title'] = sketch.plain_text(new['text']).replace('\n', ' ').strip()
    page['board'] = canvas
    return page, new


def cmd_edit(spec):
    if isinstance(spec, str):
        make, page_ref = (lambda found: sketch_edit(found, spec)), None
    elif isinstance(spec, dict):
        allowed = {'page', 'node', 'set', 'changes', 'add', 'remove', 'text', 'transition'}
        if set(spec) - allowed:
            raise Fail('invalid', 'edit 不支持字段：' + '、'.join(sorted(set(spec) - allowed)),
                       '速写写法：@id 参数 改、x @id 删、新的一行 加、== 新句子 换主句。')
        make, page_ref = (lambda found: json_edit(found, spec)), spec.get('page')
    else:
        raise Fail('invalid', 'edit 需要速写行或 JSON', '例如：@pull pink w4')
    for attempt in range(2):
        st = current_live()
        if st is None:
            raise Fail('closed', '白板已关闭', '用户已收起白板；用文字继续。')
        pages = st['document']['pages']
        page_id = page_ref or st['pageID']
        found = [p for p in pages if p['id'] == page_id]
        if not found:
            raise Fail('invalid', '找不到页 %s' % page_id, '省略 page 即修改当前页。')
        page, record = make(found[0])
        try:
            deck.validate_page(page)
        except ValueError as exc:
            raise explain(exc)
        nodes = (page.get('board') or {}).get('els') or (page.get('canvas') or {}).get('nodes', [])
        ev = pending_for(st)
        if ev:
            if ev.get('kind') != 'continue' and ev.get('id') != skill_state().get('acked'):
                return interrupted(ev, st, '这次修改没有执行。')
            # 用户已作答：回合已切换，把改好的画面作为新的一页接在回答后面。
            page['id'] = assign_ids([{'id': page_id + '-r'}], [p['id'] for p in pages])[0]['id']
            publish({'session': st['showID'], 'generation': st['liveGeneration'], 'eventID': ev['id'],
                     'pages': [to_live_page(page)]})
            if record:
                remember({page['id']: record})
            return dict({'ok': True, 'status': 'shown', 'replied_to': ev.get('kind'),
                         'note': '用户已作答，改好的画面作为新的一页接在回答后面。'}, **summary(content()))
        try:
            deck.run('edit', {'session': st['showID'], 'revision': st['documentRevision'],
                              'changes': [{'op': 'set', 'id': page_id, 'set': {k: page.get(k) for k in ('title', 'board', 'canvas') if k in page}}]})
        except ValueError as exc:
            if attempt == 0 and '文稿已更新' in str(exc):
                continue
            raise explain(exc)
        if record:
            remember({page_id: record})
        out = dict({'ok': True, 'status': 'edited', 'ids': [n.get('id') for n in nodes if n.get('id')]}, **summary(content()))
        if record:
            real = measured(page_id, record) if content().get('pageID') == page_id else None
            warnings = real if real is not None else getattr(sketch_edit, 'warnings', None)
            if warnings:
                out['warnings'] = warnings
        return out
    raise Fail('stale', '白板一直在变化，没能修改', '稍后重试。')


def cmd_close(force=False):
    st = current_live()
    if st is None:
        current = content()
        if (not current.get('showID') or current['showID'] != skill_state().get('documentShow')
                or not board.visible() or current.get('action') == 'close'):
            return {'ok': True, 'status': 'not-open'}
        st = current
    args = {'session': st['showID']}
    ev = pending_for(st)
    if ev:
        if ev.get('kind') == 'continue' or ev.get('id') == skill_state().get('acked') or force:
            args['eventID'] = ev['id']
        else:
            return interrupted(ev, st, '白板还没有收起。')
    if renderer().get('editing'):
        return {'ok': True, 'status': 'editing', 'hint': '用户正在白板上打字。先 wait 等他发出，再收起。'}
    try:
        deck.run('close', args)
    except ValueError as exc:
        raise explain(exc)
    return {'ok': True, 'status': 'closed'}


def cmd_status():
    note_dismissal()
    st, s = content(), renderer()
    live_st = current_live()
    out = {'ok': True, 'open': live_st is not None, 'visible': board.visible(), 'version': VERSION}
    if live_st is not None:
        out.update(summary(live_st))
        out.update(topic=live_st['document'].get('title'), text=live_st.get('title'), editing=bool(s.get('editing')))
        ev = pending_for(live_st)
        if ev:
            out['pending'] = event_view(ev)
            out['pending']['already_given'] = ev.get('id') == skill_state().get('acked')
            if not out['pending']['already_given']:
                out['hint'] = '用户在白板上留了话。用 wait 收取后再回应。'
    elif board.visible():
        if st.get('showID') == skill_state().get('documentShow') and st.get('action') != 'close':
            out.update(summary(st), open=True, text=st.get('title'), showing='document')
            return out
        out['showing'] = st.get('outputSource') or 'document'
        out['hint'] = '白板正在显示别的内容；要用它讲解请加 --new。'
    ks = skill_state()
    if ks.get('dismissedAt') and time.time() - ks['dismissedAt'] < REOPEN_COOLDOWN:
        out['recently_dismissed'] = True
    return out


def cmd_check(value, plain=False, full=False):
    pages, _ = prepare(value, plain)
    probe = assign_ids(copy.deepcopy(pages), [])
    result, engine = [], []
    for i in range(0, len(probe), 4):
        engine += validated(probe[i:i + 4])
    for page in engine:
        els = (page.get('board') or {}).get('els') or (page.get('canvas') or {}).get('nodes', [])
        result.append({'text': page['title'], 'elements': len(els), 'ids': [n.get('id') for n in els if n.get('id')],
                       'style': page['visualStyle'], 'nodes': len(els),
                       'chars': sum(len(n.get('text', '')) for n in els if n.get('type') == 'text')})
    out = {'ok': True, 'status': 'valid', 'pages': result}
    estimates = [w for ws in prepare.warnings.values() for w in ws]
    if estimates:
        out['warnings'] = estimates[:10]
        out['note'] = 'check 的排版提示是估算；真正显示后，say 会附上渲染引擎实测的结果。'
    if full:
        out['expanded'] = engine
    elif all('board' not in page for page in probe):
        out['expanded'] = probe
    return out


def cmd_present(path):
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Fail('invalid', '无法读取文稿：%s' % exc)
    if isinstance(doc, dict) and isinstance(doc.get('pages'), list):
        doc.setdefault('version', 1)
        for page in doc['pages']:
            if isinstance(page, dict):
                if 'text' in page and 'title' not in page:
                    page['title'] = page.pop('text')
                if 'canvas' in page:
                    page['canvas'] = shapes.expand_canvas(page['canvas'])
    try:
        was_visible = board.visible()
        if was_visible and renderer().get('renderer') != 'engine':
            raise Fail('busy', '旧播放器仍在显示，请先按 Esc 退出。')
        info = deck.run('present', {'document': doc})
    except ValueError as exc:
        raise explain(exc)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Fail('launch-failed', '无法启动播放器：%s' % exc, '运行 board.py doctor。')
    save_skill(documentShow=info['session'])
    seen = wait_renderer(info['session'], 1.5 if was_visible else 5)
    return dict({'ok': True, 'status': 'presenting' if seen else 'opening',
                 'hint': '这是完整文稿，用户用空格 / 方向键翻页。要现场讲解请用 say --new。'}, **info)


def cmd_demo(name='潮汐'):
    if name in ('声音怎样传播', '声音'):
        return cmd_present(HERE.parent / 'examples' / '声音怎样传播.白板.json')
    if name not in {f.stem for f in (HERE.parent / 'examples').glob('*.sketch')}:
        raise Fail('invalid', '请选择已安装的示例。')
    path = HERE.parent / 'examples' / ('%s.sketch' % name)
    if not path.exists():
        raise Fail('invalid', '没有示例 %s' % name, '可选：%s' % '、'.join(p.stem for p in (HERE.parent / 'examples').glob('*.sketch')))
    out = cmd_say(path.read_text(encoding='utf-8'), 'now', name, replace=True)
    out['hint'] = '示例已打开：按空格翻页，Esc 收起。示例源文件在 examples/%s.sketch，可以照着写。' % name
    return out


DESCRIBE = {
    'stage': '16:10；坐标 0–100（x 宽度 %、y 高度 %），字号 / 半径 / 图标大小按高度 %。底部 12% 留给输入框。',
    'page': '== 这一页要说的话 | push lift zoom cut bg:颜色 plain（整页没写文字时自动显示这句，**重点** 加粗上色）',
    'elements': {
        '文字 | 参数': '**重点** __高亮__ ~~删除~~ {pink:文字} \\n 换行；不写坐标就接在上一段下面',
        'o x,y 半径': '圆', 'b x,y 宽x高': '方框（round 圆角）', '- / -> / <-> 点 点…': '线、箭头',
        '~ / ~> 点 点…': '平滑曲线（首尾同点闭合）；~> a b 0.3 弧线', 'w x,y 宽x高 周期 [振幅]': '波',
        'p 点 点 点…': '多边形', 'blob x,y 大小 [种子]': '有机色块', 'arc x,y 半径 起角 止角': '弧（0° 正上、顺时针），+颜色 为扇形',
        'i 名字 x,y 大小': 'Lucide 图标', 'img 路径 x,y 宽x高': '本机图片', 'cam x,y 倍数': '镜头推近；cam reset 复位',
    },
    'flags': {
        '字号': 'xs s m l xl xxl huge 或数字', '字体': 'sans serif kai hand round mono', '字重': 'thin light regular medium bold heavy',
        '排版': 'c r w:40 lh:1.4 nowrap', '颜色': 'ink orange pink peach muted line white #RRGGBB；+颜色 填充；+orange>pink 渐变',
        '线': 'w3 dash dots dot flow', '质感': '40% -6deg glow shadow round top',
        '出场': 'rise fade pop slide draw wipe blur zoom spin drop bounce grow stretch left right up down type chars none',
        '持续': 'float pulse breathe sway bob orbit turn spinfast blink shake', '移动': 'to:x,y along:@名字 loop',
        '节奏': '& 同时；+2.5 第几秒；dur:1.2；ease:back；slow fast', '位置': 'below: above: left: right: on:@名字 gap:3',
        '其他': '@名字 命名（跨页同名就地变形）；count 数字滚动',
    },
    'edit': '@名字 参数（改） | x @名字（删） | 新的一行（加） | cam … | == 新句子（换主句）',
    'more': 'references/sketch.md；例子 examples/*.sketch',
}


def cmd_build():
    script = HERE / 'build.sh'
    if platform.system() != 'Darwin':
        raise Fail('unsupported', '只能在 Mac 上编译原生窗口', '其他系统会自动用浏览器窗口显示白板。')
    r = subprocess.run(['/bin/bash', str(script)], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail('build-failed', (r.stderr or r.stdout).strip()[-1500:] or '编译失败',
                   '把这段错误发给帮你改技能的人；在修好之前，白板会用浏览器窗口显示。')
    return {'ok': True, 'status': 'built', 'app': str(board.NATIVE), 'next': '运行 board.py demo 看效果。'}


def cmd_doctor():
    checks = []

    def add(name, ok, detail='', fix=None, level='error'):
        item = {'check': name, 'ok': bool(ok), 'detail': detail}
        if not ok:
            item['level'] = level
            if fix:
                item['fix'] = fix
        checks.append(item)

    darwin = platform.system() == 'Darwin'
    add('系统', True, platform.platform())
    add('Python', sys.version_info >= (3, 8), sys.version.split()[0], '需要 Python 3.8 或更高。')
    engine = HERE.parent / 'engine'
    for name in ('index.html', 'board.js', 'board.css', 'icons.json'):
        add('引擎 ' + name, (engine / name).exists(), str(engine), '把整个技能文件夹完整放好（engine/ 不能少）。')
    for name in ('board_server.py', 'sketch.py', 'scene.py', '演示文稿.py', '现场白板.py', 'whiteboard.py', 'shapes.py', 'canvas_schema.py'):
        add('脚本 ' + name, (HERE / name).exists(), '', '不要改名或删除 scripts/%s。' % name)
    exe = board.NATIVE / 'Contents' / 'MacOS' / 'DynamicWhiteboard'
    if darwin:
        add('原生窗口', exe.exists(), str(board.NATIVE) if exe.exists() else '还没编译；现在会用浏览器的无边框窗口代替',
            'python3 -B "%s" build' % (HERE / 'board.py'), level='warning')
        if not exe.exists():
            has_swiftc = subprocess.run(['/usr/bin/which', 'swiftc'], capture_output=True).returncode == 0
            add('编译工具 swiftc', has_swiftc, '编译原生窗口需要', 'xcode-select --install', level='warning')
        else:
            q = subprocess.run(['xattr', '-p', 'com.apple.quarantine', str(board.NATIVE)], capture_output=True)
            add('原生窗口未被隔离', q.returncode != 0, '', 'xattr -dr com.apple.quarantine "%s"' % board.NATIVE, level='warning')
        add('/usr/bin/python3', os.path.exists('/usr/bin/python3'), '原生窗口用它启动白板服务',
            'xcode-select --install', level='warning' if not exe.exists() else 'error')
        browsers = [b for b in ('Google Chrome', 'Microsoft Edge', 'Brave Browser', 'Chromium') if pathlib.Path('/Applications/%s.app' % b).exists()]
        add('备用浏览器', bool(browsers) or exe.exists(), '、'.join(browsers) or '没有 Chrome 类浏览器，备用模式会用默认浏览器（带地址栏）',
            '编译原生窗口，或安装 Chrome。', level='warning')
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        probe = DATA / ('.probe-%d' % os.getpid())
        probe.write_text('ok')
        probe.unlink()
        add('数据目录可写', True, str(DATA))
    except OSError as exc:
        add('数据目录可写', False, '%s：%s' % (DATA, exc), '检查该目录权限，或设置 DOT_WHITEBOARD_DATA。')
    s = renderer()
    alive = False
    if s.get('pid'):
        try:
            os.kill(s['pid'], 0)
            alive = True
        except (ProcessLookupError, PermissionError, TypeError):
            alive = False
    if alive and s.get('visibility') == 'visible' and s.get('renderer') != 'engine':
        add('播放器版本', False, '旧版「Dot 白板.app」正在显示', '先按 Esc 关掉旧白板，新白板才能接管。')
    else:
        add('播放器', True, ('运行中（%s）' % s.get('host', '')) if alive and s.get('visibility') == 'visible' else '未运行（say 时自动打开）')
    problems = [c for c in checks if not c['ok'] and c.get('level') == 'error']
    return {'ok': not problems, 'status': 'ready' if not problems else 'problems', 'checks': checks,
            'next': '运行 board.py demo 看一段示例。' if not problems else '按 fix 逐项修复后再运行 doctor。'}


# ---------- MCP（可选：给只支持 MCP 的宿主） ----------

def _schema(props, required=()):
    return {'type': 'object', 'properties': props, 'required': list(required)}


ANY = {}
MCP_TOOLS = {
    'whiteboard_say': ('把 1–8 页送到白板。首选 sketch：速写文本（== 开页，每行一个元素，语法见 whiteboard_describe）。也可用 pages：字符串或 {text, sketch?, choices?, drawing?|canvas?}。mode=auto（默认）用户看完前面的页才跳；now 立刻跳；queue 只排队。new=true 替换白板上其他内容。',
                       _schema({'sketch': {'type': 'string'}, 'pages': {'type': 'array', 'items': ANY},
                                'mode': {'type': 'string', 'enum': ['auto', 'now', 'queue']},
                                'topic': {'type': 'string'}, 'new': {'type': 'boolean'}, 'plain': {'type': 'boolean'}})),
    'whiteboard_ask': ('显示一个问题并等待用户在白板上回答（点选或打字）。返回 answer / continue / timeout / closed / interrupted。',
                       _schema({'text': {'type': 'string'}, 'choices': {'type': 'array', 'items': {'type': 'string'}},
                                'drawing': {'type': 'object'}, 'canvas': {'type': 'object'}, 'board': {'type':'object'}, 'sketch': {'type':'string'}, 'seconds': {'type': 'number'},
                                'topic': {'type': 'string'}, 'new': {'type': 'boolean'}}, ['text'])),
    'whiteboard_wait': ('继续等待用户在白板上的输入。', _schema({'seconds': {'type': 'number'}})),
    'whiteboard_edit': ('原位修改当前页。首选 sketch：@名字 参数 改、x @名字 删、新行 加、== 新句子 换主句。也接受 JSON：{node,set} / changes / add / remove / text。',
                        _schema({'sketch': {'type': 'string'}, 'page': {'type': 'string'}, 'node': {'type': 'string'}, 'set': {'type': 'object'},
                                 'changes': {'type': 'array', 'items': ANY}, 'add': {'type': 'array', 'items': ANY},
                                 'remove': {'type': 'array', 'items': {'type': 'string'}}, 'text': {'type': 'string'},
                                 'transition': {'type': 'string'}})),
    'whiteboard_close': ('讲完后收起白板。', _schema({'force': {'type': 'boolean'}})),
    'whiteboard_status': ('白板是否打开、当前页、是否有用户留言。', _schema({})),
    'whiteboard_check': ('不打开窗口，只校验页面。', _schema({'sketch': {'type': 'string'}, 'pages': {'type': 'array', 'items': ANY}})),
    'whiteboard_describe': ('读取页面与图元语法、图形宏。', _schema({})),
}
BLOCKING = {'whiteboard_ask', 'whiteboard_wait'}


def call(name, a):
    if not isinstance(a, dict):
        raise Fail('invalid', '工具参数应为 JSON 对象。')
    if name == 'whiteboard_say':
        return cmd_say(a.get('sketch') or a.get('pages'), a.get('mode', 'auto'), a.get('topic'), bool(a.get('new')), bool(a.get('plain')))
    if name == 'whiteboard_ask':
        page = {k: a[k] for k in ('text', 'choices', 'drawing', 'canvas', 'board', 'sketch') if k in a}
        return cmd_ask(page, None, a.get('seconds', 45), a.get('topic'), bool(a.get('new')))
    if name == 'whiteboard_wait':
        return cmd_wait(a.get('seconds', 45))
    if name == 'whiteboard_edit':
        return cmd_edit(a['sketch'] if 'sketch' in a else a)
    if name == 'whiteboard_close':
        return cmd_close(bool(a.get('force')))
    if name == 'whiteboard_status':
        return cmd_status()
    if name == 'whiteboard_check':
        return cmd_check(a.get('sketch') or a.get('pages'), bool(a.get('plain')))
    if name == 'whiteboard_describe':
        return {'ok': True, 'grammar': DESCRIBE}
    raise Fail('invalid', '未知工具 %s' % name)


def safe(fn, *args):
    try:
        return fn(*args)
    except Fail as exc:
        return exc.payload
    except (ValueError, TypeError, KeyError, OSError, OverflowError, subprocess.SubprocessError) as exc:
        return explain(exc).payload


def serve():
    out_lock = threading.Lock()
    slots = threading.BoundedSemaphore(4)

    def send(packet):
        with out_lock:
            sys.stdout.write(json.dumps(packet, ensure_ascii=False) + '\n')
            sys.stdout.flush()

    def answer(msg, name, a, release=False):
        try:
            value = safe(call, name, a)
        finally:
            if release:
                slots.release()
        send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {
            'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': not value.get('ok', True)}})

    for raw in sys.stdin.buffer:
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(msg, dict) or 'id' not in msg:
            continue
        method, params = msg.get('method'), msg.get('params') or {}
        if not isinstance(params, dict):
            send({'jsonrpc':'2.0', 'id':msg['id'], 'error':{'code':-32602, 'message':'参数应为对象'}})
            continue
        if method == 'initialize':
            version = params.get('protocolVersion')
            send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {
                'protocolVersion': version if version in ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25') else '2025-06-18',
                'capabilities': {'tools': {}}, 'serverInfo': {'name': 'dynamic-whiteboard', 'version': VERSION},
                'instructions': '本机白板是你的输出端。讲解时用 whiteboard_say 的 sketch 自己画：每页一句话、几行元素，'
                                '构图和动作由你决定，每页都不同。语法先看 whiteboard_describe。需要用户决定时用 whiteboard_ask。'
                                '讲完 whiteboard_close；用户按 Esc 后不要再自动打开。'}})
        elif method == 'ping':
            send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {}})
        elif method == 'tools/list':
            send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'tools': [
                {'name': k, 'description': v[0], 'inputSchema': v[1]} for k, v in MCP_TOOLS.items()]}})
        elif method == 'tools/call':
            name, a = params.get('name'), params.get('arguments', {})
            if not isinstance(name, str) or not isinstance(a, dict):
                send({'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32602, 'message': '需要工具名和参数对象'}})
                continue
            if name in BLOCKING:
                if not slots.acquire(blocking=False):
                    send({'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32000, 'message': '已有四个等待中的请求'}})
                    continue
                threading.Thread(target=answer, args=(msg, name, a, True), daemon=True).start()
            else:
                answer(msg, name, a)
        else:
            send({'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32601, 'message': '不支持的方法'}})


# ---------- 命令行 ----------

def read_stdin():
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.3)
    except (OSError, ValueError):
        ready = [sys.stdin]
    return sys.stdin.read() if ready else None


def gather(args, positional=True):
    if getattr(args, 'json', None):
        return parse_payload(args.json)
    if getattr(args, 'file', None):
        raw = sys.stdin.read() if str(args.file) == '-' else pathlib.Path(args.file).read_text(encoding='utf-8')
        return parse_payload(raw)
    items = getattr(args, 'items', None) if positional else None
    if items:
        if len(items) == 1:
            return parse_payload(items[0])
        return list(items)
    return parse_payload(read_stdin())


def main(argv=None):
    p = argparse.ArgumentParser(prog='board.py', description='动态白板 · 输出端（Esc 由用户掌握）')
    sub = p.add_subparsers(dest='cmd')

    def inputs(sp):
        sp.add_argument('items', nargs='*', help='一句或多句话；也可以是一段 JSON')
        sp.add_argument('--json', help='页面 JSON 字符串')
        sp.add_argument('--file', help='页面 JSON 文件（- 为标准输入）')

    sp = sub.add_parser('say', help='显示 1–8 页')
    inputs(sp)
    sp.add_argument('--now', action='store_true', help='立刻跳到新页（默认：用户看完前面的页才跳）')
    sp.add_argument('--queue', action='store_true', help='只排在后面，不跳页')
    sp.add_argument('--new', action='store_true', help='新开一块白板（替换正在显示的内容）')
    sp.add_argument('--topic', help='新白板左上角的标题')
    sp.add_argument('--plain', action='store_true', help='不自动构图，用播放器原生的对话页')
    sp = sub.add_parser('ask', help='显示一个问题并等回答')
    inputs(sp)
    sp.add_argument('--choice', action='append', help='选项，最多 3 个')
    sp.add_argument('--wait', type=float, default=45, help='等待秒数（0–120，默认 45）')
    sp.add_argument('--new', action='store_true')
    sp.add_argument('--topic')
    sp = sub.add_parser('wait', help='继续等用户输入')
    sp.add_argument('--wait', type=float, default=45)
    sp = sub.add_parser('edit', help='原位修改当前页的图')
    inputs(sp)
    sp = sub.add_parser('close', help='收起白板')
    sp.add_argument('--force', action='store_true', help='即使有未处理的回答也收起')
    sub.add_parser('status', help='白板现在的状态')
    sp = sub.add_parser('check', help='只校验，不打开窗口')
    inputs(sp)
    sp.add_argument('--full', action='store_true', help='同时输出展开后的图元')
    sub.add_parser('describe', help='页面与图元语法')
    sub.add_parser('doctor', help='检查安装与环境')
    sub.add_parser('build', help='编译原生窗口（Mac）')
    sp = sub.add_parser('demo', help='播放示例（潮汐 / 哑铃训练）')
    sp.add_argument('name', nargs='?', default='潮汐')
    sp = sub.add_parser('present', help='打开一份完整文稿 JSON')
    sp.add_argument('--file', required=True)
    sub.add_parser('mcp', help='以 MCP 标准输入输出服务运行')
    sub.add_parser('version')
    args = p.parse_args(argv)

    if args.cmd == 'mcp':
        serve()
        return 0
    try:
        if args.cmd == 'say':
            value = gather(args)
            result = cmd_say(value, 'queue' if args.queue else ('now' if args.now else 'auto'), args.topic, args.new, args.plain)
        elif args.cmd == 'ask':
            result = cmd_ask(gather(args), args.choice, args.wait, args.topic, args.new)
        elif args.cmd == 'wait':
            result = cmd_wait(args.wait)
        elif args.cmd == 'edit':
            result = cmd_edit(gather(args))
        elif args.cmd == 'close':
            result = cmd_close(args.force)
        elif args.cmd == 'status':
            result = cmd_status()
        elif args.cmd == 'check':
            result = cmd_check(gather(args), full=args.full)
        elif args.cmd == 'describe':
            result = {'ok': True, 'grammar': DESCRIBE}
        elif args.cmd == 'doctor':
            result = cmd_doctor()
        elif args.cmd == 'build':
            result = cmd_build()
        elif args.cmd == 'demo':
            result = cmd_demo(args.name)
        elif args.cmd == 'present':
            result = cmd_present(args.file)
        elif args.cmd == 'version':
            result = {'ok': True, 'version': VERSION, 'native': str(board.NATIVE), 'native_built': board.native_ready(), 'data': str(DATA)}
        else:
            p.print_help()
            return 0
    except Fail as exc:
        result = exc.payload
    except (ValueError, TypeError, KeyError, OSError, OverflowError, subprocess.SubprocessError) as exc:
        result = explain(exc).payload
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok', True) else 1


if __name__ == '__main__':
    sys.exit(main())
