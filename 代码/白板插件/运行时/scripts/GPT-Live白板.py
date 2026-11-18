"""Attach the native whiteboard to an API-owned GPT-Live session on this Mac."""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import uuid
from collections import OrderedDict

sys.dont_write_bytecode = True
import 演示文稿 as deck

LIVE_TOOLS = ('live_board', 'live_ask', 'live_input', 'describe', 'read_document', 'edit', 'close')
VISUAL_DIRECTION = ('你有一块随时可用的白板。由你判断何时视觉表达更清楚，并立即委派白板工具，'
                    '无需用户提到白板、指定图案或同意开板。当口述足够时保持屏幕原样。'
                    '自行设计图和揭示顺序，随讲话逐步绘制、变换、指示和换页，讲清后自行收起。'
                    '需要用户判断才停下提问；用户插话就跟随新问题，Esc 后尊重退出。')

def configuration():
    return {'instructions': VISUAL_DIRECTION, 'delegation': {'type': 'responses', 'responses': {
        'model': os.getenv('OPENAI_LIVE_DELEGATION_MODEL') or 'gpt-6-luna',
        'tools': [{'type': 'function', 'name': name, 'description': deck.specs[name][0],
                   'parameters': deck.specs[name][1], 'strict': False}
                  for name in LIVE_TOOLS],
        'parallel_tool_calls': False,
        'tool_choice': 'auto',
        'instructions': VISUAL_DIRECTION + '只调用已注册的白板工具。每页一个要点。用 live_ask 开板提问。answer 表示收到点选或输入，续页带 eventID。speaking 表示用户正在语音接话，听完再决定画什么，续页用 show_now 和 fromPage。需要图元与动画语法时调用 describe。live_board 开板作图，edit 原位补图，close 收起。'}}}


class Captions:
    def __init__(self):
        self.session = None
        self.text = ''
        self.rendered = ''
        self.ends_at = -1
        self.user_ends_at = -1
        self.new_line = True
        self.due = 0

    def receive(self, event):
        kind = event.get('type')
        if kind == 'session.input_transcript.delta':
            self.user_ends_at = max(self.user_ends_at, event.get('end_ms', -1))
            self.new_line = True
            return
        if kind != 'session.output_transcript.delta' or not isinstance(event.get('delta'), str):
            return
        end = event.get('end_ms', 0)
        if end < max(self.user_ends_at, self.ends_at):
            return
        if self.new_line or event.get('start_ms', 0) - self.ends_at > 900 or len(self.text) >= 60:
            self.text = ''
        self.text = (self.text + event['delta'])[-120:]
        self.ends_at = end
        self.new_line = bool(re.search(r'[。！？!?]\s*$', self.text))

    def paint(self, overlay=False):
        title = self.text.strip()
        if not title or self.rendered == title or time.monotonic() < self.due:
            return
        if self.session is None:
            if deck.board.visible():
                raise ValueError('已有白板正在使用，退出该白板后再连接')
            page = {'id': 'live-caption', 'title': title, 'visualStyle': 'live-side'}
            info = deck.run('present', {'document': {'title': 'GPT-Live · 实时字幕', 'pages': [page]}})
            self.session = info['session']
        else:
            with deck.lock():
                state = deck.board.read(deck.board.DATA / 'content.json')
                deck.check_session(state, {'session': self.session})
                if overlay:
                    event = deck.board.read(deck.board.DATA / 'pending-reply.json')
                    if event.get('turnID') == state['turnID'] or deck.board.read(deck.board.DATA / 'status.json').get('editing'):
                        return
                    state.update(body=title, action='caption', writtenAt=time.time())
                else:
                    state['document']['pages'][0]['title'] = title
                    state['documentRevision'] += 1
                    deck.activate(state, 0, 'caption', new_turn=False)
                deck.board.write(deck.board.DATA / 'content.json', state)
        self.rendered = title
        self.due = time.monotonic() + 0.075


