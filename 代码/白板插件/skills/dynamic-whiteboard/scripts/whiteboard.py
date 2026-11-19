#!/usr/bin/env python3
"""Whiteboard file protocol and local WebKit or browser launcher."""
import argparse, json, os, pathlib, subprocess, sys, time, uuid, select
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from canvas_schema import validate_canvas
ROOT = pathlib.Path(__file__).resolve().parents[1]
bundled_transport = ROOT / 'scripts' / '连接依赖.zip'
if bundled_transport.is_file():
    sys.path.insert(0,str(bundled_transport))
DATA = pathlib.Path(os.environ.get('DOT_WHITEBOARD_DATA',str(pathlib.Path.home() / 'Library/Application Support/DotWhiteboard')))
NATIVE = ROOT / '动态白板.app'          # 新播放器（scripts/build.sh 编译）
LEGACY = ROOT / 'Dot 白板.app'          # 旧播放器：只认旧格式，留作备用
APP = NATIVE

def read(path):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return {}

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(temp, path)

def visible():
    status=read(DATA/'status.json');pid=status.get('pid',0)
    if status.get('visibility')=='visible' and isinstance(pid,int) and pid>0:
        try:os.kill(pid,0)
        except ProcessLookupError:return False
        return True
    return False

def native_ready():
    return sys.platform=='darwin' and (NATIVE/'Contents'/'MacOS'/'DynamicWhiteboard').exists() and os.environ.get('DOT_WHITEBOARD_HOST')!='browser'

def open_app(*flags):
    """打开新播放器：编译过原生窗口就用它，否则用本机浏览器的无边框窗口。"""
    show=flags[flags.index('--external')+1] if '--external' in flags else ''
    if native_ready():
        args=['open','-n','-a',str(NATIVE)]
        if 'DOT_WHITEBOARD_DATA' in os.environ:args+=['--env','DOT_WHITEBOARD_DATA='+str(DATA)]
        args += ['--args','--show',show]
        if 'DOT_WHITEBOARD_DATA' in os.environ and os.environ.get('DOT_WHITEBOARD_TEST_WINDOW') == '1':
            args.append('--test-window')
        subprocess.run(args,check=True);return
    server=ROOT/'scripts'/'board_server.py'
    proc=subprocess.Popen([sys.executable,'-B',str(server),'--show',show,'--host','browser'],stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=os.environ.copy())
    ready,_,_=select.select([proc.stdout],[],[],8)
    line=proc.stdout.readline().decode() if ready else ''
    if not line.startswith('PORT '):
        proc.kill();raise OSError('白板服务没有启动')
    _, port, key = line.split()
    url='http://127.0.0.1:%s/%s/' % (port, key)
    write(DATA/'host-url.json',{'url':url,'pid':proc.pid,'at':time.time()})
    open_browser(url)

def open_browser(url):
    if os.environ.get('DOT_WHITEBOARD_NO_BROWSER')=='1':return
    if sys.platform=='darwin':
        for app in ('Google Chrome','Microsoft Edge','Brave Browser','Chromium','Arc'):
            if pathlib.Path('/Applications/%s.app'%app).exists() and app!='Arc':
                subprocess.run(['open','-na',app,'--args','--app='+url,'--start-fullscreen','--new-window'],check=False);return
        subprocess.run(['open',url],check=False);return
    import webbrowser;webbrowser.open(url)

def receive_event(wait, expected=None):
    deadline=time.monotonic()+wait
    queue=None;fd=None
    try:
        if wait>0 and hasattr(select,'kqueue') and DATA.exists():
            fd=os.open(DATA,os.O_RDONLY);queue=select.kqueue()
            queue.control([select.kevent(fd,filter=select.KQ_FILTER_VNODE,flags=select.KQ_EV_ADD|select.KQ_EV_CLEAR,fflags=select.KQ_NOTE_WRITE)],0,0)
        while True:
            current=read(DATA/'content.json');event=read(DATA/'pending-reply.json')
            status=read(DATA/'status.json')
            key=(current.get('showID'),current.get('turnID'))
            if expected is None:expected=key
            if key!=expected or current.get('action')=='close':return None
            if status.get('showID')==key[0] and status.get('visibility')=='dismissed':return None
            if status.get('source','dot')!='dot' and current.get('writtenAt',0)<=status.get('rendererObservedAt',0):return None
            if event and event.get('showID')==current.get('showID') and event.get('turnID')==current.get('turnID'):
                return event
            left=deadline-time.monotonic()
            if left<=0:return None
            if queue:queue.control(None,1,left)
            else:time.sleep(min(0.2,left))
    finally:
        if queue:queue.close()
        if fd is not None:os.close(fd)

