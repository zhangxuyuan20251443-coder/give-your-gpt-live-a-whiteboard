#!/usr/bin/env python3
"""动态白板 · 输出端命令行。任何能运行命令的大模型都可以用它把内容送到本机原生白板。

    board.py say "一句话" ["下一句" …]       显示（用户看完前面的页才跳，其余按空格看）
    board.py say < pages.json                带图的页面（JSON 从标准输入读）
    board.py ask "问题？" --choice 甲 --choice 乙   显示问题并等回答
    board.py wait [--wait 45]                继续等用户在白板上的输入
    board.py edit '{"node":"arrow","set":{"color":"orange"}}'   原位改当前页的图
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
import 现场白板 as live

VERSION = '2.0.0'
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
    if text[0] in '[{"':
        try:
            return json.loads(text)
        except ValueError as exc:
            raise Fail('invalid', 'JSON 无法解析：%s' % exc, '检查引号和逗号；用 <<\'JSON\' 包住多行 JSON。')
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
        extra = set(page) - {'id', 'text', 'choices', 'drawing', 'canvas'}
        if extra:
            raise Fail('invalid', '页面不支持字段：' + '、'.join(sorted(extra)),
                       '页面字段只有 text、choices、drawing（文字旁配图）、canvas（整页画布）、id（可省略）。')
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
    if page.get('canvas'):
        out['canvas' if page.get('visualStyle') == 'live-full' else 'drawing'] = page['canvas']
    return out


# ---------- 打开窗口 ----------

def launch(show_id):
    if not (board.APP / 'Contents' / 'MacOS').exists():
        raise Fail('not-installed', '找不到播放器：%s' % board.APP, '运行 board.py doctor 检查安装。')
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
        if replying:
            out['replied_to'] = ev.get('kind')
        if queued_reason:
            out['hint'] = queued_reason
        elif out['status'] == 'queued':
            out['hint'] = '用户还没看完前面的页，新页排在后面（按空格看到）。要立刻跳到新页用 --now。'
        return out
    raise Fail('stale', '白板一直在变化，没能写入', '稍后重试。')


# ---------- 命令 ----------

def cmd_say(value, mode='auto', topic=None, replace=False):
    if mode not in ('auto', 'now', 'queue'):
        raise Fail('invalid', 'mode 应为 auto、now 或 queue。')
    pages = validated_shape(normalize_pages(value))
    return push(pages, mode, topic, replace)


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
    if choices:
        pages[0]['choices'] = choices
    if type(seconds) not in (int, float) or not 0 <= seconds <= 120:
        raise Fail('invalid', '等待时间应为 0–120 秒')
    shown = push(validated_shape(pages), 'auto', topic, replace)
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


def cmd_edit(spec):
    if not isinstance(spec, dict):
        raise Fail('invalid', 'edit 需要一个 JSON 对象', '例如 {"node":"arrow","set":{"color":"orange"}}。')
    allowed = {'page', 'node', 'set', 'changes', 'add', 'remove', 'text', 'transition'}
    if set(spec) - allowed:
        raise Fail('invalid', 'edit 不支持字段：' + '、'.join(sorted(set(spec) - allowed)),
                   'edit 字段：page、node+set、changes、add、remove、text、transition。')
    if any(not isinstance(spec.get(key, []), list) for key in ('changes', 'remove')) or not all(isinstance(k, str) for k in spec.get('remove', [])):
        raise Fail('invalid', 'changes 和 remove 应为列表，remove 的每项应为图元 id。')
    for attempt in range(2):
        st = current_live()
        if st is None:
            raise Fail('closed', '白板已关闭', '用户已收起白板；用文字继续。')
        pages = st['document']['pages']
        page_id = spec.get('page', st['pageID'])
        found = [p for p in pages if p['id'] == page_id]
        if not found:
            raise Fail('invalid', '找不到页 %s' % page_id, '省略 page 即修改当前页。')
        page = copy.deepcopy(found[0])
        canvas = copy.deepcopy(page.get('canvas') or {'nodes': []})
        nodes = canvas.get('nodes', [])
        changes = list(spec.get('changes') or [])
        if 'node' in spec:
            changes.append({'node': spec['node'], 'set': spec.get('set')})
        for change in changes:
            nid, attrs = change.get('node') if isinstance(change, dict) else None, change.get('set') if isinstance(change, dict) else None
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
            page['title'] = spec['text']
        try:
            deck.validate_page(page)
        except ValueError as exc:
            raise explain(exc)
        ev = pending_for(st)
        if ev:
            if ev.get('kind') != 'continue' and ev.get('id') != skill_state().get('acked'):
                return interrupted(ev, st, '这次修改没有执行。')
            # 用户已作答：回合已切换，把改好的图作为新的一页接在回答后面。
            page['id'] = assign_ids([{'id': page_id + '-r'}], [p['id'] for p in pages])[0]['id']
            res = publish({'session': st['showID'], 'generation': st['liveGeneration'], 'eventID': ev['id'],
                           'pages': [to_live_page(page)]})
            return dict({'ok': True, 'status': 'shown', 'replied_to': ev.get('kind'),
                         'note': '用户已作答，改好的图作为新的一页接在回答后面。'}, **summary(content()))
        try:
            deck.run('edit', {'session': st['showID'], 'revision': st['documentRevision'],
                              'changes': [{'op': 'set', 'id': page_id, 'set': {'title': page['title'], 'canvas': page['canvas']}}]})
        except ValueError as exc:
            if attempt == 0 and '文稿已更新' in str(exc):
                continue
            raise explain(exc)
        return dict({'ok': True, 'status': 'edited', 'nodes': [n.get('id') for n in nodes if n.get('id')]}, **summary(content()))
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


def cmd_check(value):
    pages = normalize_pages(value)
    probe = assign_ids(copy.deepcopy(pages), [])
    result = []
    for i in range(0, len(probe), 4):
        for page in validated(probe[i:i + 4]):
            nodes = (page.get('canvas') or {}).get('nodes', [])
            result.append({'text': page['title'], 'style': page['visualStyle'], 'nodes': len(nodes),
                           'chars': sum(len(n.get('text', '')) for n in nodes if n.get('type') == 'text')})
    return {'ok': True, 'status': 'valid', 'pages': result, 'expanded': probe}


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
        info = deck.run('present', {'document': doc})
    except ValueError as exc:
        raise explain(exc)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Fail('launch-failed', '无法启动播放器：%s' % exc, '运行 board.py doctor。')
    save_skill(documentShow=info['session'])
    seen = wait_renderer(info['session'], 1.5 if was_visible else 5)
    return dict({'ok': True, 'status': 'presenting' if seen else 'opening',
                 'hint': '这是完整文稿，用户用空格 / 方向键翻页。要现场讲解请用 say --new。'}, **info)


def cmd_demo():
    doc = json.loads((HERE.parent / 'examples' / '声音怎样传播.白板.json').read_text(encoding='utf-8'))
    pages = [{'id': p['id'], 'text': p['title'], 'canvas': p['canvas']} for p in doc['pages']]
    return push(pages, 'now', doc['title'], replace=True)


DESCRIBE = {
    'page': '{"text":"一句话","choices":["最多3个"],"drawing":{nodes…} 或 "canvas":{nodes…}}；text 必填，其余可省。drawing 在文字旁配图；canvas 用整页，页面要看见的字也放进画布。',
    'canvas': '{"nodes":[…1–12 个], "transition":"crossfade|cut|lift|push"}；坐标 0–1，左上为原点，y 向下；整页文字合计 ≤80 字。',
    'nodes': {
        'text': 'text(1–40字) x y w h size(0.03–0.6，字号上限，放不下 w 时自动缩小) weight(light|regular|semibold) align(left|center|right) effect(none|underline|outline)',
        'rect / circle': 'x y w h（外框） fill color stroke',
        'line / polyline / arrow': 'points:[[x,y],…] 2–32 个；arrow 箭头在最后一点',
        'bezier': 'points 数为 4、7、10…：起点 + 每段(控制点1, 控制点2, 终点)',
    },
    'paint': 'color / fill：ink orange rose muted none 或 #RRGGBB（品牌色 #F7513C 橙、#FF8066 浅橙、#FA70AB 粉）；stroke 1–10',
    'motion': 'motion: none fade rise slide pop draw；delay 0–1 秒；duration 0.1–2 秒。线条用 draw 会逐笔画出。',
    'marker': '线条可带 marker:{"radius":2–18,"duration":0.1–4,"color":…}，一个圆点沿路径移动',
    'timeline': '[{"property":"x|y|scale|rotation|opacity|draw","keys":[[0,值],[秒,值]…],"easing":"linear|ease|ease-in|ease-out"}]，2–24 帧，0 秒起，最长 8 秒；x/y 为相对位移（-1–1）',
    'macros': {
        'wave': '{"type":"wave","x","y","w","h","cycles":0.5–5,"amp":0–1,"decay":0.1–1,"flip":bool,+线条样式}',
        'curve': '{"type":"curve","from":[x,y],"to":[x,y],"bend":-1–1,"head":bool,+线条样式}',
        'flow': '{"type":"flow","items":[2–5 个],"x","y","w","h","direction":"row|column","size","color","arrow_color"}',
        'cycle': '{"type":"cycle","items":[3–5 个],"x","y","w","h","size","color","arrow_color","heads":bool}',
        'bars': '{"type":"bars","values":[1–6 个],"labels":[…],"x","y","w","h","max","color","colors"}',
    },
    'edit': '{"node":"id","set":{…}} | {"changes":[{"node","set"}…]} | {"add":[节点…]} | {"remove":["id"]} | {"text":"新主句"}；宏的 id 可整体修改/删除',
    'more': '完整说明与配方：references/canvas.md、references/recipes.md',
}


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
    add('macOS', darwin, platform.platform(), '原生播放器只能在 Mac 上运行。')
    if darwin:
        ver = platform.mac_ver()[0] or '0'
        try:
            major = int(ver.split('.')[0])
        except ValueError:
            major = 0
        add('macOS 版本', major >= 27, ver, '当前播放器构建声明需要 macOS 27 或更高。', level='warning')
        add('Apple 芯片', platform.machine() == 'arm64', platform.machine(), '播放器只编译了 arm64。')
    add('Python', sys.version_info >= (3, 8), sys.version.split()[0], '需要 Python 3.8 或更高。')
    add('/usr/bin/python3', os.path.exists('/usr/bin/python3'), '播放器保存/打开文稿时调用它',
        '安装命令行工具：xcode-select --install', level='warning')
    exe = board.APP / 'Contents' / 'MacOS' / 'DotWhiteboard'
    add('播放器文件', exe.exists(), str(board.APP), '把「Dot 白板.app」放在本技能根目录（与 scripts 同级）。')
    if exe.exists():
        add('播放器可执行', os.access(str(exe), os.X_OK), str(exe), 'chmod +x "%s"' % exe)
    for name in ('演示文稿.py', '当前聊天.py', '现场白板.py', 'canvas_schema.py', 'whiteboard.py', 'shapes.py'):
        add('脚本 ' + name, (HERE / name).exists(), '播放器和引擎按这个文件名加载', '不要改名或删除 scripts/%s。' % name)
    if darwin and exe.exists():
        q = subprocess.run(['xattr', '-p', 'com.apple.quarantine', str(board.APP)], capture_output=True)
        add('未被隔离', q.returncode != 0, '从网络/压缩包解出的 App 会带隔离属性，可能被拦截',
            'xattr -dr com.apple.quarantine "%s"' % board.APP)
        c = subprocess.run(['codesign', '--verify', '--deep', str(board.APP)], capture_output=True, text=True)
        add('签名有效', c.returncode == 0, (c.stderr or '').strip()[:200],
            'codesign --force --deep -s - "%s"' % board.APP)
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        probe = DATA / ('.probe-%d' % os.getpid())
        probe.write_text('ok')
        probe.unlink()
        add('数据目录可写', True, str(DATA))
    except OSError as exc:
        add('数据目录可写', False, '%s：%s' % (DATA, exc), '检查该目录权限，或设置 DOT_WHITEBOARD_DATA。')
    s = renderer()
    running = False
    if s.get('pid'):
        try:
            os.kill(s['pid'], 0)
            running = True
        except (ProcessLookupError, PermissionError, TypeError):
            running = False
    add('播放器进程', True, '运行中，%s' % s.get('visibility') if running else '未运行（say 时会自动启动）')
    problems = [c for c in checks if not c['ok'] and c.get('level') == 'error']
    return {'ok': not problems, 'status': 'ready' if not problems else 'problems', 'checks': checks,
            'next': '运行 board.py demo 看一段示例；看到窗口说明链路通了。' if not problems else '按 fix 逐项修复后再运行 doctor。'}


# ---------- MCP（可选：给只支持 MCP 的宿主） ----------

def _schema(props, required=()):
    return {'type': 'object', 'properties': props, 'required': list(required)}


ANY = {}
MCP_TOOLS = {
    'whiteboard_say': ('把 1–8 页送到白板。pages 元素可以是字符串或 {text, choices?, drawing?|canvas?}。mode=auto（默认）：用户已看完前面的页就立刻显示，否则排在后面；now 立刻跳页；queue 只排队。new=true 替换白板上其他内容。',
                       _schema({'pages': {'type': 'array', 'items': ANY}, 'mode': {'type': 'string', 'enum': ['auto', 'now', 'queue']},
                                'topic': {'type': 'string'}, 'new': {'type': 'boolean'}}, ['pages'])),
    'whiteboard_ask': ('显示一个问题并等待用户在白板上回答（点选或打字）。返回 answer / continue / timeout / closed / interrupted。',
                       _schema({'text': {'type': 'string'}, 'choices': {'type': 'array', 'items': {'type': 'string'}},
                                'drawing': {'type': 'object'}, 'canvas': {'type': 'object'}, 'seconds': {'type': 'number'},
                                'topic': {'type': 'string'}, 'new': {'type': 'boolean'}}, ['text'])),
    'whiteboard_wait': ('继续等待用户在白板上的输入。', _schema({'seconds': {'type': 'number'}})),
    'whiteboard_edit': ('原位修改当前页：{node,set} / changes / add / remove / text / transition。',
                        _schema({'page': {'type': 'string'}, 'node': {'type': 'string'}, 'set': {'type': 'object'},
                                 'changes': {'type': 'array', 'items': ANY}, 'add': {'type': 'array', 'items': ANY},
                                 'remove': {'type': 'array', 'items': {'type': 'string'}}, 'text': {'type': 'string'},
                                 'transition': {'type': 'string'}})),
    'whiteboard_close': ('讲完后收起白板。', _schema({'force': {'type': 'boolean'}})),
    'whiteboard_status': ('白板是否打开、当前页、是否有用户留言。', _schema({})),
    'whiteboard_check': ('不打开窗口，只校验页面并返回展开后的图元。', _schema({'pages': {'type': 'array', 'items': ANY}}, ['pages'])),
    'whiteboard_describe': ('读取页面与图元语法、图形宏。', _schema({})),
}
BLOCKING = {'whiteboard_ask', 'whiteboard_wait'}


def call(name, a):
    if not isinstance(a, dict):
        raise Fail('invalid', '工具参数应为 JSON 对象。')
    if name == 'whiteboard_say':
        return cmd_say(a.get('pages'), a.get('mode', 'auto'), a.get('topic'), bool(a.get('new')))
    if name == 'whiteboard_ask':
        page = {k: a[k] for k in ('text', 'choices', 'drawing', 'canvas') if k in a}
        return cmd_ask(page, None, a.get('seconds', 45), a.get('topic'), bool(a.get('new')))
    if name == 'whiteboard_wait':
        return cmd_wait(a.get('seconds', 45))
    if name == 'whiteboard_edit':
        return cmd_edit(a)
    if name == 'whiteboard_close':
        return cmd_close(bool(a.get('force')))
    if name == 'whiteboard_status':
        return cmd_status()
    if name == 'whiteboard_check':
        return cmd_check(a.get('pages'))
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
                'instructions': '本机白板是你的输出端。关系、机制、流程、变化或比较画出来更清楚时，自己调用 whiteboard_say；'
                                '每页一个要点，已在白板表达的内容无需在聊天里重复。需要用户决定时用 whiteboard_ask。讲完 whiteboard_close。'
                                '用户按 Esc 后不要再自动打开。'}})
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
    sub.add_parser('describe', help='页面与图元语法')
    sub.add_parser('doctor', help='检查安装与环境')
    sub.add_parser('demo', help='播放示例「声音怎样传播」')
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
            result = cmd_say(value, 'queue' if args.queue else ('now' if args.now else 'auto'), args.topic, args.new)
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
            result = cmd_check(gather(args))
        elif args.cmd == 'describe':
            result = {'ok': True, 'grammar': DESCRIBE}
        elif args.cmd == 'doctor':
            result = cmd_doctor()
        elif args.cmd == 'demo':
            result = cmd_demo()
        elif args.cmd == 'present':
            result = cmd_present(args.file)
        elif args.cmd == 'version':
            result = {'ok': True, 'version': VERSION, 'app': str(board.APP), 'data': str(DATA)}
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