class Sideband:
    def __init__(self, send, captions=False):
        self.send = send
        self.captions = Captions()
        self.captions_only = captions
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.events = OrderedDict()
        self.call_ids = set()
        self.groups = {}
        self.board_session = None
        self.ended = False
        self.stopping = threading.Event()
        self.dismissed = False
        self.last_voice_start = -1
        self.delegation_offset = -1

    def emit(self, kind, **fields):
        self.send({'type': kind, 'event_id': uuid.uuid4().hex, **fields})

    def receive(self, event):
        eid = event.get('event_id')
        if eid:
            if eid in self.events:
                return
            self.events[eid] = True
            if len(self.events) > 8192:
                self.events.popitem(last=False)
        kind = event.get('type')
        if kind == 'session.closed':
            self.ended = True
            return
        if kind == 'error':
            raise ValueError('GPT-Live 返回错误：' + str(event.get('error', {}).get('code', 'unknown')))
        self.captions.receive(event)
        if kind == 'session.delegation.created':
            self.delegation_offset = max(self.delegation_offset, event.get('offset_ms', -1))
        if kind == 'session.input_transcript.delta' and (event.get('delta') or '').strip():
            self.last_voice_start = max(self.last_voice_start, event.get('start_ms', -1))
        if self.captions_only:
            return
        if kind != 'response.event':
            return
        nested = event.get('event', {})
        key = event.get('delegation_id')
        typ = nested.get('type')
        if not key:
            return
        if typ == 'response.created':
            self.groups.setdefault(key, {'jobs': [], 'complete': False, 'other': False})
        elif typ == 'response.output_item.done':
            item = nested.get('item', {})
            if item.get('type') != 'function_call':
                return
            group = self.groups.setdefault(key, {'jobs': [], 'complete': False, 'other': False})
            if item.get('name') not in LIVE_TOOLS:
                group['other'] = True
                return
            cid = item.get('call_id')
            if not cid or cid in self.call_ids:
                return
            self.call_ids.add(cid)
            voice_floor = max(self.last_voice_start, self.captions.user_ends_at - 1,
                              self.captions.ends_at - 1, self.delegation_offset - 1)
            group['jobs'].append((cid, self.pool.submit(self.execute, item, voice_floor)))
        elif typ == 'response.completed' and key in self.groups:
            self.groups[key]['complete'] = True
        elif typ in ('response.failed', 'response.incomplete', 'response.cancelled'):
            group = self.groups.pop(key, {})
            for _, job in group.get('jobs', []):
                job.cancel()

    def execute(self, item, voice_floor):
        try:
            args = json.loads(item['arguments'])
            if not isinstance(args, dict):
                raise ValueError('参数应为对象')
            if self.dismissed:
                return {'status': 'dismissed', 'message': '用户已退出白板，请继续语音交谈'}
            if args.get('session') and args['session'] != self.board_session:
                raise ValueError('工具调用不属于本通话的白板')
            if self.board_session and item['name'] in ('live_board','live_ask') and not args.get('session'):
                raise ValueError('继续展示需要原 session')
            if item['name'] == 'live_ask':
                seconds = args.get('seconds', 45)
                if type(seconds) not in (int,float) or not 0 <= seconds <= 120:
                    raise ValueError('等待时间应为 0–120 秒')
                page = {k:args[k] for k in ('id','text','choices','drawing','canvas') if k in args}
                control = {k:args[k] for k in ('session','generation','fromPage','show_now','eventID') if k in args}
                if control.get('session') and not control.get('eventID'):
                    control['show_now'] = True
                shown = deck.run('live_board', {**control, 'pages':[page]})
                if shown['status'] != 'shown':
                    return shown
                self.board_session = shown['session']
                answer = self.execute({'name':'live_input','arguments':json.dumps({'session':self.board_session,'seconds':seconds})}, voice_floor)
                return {**shown, **answer}
            if self.stopping.is_set():
                return {'status': 'closed'}
            if item['name'] == 'live_input':
                seconds = args.get('seconds', 45)
                if type(seconds) not in (int, float) or not 0 <= seconds <= 120:
                    raise ValueError('等待时间应为 0–120 秒')
                end = time.monotonic() + seconds
                while not self.stopping.is_set():
                    result = deck.run('live_input', {**args, 'seconds': min(0.12, max(0, end - time.monotonic()))})
                    if result['status'] != 'timeout':
                        return result
                    if self.last_voice_start > voice_floor:
                        state = deck.board.read(deck.board.DATA / 'content.json')
                        deck.check_session(state, args)
                        return {**deck.state_summary(state), 'generation': state['liveGeneration'],
                                'status': 'speaking', 'message': '用户正在原通话中接话。听完后自行决定是否推进。'}
                    if time.monotonic() >= end:
                        return result
                return {'status': 'closed'}
            result = deck.run(item['name'], args)
            if item['name'] == 'close':
                self.board_session = None
                self.captions = Captions()
            elif result.get('session'):
                self.board_session = result['session']
            return result
        except (ValueError, TypeError, KeyError, OSError) as error:
            return {'error': str(error)}

    def tick(self):
        if self.captions_only:
            self.captions.paint()
            self.board_session = self.captions.session
        elif self.board_session:
            self.captions.session = self.board_session
            self.captions.paint(overlay=True)
        for key, group in list(self.groups.items()):
            if not group['complete'] or not all(job.done() for _, job in group['jobs']):
                continue
            for cid, job in group['jobs']:
                self.emit('response.item.create', item={'type': 'function_call_output', 'call_id': cid,
                          'output': json.dumps(job.result(), ensure_ascii=False)})
            if group['jobs'] and not group['other']:
                self.emit('response.create')
            del self.groups[key]

    def close(self):
        self.stopping.set()
        self.pool.shutdown(wait=False, cancel_futures=True)