def patch_scene(request):
    """Same-turn scene frame. One writer; never opens, changes turn, or submits input."""
    if not isinstance(request,dict) or set(request)-{'showID','turnID','sequence','canvas','updates'}:
        raise ValueError('frame 仅支持 showID/turnID/sequence/canvas')
    if not isinstance(request.get('sequence'),int) or isinstance(request.get('sequence'),bool) or request['sequence']<1:
        raise ValueError('sequence 必须为正整数')
    current=read(DATA/'content.json');status=read(DATA/'status.json');event=read(DATA/'pending-reply.json')
    if not current.get('showID') or any(request.get(k)!=current.get(k) for k in ('showID','turnID')):
        raise ValueError('stale: 回合已改变')
    if status and not status.get('sceneStream') and status.get('visibility')!='dismissed':
        raise ValueError('renderer-upgrade-required: 请等白板下次正常启动新版，避免旧版清空草稿')
    if current.get('action')=='close' or (status.get('showID')==current['showID'] and status.get('visibility')=='dismissed'):
        raise ValueError('closed: 用户已退出')
    if event.get('showID')==current['showID'] and event.get('turnID')==current.get('turnID'):
        raise ValueError('answered: 先处理真实回复，不再刷新旧页')
    if status.get('source','dot')!='dot':raise ValueError('当前为独立锻炼会话')
    if request['sequence']<=current.get('sceneSequence',0):raise ValueError('stale: sequence 需递增')
    if ('canvas' in request)==('updates' in request):raise ValueError('canvas 或 updates 二选一')
    if 'updates' in request:
        if status and not status.get('stableNodes'):raise ValueError('renderer-upgrade-required: 稳定节点需新版')
        updates=request['updates'];canvas=json.loads(json.dumps(current.get('canvas')))
        if not isinstance(canvas,dict) or not isinstance(updates,list) or not 1<=len(updates)<=12:raise ValueError('updates 需 1–12 项且当前存在 canvas')
        nodes={n.get('id'):n for n in canvas['nodes'] if n.get('id')};seen=set()
        for update in updates:
            if not isinstance(update,dict) or set(update)-{'id','set'} or not isinstance(update.get('id'),str) or update['id'] not in nodes or update['id'] in seen:raise ValueError('未知或重复节点 id')
            attrs=update.get('set')
            if not isinstance(attrs,dict) or not attrs or set(attrs)&{'id','type'}:raise ValueError('set 不能修改身份或类型')
            nodes[update['id']].update(attrs);seen.add(update['id'])
    else:canvas=request['canvas']
    validate_canvas(canvas)
    if canvas is None:raise ValueError('需要 canvas')

    current.update(canvas=canvas,sceneSequence=request['sequence'],action='patch',writtenAt=time.time())
    write(DATA/'content.json',current)
    return {'ok':True,'sequence':request['sequence'],'writtenAt':current['writtenAt']}

def stream_frames():
    # Bounded complete JSONL frames, not partial JSON/token fragments. No subprocess.
    for line in sys.stdin:
        try:
            if len(line.encode('utf-8'))>65536:raise ValueError('frame 最大 64 KiB')
            print(json.dumps(patch_scene(json.loads(line)),ensure_ascii=False),flush=True)
        except (ValueError,TypeError) as error:
            print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False),flush=True)
            return

