"""原生白板的可编辑文稿、播放会话与 MCP 标准输入输出接口。"""
import argparse
import contextlib
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
import threading
import uuid
sys.dont_write_bytecode=True
import whiteboard as board
from canvas_schema import validate_canvas

def check(ok, explanation):
    if not ok:raise ValueError(explanation)

def short(value, limit):
    return isinstance(value,str) and 0<len(value.strip())<=limit

def validate_page(page):
    check(isinstance(page,dict) and not set(page)-{'id','title','body','canvas','scene','interaction','visualStyle'},'未知页字段')
    check(page.get('visualStyle') in (None,'live-side','live-full'),'未知画面样式')
    check(short(page.get('id'),64) and short(page.get('title'),120),'需要短 id 与主句')
    check(isinstance(page.get('body',''),str) and len(page.get('body',''))<=160,'附注最多160字')
    validate_canvas(page.get('canvas'))
    scene=page.get('scene',{})
    options={'layout':('editorial','focus','countdown'),'motion':('slide','rise','quiet','pop','sweep','breathe'),
             'accent':('orange','ink','rose'),'decoration':('none','strides','rings')}
    check(isinstance(scene,dict) and all(k in options and v in options[k] for k,v in scene.items()),'非法场景选项')
    ui=page.get('interaction')
    if ui is not None:
        check(isinstance(ui,dict) and not set(ui)-{'choices','placeholder'},'非法交互字段')
        choices=ui.get('choices',[])
        check(isinstance(choices,list) and len(choices)<=3 and all(short(x,16) for x in choices),'选项最多三个，每个16字')
        check(short(ui.get('placeholder','写下回答'),60),'输入提示过长')

def document_size(doc):
    return len(json.dumps(doc,ensure_ascii=False).encode())

def validate_document(doc):
    check(isinstance(doc,dict) and not set(doc)-{'version','title','pages'},'文稿只接受 version、title、pages')
    check(type(doc.get('version',1)) is int and doc.get('version',1)==1 and short(doc.get('title'),80),'需要文稿标题和版本 1')
    pages=doc.get('pages')
    check(isinstance(pages,list) and 1<=len(pages)<=80,'每份文稿 1–80 页')
    for page in pages:validate_page(page)
    check(len({p['id'] for p in pages})==len(pages),'页 id 必须唯一')
    check(document_size(doc)<=512*1024,'文稿超过512 KiB')
    return doc

@contextlib.contextmanager
def lock():
    board.DATA.mkdir(parents=True,exist_ok=True)
    fd=os.open(board.DATA,os.O_RDONLY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX);yield
    finally:os.close(fd)

def fit_live_window(state,index):
    if not state.get('followThread'):return index
    pages=state['document']['pages']
    pages.extend(state.pop('followBacklog',[]))
    drop=min(index,max(0,len(pages)-80))
    if drop:del pages[:drop];index-=drop
    if len(pages)>80:state['followBacklog']=pages[80:];del pages[80:]
    return index

def activate(state,index,action,new_turn=True):
    doc=state['document'];page=doc['pages'][index]
    state.update(title=page['title'],body=page.get('body',''),subtitle=doc['title'],
                 items=[],startsAt=None,endsAt=None,canvas=page.get('canvas'),scene=page.get('scene'),
                 interaction=page.get('interaction'),visualStyle=page.get('visualStyle'),pageIndex=index,pageCount=len(doc['pages']),pageID=page['id'],
                 action=action,writtenAt=time.time())
    if new_turn:
        state.update(turnID=str(uuid.uuid4()),sceneSequence=0);state.pop('followDelivery',None)
    else:state['sceneSequence']=state.get('sceneSequence',0)+1

def check_session(state,args):
    check(state.get('document') and state.get('showID')==args.get('session'),'会话已改变')
    status=board.read(board.DATA/'status.json')
    check(state.get('action')!='close' and not (status.get('showID')==state['showID'] and status.get('visibility')=='dismissed'),'白板已退出')
    if status.get('visibility')=='visible' and status.get('showID')!=state['showID']:
        check(state.get('action')=='show' and state.get('writtenAt',0)>status.get('rendererObservedAt',0),'已切换到其他白板')
    if 'revision' in args:check(state['documentRevision']==args['revision'],'文稿已更新，请先读取最新版本')

def state_summary(state):
    return dict(session=state['showID'],turn=state['turnID'],page=state['pageID'],
                index=state['pageIndex']+1,pages=state['pageCount'],revision=state['documentRevision'],writtenAt=state['writtenAt'])