def pump(ws, captions=False):
    import websocket
    bridge = Sideband(lambda event: ws.send(json.dumps(event)), captions)
    ws.settimeout(0.12)
    try:
        if not captions:
            bridge.emit('session.instructions.append', delegation_id=None, content=VISUAL_DIRECTION)
        while not bridge.ended:
            try:
                packet = ws.recv()
                if not packet:
                    break
                bridge.receive(json.loads(packet))
            except websocket.WebSocketTimeoutException:
                pass
            if bridge.ended:
                break
            if bridge.board_session:
                status = deck.board.read(deck.board.DATA / 'status.json')
                if status.get('showID') == bridge.board_session and status.get('visibility') == 'dismissed':
                    if captions:
                        break
                    bridge.dismissed = True
                    bridge.board_session = None
            bridge.tick()
    finally:
        bridge.close()
        ws.close()


def main():
    parser = argparse.ArgumentParser(description='连接已存在的 GPT-Live API 通话')
    parser.add_argument('--session', default=os.getenv('OPENAI_LIVE_SESSION_ID'))
    parser.add_argument('--captions', action='store_true', help='实时显示公开语音文本；语音交互保留在原通话')
    parser.add_argument('--tool-config', action='store_true', help='打印应合并到创建通话配置的 delegation 设置')
    args = parser.parse_args()
    if args.tool_config:
        print(json.dumps(configuration(), ensure_ascii=False, indent=2))
        return
    if not args.session or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}', args.session):
        parser.error('需要创建或接听这场通话时返回的 GPT-Live API session.id')
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        parser.error('需要创建该通话的 OpenAI 项目凭据 OPENAI_API_KEY')
    import websocket
    headers = {'Authorization': 'Bearer ' + key}
    for name, env in [('OpenAI-Project', 'OPENAI_PROJECT_ID'), ('OpenAI-Organization', 'OPENAI_ORG_ID')]:
        if os.getenv(env):
            headers[name] = os.environ[env]
    address = 'wss://api.openai.com/v1/live/sessions/' + args.session + '/attach'
    ws = websocket.create_connection(address, header=headers, timeout=10, redirect_limit=0)
    pump(ws, args.captions)


if __name__ == '__main__':
    main()