def main():
    p = argparse.ArgumentParser(description='Dot 本地全屏橙色白板；Esc 退出。')
    p.add_argument('command', choices=['show','update','close','status','receive','reply','talk','stream','exercise'])
    p.add_argument('--file', type=pathlib.Path, help='UTF-8 JSON 内容文件')
    p.add_argument('--demo',action='store_true',help='exercise 使用离线演示')
    p.add_argument('--open',action='store_true',help='talk 显式打开新白板；否则绝不重开')
    p.add_argument('--layout',choices=['editorial','focus','countdown'])
    p.add_argument('--motion',choices=['slide','rise','pop','sweep','breathe','quiet'])
    p.add_argument('--decoration',choices=['none','rings','strides'])
    p.add_argument('--accent',choices=['orange','ink','rose'])
    p.add_argument('--style',choices=['magazine','ink','soft','brush'],help='本机中文艺术字风格')
    p.add_argument('--choice',action='append',help='talk 的简短回答选项，最多三个')
    p.add_argument('--reply-to', help='reply 必须关联 receive 返回的事件 id')
    p.add_argument('--wait',type=float,default=0,help='receive 等待秒数，最多 120')
    p.add_argument('--title'); p.add_argument('--body'); p.add_argument('--subtitle')
    p.add_argument('--item', action='append', dest='items')
    p.add_argument('--minutes', type=float, help='从现在开始的分钟倒计时')
    args = p.parse_args()
    if args.command=='exercise':
        status=read(DATA/'status.json')
        if visible():
            print(json.dumps({'state':'already-visible','source':status.get('source','dot')}));return
        open_app('--exercise',*(['--demo'] if args.demo else []))
        print(json.dumps({'state':'launch-requested'}));return
    if args.command=='stream':stream_frames();return
    talking=args.command=='talk'
    if talking:
        current=read(DATA/'content.json'); pending=read(DATA/'pending-reply.json')
        if args.open: args.command='show'
        elif args.reply_to: args.command='reply'
        elif pending and pending.get('turnID')==current.get('turnID') and pending.get('showID')==current.get('showID'):
            args.command='reply'; args.reply_to=pending['id']
        else: p.error('没有待回复回合；使用 receive 等待用户作答')
        if not 0<=args.wait<=120: p.error('--wait 必须在 0 至 120 秒')
    if args.command == 'receive':
        if not 0<=args.wait<=120: p.error('--wait 必须在 0 至 120 秒')
        print(json.dumps(receive_event(args.wait),ensure_ascii=False)); return
    if args.command == 'status':
        status=read(DATA/'status.json')
        try: os.kill(status.get('pid', -999999), 0); alive=True
        except ProcessLookupError: alive=False
        except PermissionError: alive=None
        if not status: alive=False
        print(json.dumps({'running':alive, **status}, ensure_ascii=False)); return
    board = read(DATA/'content.json') if args.command in ('update','close','reply') else {}
    if args.command=='reply':
        status=read(DATA/'status.json')
        if board.get('action')=='close' or (status and (status.get('source','dot')!='dot' or
                (status.get('showID')==board.get('showID') and status.get('visibility')=='dismissed'))):
            p.error('closed: 会话已结束')
        event=read(DATA/'pending-reply.json')
        if not args.reply_to or event.get('id')!=args.reply_to or event.get('turnID')!=board.get('turnID') or event.get('showID')!=board.get('showID'):
            p.error('回复事件已过期、不匹配或不存在；请先 receive')
    defaults={'title':'给想法一点空间','subtitle':'petaleg · 本地白板','body':'','items':[], 'endsAt':None, 'startsAt':None, 'showID':''}
    board={**defaults, **board}
    if args.file:
        if str(args.file)=='-':
            raw=sys.stdin.buffer.read(65537)
            if len(raw)>65536:p.error('单页最多 64 KiB')
            try:incoming=json.loads(raw)
            except ValueError:p.error('无效 JSON')
        else: incoming=read(args.file)
        if not incoming: p.error('内容文件不存在、为空或不是有效 JSON')
        allowed={'title','subtitle','body','items','endsAt','startsAt','components','interaction','visualStyle','scene','canvas'}
        if set(incoming)-allowed: p.error('不支持的内容字段：'+','.join(set(incoming)-allowed))
        board.update(incoming)
        if ('title' in incoming or 'body' in incoming) and 'components' not in incoming:
            board.pop('components', None)
        if ('title' in incoming or 'body' in incoming) and 'canvas' not in incoming:
            board.pop('canvas', None)
    if args.title is not None or args.body is not None:
        board.pop('components', None)
        if not args.file or 'canvas' not in incoming: board.pop('canvas', None)
    for key in ('title','body','subtitle','items'):
        value=getattr(args,key)
        if value is not None: board[key]=value
    for key in ('title','body','subtitle'):
        if not isinstance(board[key],str) or len(board[key])>50000: p.error(key+' 必须是 50000 字以内文本')
    if not isinstance(board['items'],list) or not all(isinstance(v,str) for v in board['items']) or len(board['items'])>200: p.error('items 必须是至多 200 项的字符串列表')
    if 'components' in board and board['components'] is not None:
        components=board['components']
        if not isinstance(components,list) or not 1<=len(components)<=6: p.error('components 必须为 1 至 6 个组件')
        types={'headline','eyebrow','caption','symbol','progress','timer'}
        seen=set()
        for c in components:
            if not isinstance(c,dict) or set(c)-{'type','text','value'} or c.get('type') not in types: p.error('组件仅支持 type/text/value 和安全组件类型')
            if c['type'] in seen: p.error('每种组件最多一个')
            seen.add(c['type'])
            if 'text' in c and (not isinstance(c['text'],str) or len(c['text'])>120): p.error('组件文本最多 120 字')
            if c['type']=='symbol' and c.get('text') not in {'sparkles','figure.mind.and.body','figure.walk','figure.run','checkmark','sun.max','moon','heart'}: p.error('图形必须使用技能中的安全符号名称')
            if 'value' in c and (not isinstance(c['value'],(int,float)) or not 0<=c['value']<=1): p.error('value 必须在 0 至 1 之间')
    try:validate_canvas(board.get('canvas'))
    except ValueError as error:p.error(str(error))
    scene=board.get('scene') or {}
    if not isinstance(scene,dict) or set(scene)-{'layout','motion','accent','decoration'}: p.error('scene 仅支持 layout/motion/accent/decoration')
    for key,allowed in [('layout',{'editorial','focus','countdown'}),('motion',{'slide','rise','pop','sweep','breathe','quiet'}),('accent',{'orange','ink','rose'}),('decoration',{'none','rings','strides'})]:
        value=getattr(args,key)
        if value is not None: scene[key]=value
        if key in scene and scene[key] not in allowed: p.error('非法 scene '+key)
    board['scene']=scene
    if args.style is not None: board['visualStyle']=args.style
    if board.get('visualStyle') not in (None,'magazine','ink','soft','brush'): p.error('visualStyle 必须是 magazine（旧风格值仅兼容）')
    if talking and (args.choice is not None or not args.file or 'interaction' not in incoming):
        board['interaction']={'choices':args.choice or []}
    if board.get('interaction') is not None:
        interaction=board['interaction']
        if not isinstance(interaction,dict) or set(interaction)-{'placeholder','choices'}: p.error('interaction 仅支持 placeholder 和 choices')
        if 'placeholder' in interaction and (not isinstance(interaction['placeholder'],str) or len(interaction['placeholder'])>60): p.error('placeholder 最多 60 字')
        choices=interaction.get('choices',[])
        if not isinstance(choices,list) or len(choices)>3 or not all(isinstance(c,str) and 0<len(c)<=16 for c in choices): p.error('choices 最多 3 个、每个 1 至 16 字')
    if args.minutes is not None:
        if not 0<args.minutes<=1440: p.error('分钟数必须在 0 到 1440 之间')
        board.update(startsAt=time.time(),endsAt=time.time()+args.minutes*60)
    for key in ('startsAt','endsAt'):
        if board[key] is not None and (not isinstance(board[key],(int,float)) or not __import__('math').isfinite(board[key])): p.error(key+' 必须是有限的 Unix 秒时间戳')
    board['writtenAt']=time.time()
    board['action']=args.command
    if args.command != 'close': board['turnID']=str(uuid.uuid4());board['sceneSequence']=0
    if args.command=='show': board['showID']=str(uuid.uuid4())
    if args.command=='close':
        status=read(DATA/'status.json')
        if status.get('visibility')=='visible':board['showID']=status.get('showID',board['showID'])
    write(DATA/'content.json',board)
    if args.command=='show':
        if not APP.exists(): p.error('尚未编译，请执行 scripts/build.sh')
        if not visible():open_app('--external',board['showID'])
    if talking:
        print(json.dumps(receive_event(args.wait,(board.get('showID'),board.get('turnID'))),ensure_ascii=False))
        return
    print(json.dumps({'command':args.command,'title':board['title'],'content':str(DATA/'content.json')},ensure_ascii=False))
if __name__=='__main__': main()