def run(name,args):
    if name=='live_ask':
        import 现场白板 as live
        seconds=args.get('seconds',45)
        check(type(seconds) in (int,float) and 0<=seconds<=120,'等待时间应为 0–120 秒')
        page={k:args[k] for k in ('id','text','choices','drawing','canvas') if k in args}
        request={k:args[k] for k in ('session','generation','fromPage','show_now','eventID') if k in args}
        if request.get('session') and not request.get('eventID'):
            request['show_now']=True
        shown=live.publish({**request,'pages':[page]},sys.modules[__name__])
        if shown['status']!='shown':return shown
        return {**shown,**live.listen({'session':shown['session'],'seconds':seconds},sys.modules[__name__])}
    if name in ('live_board','live_input'):
        import 现场白板 as live
        return (live.publish if name=='live_board' else live.listen)(args,sys.modules[__name__])
    if name=='converse':
        from 当前聊天 import chat_page
        thread_arg=args.get('thread') or os.environ.get('CODEX_THREAD_ID')
        check(isinstance(thread_arg,str),'需要当前聊天 UUID')
        thread=str(uuid.UUID(thread_arg))
        seconds=args.get('seconds',45)
        check(type(seconds) in (int,float) and 0<=seconds<=120,'等待时间应为0至120秒')
        page_id=args.get('id')
        check(short(page_id,64) and short(args.get('text'),120),'需要唯一页 id 与一句短话')
        page=chat_page(args['text'])
        page['id']=page_id
        if 'choices' in args:page['interaction']['choices']=args['choices']
        for key in ('scene','canvas'):
            if key in args:page[key]=args[key]
        validate_page(page)
        with lock():
            state=board.read(board.DATA/'content.json')
            if not args.get('session') and state.get('directThread')==thread and state.get('pageID')!=page_id:
                check(not any(p['id']==page_id for p in state['document']['pages']),'旧页面已结束')
            if args.get('session') or (state.get('directThread')==thread and state.get('pageID')==page_id):
                check_session(state,{'session':args.get('session',state.get('showID'))})
                check(state.get('directThread')==thread,'白板属于另一条聊天')
                if state.get('pageID')!=page_id:
                    pending=board.read(board.DATA/'pending-reply.json')
                    check(args.get('eventID') and args['eventID']==pending.get('id') and
                          (pending.get('showID'),pending.get('turnID'))==(state['showID'],state['turnID']),'需要本页真实操作')
                    pages=state['document']['pages']
                    check(not any(p['id']==page_id for p in pages),'页 id 已存在')
                    del pages[state['pageIndex']+1:]
                    pages.append(page)
                    if len(pages)>80:del pages[0]
                    while len(json.dumps(state['document'],ensure_ascii=False).encode())>512*1024 and len(pages)>1:
                        del pages[0]
                    validate_document(state['document'])
                    state['documentRevision']+=1
                    activate(state,len(pages)-1,'reply')
                    board.write(board.DATA/'content.json',state)
                else:check(state['document']['pages'][state['pageIndex']]==page,'重试的页面内容不一致')
            else:
                live=board.visible()
                check(not(live and board.read(board.DATA/'status.json').get('editing')),'用户正在输入，保留当前白板')
                state={'showID':str(uuid.uuid4()),'documentRevision':1,'directThread':thread,'outputSource':'tool',
                       'document':{'version':1,'title':'Dot · 当前对话','pages':[page]}}
                activate(state,0,'show')
                board.write(board.DATA/'content.json',state)
                if not live:board.open_app('--external',state['showID'])
        result=state_summary(state)
        if seconds:
            result.update(run('wait_answer',{'session':result['session'],'turn':result['turn'],'seconds':seconds}))
        return result
    if name=='describe':
        return {'format':{'version':1,'title':'主题','pages':[{'id':'opening','title':'先看这条曲线','canvas':{'transition':'lift','nodes':[
            {'id':'word','type':'text','text':'先看这条曲线','x':0.03,'y':0.05,'w':0.9,'h':0.36,'size':0.3,'weight':'light'},
            {'id':'arc','type':'bezier','points':[[0.08,0.8],[0.3,0.85],[0.5,0.3],[0.9,0.54]],'color':'orange','motion':'draw','marker':{'radius':6,'duration':1,'color':'ink'}}]}}]},
            'canvas':{'nodes':'1–12','origin':'左上，坐标归一化','types':['text','rect','circle','line','polyline','bezier','arrow'],
            'geometry':'x/y/w/h 或 points；bezier 为起点和每段两个控制点与终点','text':'text, size(.03..6e-1), weight(light/regular/semibold), align(left/center/right), effect(outline/underline/none)',
            'paint':'color,fill 使用 ink/orange/rose/muted、#RRGGBB 或 none；stroke 1–10',
            'animation':'motion 可选 fade,rise,slide,pop,draw,none；duration 0.1–2秒，delay 0–1秒。timeline 自编每属性 2–24 帧，0 起最长8秒；property 可为 x/y/scale/rotation/opacity/draw。',
            'track':{'property':'x','keys':[[0,-0.08],[0.42,0.01],[0.65,0]],'easing':'ease-out'},
            'transitions':['cut','lift','crossfade','push'],'marker':'路径可携带 marker；radius 2–18，duration 0.1–4，color 为安全色值'},
            'interaction':{'placeholder':'也可以自己输入','choices':['继续','换个例子']},
            'conversation':'长回答优先用 follow_chat 接入同一聊天，每次说一个重点。信息会改变下一步时主动问一句；收到 continue 则跳过问题，延续上下文。',
            'editing':'给每一页及需要局部修改的节点命名。edit 附 revision；与观众交流时 wait_answer 后用 respond 关联 answerID。'}
    if name=='wait_answer':
        state=board.read(board.DATA/'content.json');check_session(state,args)
        check(state['turnID']==args.get('turn'),'回合已改变')
        seconds=args.get('seconds',0);check(type(seconds) in (int,float) and 0<=seconds<=120,'等待时间应为0至120秒')
        event=board.receive_event(seconds,(state['showID'],state['turnID']))
        if not event:
            current=board.read(board.DATA/'content.json')
            status=board.read(board.DATA/'status.json')
            closed=current.get('showID')!=state['showID'] or current.get('action')=='close' or (status.get('showID')==state['showID'] and status.get('visibility')=='dismissed')
            outcome='closed' if closed else ('moved' if current.get('turnID')!=state['turnID'] else 'timeout')
            return {'answer':None,'event':None,'status':outcome,'turn':None if closed else current.get('turnID')}
        if state.get('followThread'):
            with lock():
                current=board.read(board.DATA/'content.json')
                if current.get('showID')==state['showID'] and current.get('turnID')==state['turnID']:
                    if current.get('queueAttempt')==event['id'] and current.get('followDelivery')!='unavailable':
                        return {'answer':None,'event':None,'status':'queued' if current.get('queuedEvent')==event['id'] else 'sending'}
                    current['deliveredEvent']=event['id']
                    board.write(board.DATA/'content.json',current)
        return {'answer':None if event.get('kind')=='continue' else event,'event':event}
    with lock():
        state=board.read(board.DATA/'content.json')
        if name in ('present','follow_chat'):
            binding={}
            if name=='follow_chat':
                from 当前聊天 import source_file,source_offset
                thread=args.get('thread') or os.environ.get('CODEX_THREAD_ID')
                check(isinstance(thread,str),'需要当前聊天 ID')
                filepath=source_file(thread)
                if state.get('followThread')==thread and board.visible() and board.read(board.DATA/'status.json').get('showID')==state.get('showID') and state.get('action')!='close':
                    return {**state_summary(state),'source':state.get('outputSource','connecting')}
                binding={'followThread':thread,'followOffset':source_offset(filepath),'outputSource':'connecting'}
                doc={'version':1,'title':'Dot · 当前对话','pages':[{'id':'waiting','title':'等 Dot 开口…','interaction':{}}]}
            else:doc=validate_document(args.get('document'))
            page=args.get('page',doc['pages'][0]['id']);ids=[p['id'] for p in doc['pages']]
            check(page in ids,'页不存在')
            active=board.visible()
            state=dict(showID=str(uuid.uuid4()),document=doc,documentRevision=1,**binding)
            activate(state,ids.index(page),'show')
            board.write(board.DATA/'content.json',state)
            if not active:board.open_app('--external',state['showID'])
            return state_summary(state)
        check_session(state,args)
        if name=='read_document':return {**state_summary(state),'source':state.get('outputSource','document'),'document':state['document']}
        pages=state['document']['pages'];index=state['pageIndex'];ids=[p['id'] for p in pages]
        if name=='navigate':
            if 'fromPage' in args:check(state['pageID']==args['fromPage'],'页面已改变')
            check(args.get('page') in ids,'页不存在')
            index=ids.index(args['page'])
            if index==state['pageIndex']:return state_summary(state)
            activate(state,fit_live_window(state,index),'navigate')
        elif name=='edit':
            ops=args.get('changes')
            check(isinstance(ops,list) and 1<=len(ops)<=80,'一次 1–80 项编辑')
            current=state['pageID'];before=json.dumps(pages[index],sort_keys=True);pending=board.read(board.DATA/'pending-reply.json')
            for change in ops:
                check(isinstance(change,dict),'编辑项必须是对象')
                op=change.get('op');target=change.get('id');ids=[p['id'] for p in pages]
                if op=='insert':
                    page=change.get('page');validate_page(page);after=change.get('after')
                    check(page['id'] not in ids and (after is None or after in ids),'插页位置或新 id 无效')
                    pages.insert(len(pages) if after is None else ids.index(after)+1,page);continue
                check(target in ids,'待编辑的页不存在');i=ids.index(target)
                if op=='remove':pages.pop(i)
                elif op=='set':
                    attrs=change.get('set');check(isinstance(attrs,dict) and 'id' not in attrs,'set 需要属性且不能改 id')
                    pages[i].update(attrs)
                elif op=='node':
                    attrs=change.get('set');check(isinstance(attrs,dict) and not {'id','type'}.intersection(attrs),'非法节点属性')
                    node=next((n for n in (pages[i].get('canvas') or {}).get('nodes',[]) if n.get('id')==change.get('node')),None)
                    check(node is not None,'待修改的节点不存在');node.update(attrs)
                else:raise ValueError('未知编辑操作')
            validate_document(state['document']);ids=[p['id'] for p in pages]
            index=ids.index(current) if current in ids else min(index,len(ids)-1)
            changed=current not in ids or json.dumps(pages[index],sort_keys=True)!=before
            check(not(changed and pending.get('turnID')==state['turnID']),'观众已回答，请使用 respond')
            state['documentRevision']+=1
            activate(state,index,'edit' if changed else 'catalog',new_turn=current not in ids)
        elif name=='respond':
            event=board.read(board.DATA/'pending-reply.json')
            event_id=args.get('eventID') or args.get('answerID')
            check(event.get('kind')!='continue' or args.get('eventID'),'跳过本题时使用 eventID 续页')
            check(event_id and event.get('id')==event_id and
                  (event.get('showID'),event.get('turnID'))==(state['showID'],state['turnID']),'回答已过期')
            page=args.get('page');validate_page(page);check(page['id'] not in ids,'需要新的页 id')
            pages.insert(index+1,page);index=fit_live_window(state,index+1);validate_document(state['document']);state['documentRevision']+=1
            activate(state,index,'reply')
        elif name=='close':
            if state.get('outputSource')=='live-tool':
                check(not board.read(board.DATA/'status.json').get('editing'),'观众正在输入')
                event=board.read(board.DATA/'pending-reply.json')
                check(event.get('turnID')!=state['turnID'] or event.get('id')==args.get('eventID'),'请先处理观众的回答')
            state.update(action='close',writtenAt=time.time())
        else:raise ValueError('未知操作')
        board.write(board.DATA/'content.json',state);return state_summary(state)

