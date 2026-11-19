#!/usr/bin/env python3
"""白板宿主：在本机起一个只监听 127.0.0.1 的小服务，把渲染引擎（engine/）交给原生窗口或浏览器显示，
并按原有文件协议（content.json / status.json / pending-reply.json）与 board.py 对接。

    python3 board_server.py [--port 0] [--show SHOW_ID] [--host wk|browser]

启动后第一行输出 `PORT <端口>`。页面长时间没有轮询（窗口被关掉）时自动退出。
"""
import argparse
import hashlib
import json
import mimetypes
import os
import pathlib
import secrets
import signal
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import whiteboard as board  # noqa: E402
import 演示文稿 as deck  # noqa: E402
import scene as scenes  # noqa: E402

ENGINE = HERE.parent / 'engine'
DATA = board.DATA
STATIC = {'/': 'index.html', '/index.html': 'index.html', '/board.js': 'board.js', '/board.css': 'board.css', '/icons.json': 'icons.json'}


class Host:
    def __init__(self, show, kind):
        self.show = show
        self.token = secrets.token_urlsafe(32)
        self.kind = kind
        self.last_poll = time.monotonic()
        self.started = time.monotonic()
        self.polled = False
        self.lock = threading.Lock()
        self.cache = {}

    def status(self, **values):
        with self.lock:
            s = board.read(DATA / 'status.json')
            if values.get('visibility') != 'starting' and s.get('pid') != os.getpid():
                return
            s.update(pid=os.getpid(), source='dot', sceneStream=True, stableNodes=True, host=self.kind, renderer='engine',
                     rendererObservedAt=time.time())
            s.update(values)
            board.write(DATA / 'status.json', s)

    def version(self):
        try:
            st = os.stat(DATA / 'content.json')
            return '%d:%d' % (st.st_mtime_ns, st.st_size)
        except OSError:
            return '0'

    def snapshot(self):
        content = board.read(DATA / 'content.json')
        doc = content.get('document')
        if isinstance(doc, dict) and isinstance(doc.get('pages'), list):
            pages = []
            for page in doc['pages']:
                if not isinstance(page, dict):
                    continue
                if isinstance(page.get('board'), dict):
                    pages.append(page)
                    continue
                key = hashlib.sha1(json.dumps(page, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
                sc = self.cache.get(key)
                if sc is None:
                    sc = scenes.page_scene(page)
                    self.cache[key] = sc
                    if len(self.cache) > 400:
                        self.cache.clear()
                pages.append(dict(page, board=sc))
            content = dict(content, document=dict(doc, pages=pages))
        return content

    def shutdown_soon(self):
        def bye():
            time.sleep(0.4)
            os._exit(0)
        threading.Thread(target=bye, daemon=True).start()


HOST = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'DynamicWhiteboard/4'

    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, value):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_route(self):
        address = '127.0.0.1:%d' % self.server.server_port
        url = urllib.parse.urlsplit(self.path)
        prefix = '/' + HOST.token + '/'
        if self.headers.get('Host') != address or not url.path.startswith(prefix):
            self.send_error(404)
            return None
        return url._replace(path='/' + url.path[len(prefix):])

    def end_headers(self):
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        policy = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        self.send_header('Content-Security-Policy', policy)
        super().end_headers()

    def do_GET(self):
        url = self.local_route()
        if url is None:
            return
        if url.path == '/state':
            HOST.polled = True
            HOST.last_poll = time.monotonic()
            since = urllib.parse.parse_qs(url.query).get('since', [''])[0]
            end = time.monotonic() + 20
            while time.monotonic() < end:
                v = HOST.version()
                if v != since:
                    HOST.last_poll = time.monotonic()
                    return self.send_json(200, {'v': v, 'content': HOST.snapshot()})
                time.sleep(0.03)
                HOST.last_poll = time.monotonic()
            self.send_response(204)
            self.end_headers()
            return
        if url.path == '/file':
            src = urllib.parse.parse_qs(url.query).get('p', [''])[0]
            doc = board.read(DATA / 'content.json').get('document') or {}
            allowed = any(el.get('k') == 'image' and el.get('src') == src
                          for page in doc.get('pages', []) for el in (page.get('board') or {}).get('els', []))
            if not allowed:
                self.send_error(404)
                return
            try:
                target = pathlib.Path(src).expanduser().resolve()
                if target.suffix.lower() not in scenes.IMAGE_EXT or not target.is_file():
                    raise ValueError('unsupported image')
                data = target.read_bytes()
            except (OSError, RuntimeError, ValueError):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Security-Policy', "sandbox; default-src 'none'; style-src 'unsafe-inline'")
            self.send_header('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        name = STATIC.get(url.path)
        if not name:
            self.send_response(404)
            self.end_headers()
            return
        data = (ENGINE / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(name)[0] or 'text/plain')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        url = self.local_route()
        if url is None:
            return
        if url.path != '/event':
            self.send_response(404)
            self.end_headers()
            return
        if self.headers.get_content_type() != 'application/json' or self.headers.get('Origin') not in (None, 'http://' + self.headers['Host']):
            return self.send_json(403, {'ok': False})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 1_000_000:
                return self.send_json(400, {'ok': False})
            evt = json.loads(self.rfile.read(min(n, 1_000_000)) or b'{}')
        except (ValueError, OSError):
            return self.send_json(400, {'ok': False})
        if not isinstance(evt, dict):
            return self.send_json(400, {'ok': False})
        handle(evt)
        self.send_json(200, {'ok': True})


def handle(evt):
    kind = evt.get('type')
    st = board.read(DATA / 'content.json')
    status = board.read(DATA / 'status.json')
    if status.get('pid') != os.getpid() or status.get('visibility') in ('closed', 'dismissed'):
        return
    if kind != 'ready' and evt.get('showID') != st.get('showID'):
        return
    if kind == 'ready':
        st = board.read(DATA / 'content.json')
        HOST.status(visibility='visible', showID=st.get('showID') or HOST.show, editing=False)
    elif kind == 'shown':
        HOST.status(visibility='visible', showID=evt.get('showID'))
    elif kind == 'editing':
        HOST.status(editing=bool(evt.get('on')))
    elif kind == 'nav':
        with deck.lock():
            st = board.read(DATA / 'content.json')
            pages = (st.get('document') or {}).get('pages') or []
            i = evt.get('index')
            if st.get('showID') == evt.get('showID') and st.get('action') != 'close' and isinstance(i, int) and 0 <= i < len(pages):
                if st.get('pageIndex') != i:
                    deck.activate(st, i, 'navigate', new_turn=False)
                    board.write(DATA / 'content.json', st)
    elif kind in ('answer', 'continue'):
        with deck.lock():
            st = board.read(DATA / 'content.json')
            if (st.get('showID') == evt.get('showID') and st.get('action') != 'close'
                    and st.get('turnID') == evt.get('turnID') and st.get('pageID') == evt.get('pageID')):
                old = board.read(DATA / 'pending-reply.json')
                if (old.get('showID'), old.get('turnID')) == (st['showID'], st['turnID']):
                    return
                ev = {'id': uuid.uuid4().hex, 'showID': st['showID'], 'turnID': st.get('turnID'), 'kind': kind,
                      'pageID': evt.get('pageID') or st.get('pageID'), 'at': time.time()}
                if kind == 'answer':
                    ev['text'] = str(evt.get('text', ''))[:4000]
                    ev['choice'] = bool(evt.get('choice'))
                board.write(DATA / 'pending-reply.json', ev)
        HOST.status(editing=False)
    elif kind == 'layout':
        board.write(DATA / 'layout-report.json', dict(evt, at=time.time()))
    elif kind == 'dismiss':
        HOST.status(visibility='dismissed', showID=evt.get('showID') or board.read(DATA / 'content.json').get('showID'), editing=False)
        HOST.shutdown_soon()
    elif kind == 'closed':
        HOST.status(visibility='closed', editing=False)
        HOST.shutdown_soon()


def stop_renderer(*_):
    status = board.read(DATA / 'status.json')
    if status.get('pid') == os.getpid() and status.get('visibility') in ('starting', 'visible'):
        closing = board.read(DATA / 'content.json').get('action') == 'close'
        HOST.status(visibility='closed' if closing or not HOST.polled else 'dismissed', editing=False)
    os._exit(0)


def watchdog():
    while True:
        time.sleep(1)
        idle = time.monotonic() - HOST.last_poll
        if (HOST.polled and idle > 8) or (not HOST.polled and time.monotonic() - HOST.started > 40):
            stop_renderer()


def main():
    global HOST
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--show', default='')
    p.add_argument('--host', default='browser')
    args = p.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    HOST = Host(args.show, args.host)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    signal.signal(signal.SIGTERM, stop_renderer)
    HOST.status(visibility='starting', showID=args.show or board.read(DATA / 'content.json').get('showID'), editing=False)
    print('PORT %d %s' % (server.server_port, HOST.token), flush=True)
    try:
        log = open(DATA / 'server.log', 'a')
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    except OSError:
        pass
    threading.Thread(target=watchdog, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