def obj(props,required=()):
    return {'type':'object','properties':props,'required':list(required),'additionalProperties':False}
string={'type':'string'}
dictionary={'type':'object'}
live_page=obj({'id':string,'text':string,'choices':{'type':'array','items':string,'maxItems':3},
               'drawing':dictionary,'canvas':dictionary},['id','text'])
specs={
 'live_ask':('由你决定何时开板提问。直接显示一句话并在一次工具调用中取得观众选择或原文。没有即 answer 的内容，空格只表示 continue。超时可用 live_input 续等。',obj({**live_page['properties'],'session':string,'generation':string,'fromPage':string,'show_now':{'type':'boolean'},'eventID':string,'seconds':{'type':'number'}},['id','text'])),
 'live_board':('当图比口述清楚时，自行唤起白板并画出你要说明的内容。一次 1–4 页。追加需 session、generation；随讲解主动换页时传 show_now=true 和 fromPage。观众打断后附 eventID。drawing 配图，canvas 自由全页。',obj({'pages':{'type':'array','items':live_page,'minItems':1,'maxItems':4},'session':string,'generation':string,'eventID':string,'show_now':{'type':'boolean'},'fromPage':string},['pages'])),
 'live_input':('等待现场观众的真实输入，已缓冲页面之间翻页不会打断等待。answer 含原文，continue 只表示跳过，closed 表示退出，timeout 时可续等。',obj({'session':string,'seconds':{'type':'number'}},['session'])),
 'converse':('直接在当前 Dot 聊天说一句并等待观众接话。首次传真实 thread、唯一 id 和 text。下一句附上次的 session、eventID。continue 只表示翻页。可附简短 choices、scene 或 canvas。',obj({'thread':string,'id':string,'text':string,'choices':{'type':'array','items':string},'scene':dictionary,'canvas':dictionary,'session':string,'eventID':string,'seconds':{'type':'number'}},['id','text'])),
 'follow_chat':('将正在进行的当前聊天输出直达本机白板，传当前 thread UUID。请直接说下一句话；需互动时调用 wait_answer，按 event.kind 区分回答和继续。',obj({'thread':string})),
 'describe':('读取创作语法、图元、动画、文本、交互与可编辑示例。',obj({})),
 'present':('打开可编辑文稿。document={version:1,title,pages:[{id,title,canvas?,scene?,interaction?}]}。只有显式打开才用。',obj({'document':dictionary,'page':string},['document'])),
 'read_document':('读取页、节点、当前索引与文稿版本。',obj({'session':string},['session'])),
 'edit':('原子编辑。changes 支持 {op:set,id,set}、{op:node,id,node,set}、{op:insert,page,after?}、{op:remove,id}。',obj({'session':string,'revision':{'type':'integer'},'changes':{'type':'array','items':dictionary}},['session','revision','changes'])),
 'navigate':('跳到指定页。',obj({'session':string,'page':string,'fromPage':string},['session','page'])),
 'wait_answer':('等待用户操作。event.kind 为 answer 或 continue；空格时 answer=null。',obj({'session':string,'turn':string,'seconds':{'type':'number'}},['session','turn'])),
 'respond':('依据真实回答生成新页，关联回答 id 后插入并显示。',obj({'session':string,'answerID':string,'eventID':string,'page':dictionary},['session','page'])),
 'close':('讲清后主动收起当前展示。有未处理的输入时先接话；依据最后一个事件结束时带上 eventID。',obj({'session':string,'eventID':string},['session']))}

def serve():
    output=threading.Lock()
    waits=threading.BoundedSemaphore(4)
    def deliver(packet):
        with output:print(json.dumps(packet,ensure_ascii=False),flush=True)
    def wait_async(msg):
        try:
            value=run(msg['params']['name'],msg['params'].get('arguments',{}))
            result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
        except (ValueError,OSError,TypeError,KeyError,subprocess.SubprocessError) as exc:
            result={'content':[{'type':'text','text':str(exc)}],'isError':True}
        finally:waits.release()
        deliver({'jsonrpc':'2.0','id':msg['id'],'result':result})
    for raw in sys.stdin.buffer:
        msg={}
        try:
            check(len(raw)<1_100_000,'消息过大');msg=json.loads(raw)
            if 'id' not in msg:continue
            method=msg['method'];params=msg.get('params',{})
            if method=='initialize':
                version=params.get('protocolVersion')
                result={'protocolVersion':version if version in ('2024-11-05','2025-03-26','2025-06-18','2025-11-25') else '2025-06-18',
                        'capabilities':{'tools':{}},'instructions':'白板是你在讲解时可随手使用的媒介。图能讲清概念时自己调用 live_board，不用等待用户开板。图形和时机由你决定。edit 原位更新，show_now 主动换页，close 收起；尊重正在输入的用户和 Esc。','serverInfo':{'name':'dynamic-whiteboard','version':'1.4.0'}}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':[{'name':k,'description':v[0],'inputSchema':v[1]} for k,v in specs.items()]}
            elif method=='tools/call':
                if params.get('name') in ('wait_answer','converse','live_input','live_ask') and waits.acquire(blocking=False):
                    threading.Thread(target=wait_async,args=(msg,),daemon=True).start();continue
                if params.get('name') in ('wait_answer','converse','live_input','live_ask'):raise ValueError('已存在四个等待请求')
                try:value=run(params['name'],params.get('arguments',{}));error=False
                except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as exc:value={'error':str(exc)};error=True
                result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':error}
            else:raise KeyError('不支持的方法')
            response={'jsonrpc':'2.0','id':msg['id'],'result':result}
        except (ValueError,KeyError,TypeError) as exc:
            response={'jsonrpc':'2.0','id':msg.get('id'),'error':{'code':-32600,'message':str(exc)}}
        deliver(response)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['mcp',*specs]);parser.add_argument('--file',type=pathlib.Path)
    args=parser.parse_args()
    if args.command=='mcp':serve()
    else:
        try:
            payload=json.loads(args.file.read_text()) if args.file else json.load(sys.stdin)
            if args.file and args.command=='present':payload={'document':payload}
            print(json.dumps(run(args.command,payload),ensure_ascii=False))
        except (ValueError,KeyError,TypeError,OSError) as exc:parser.exit(2,str(exc)+'\n')
