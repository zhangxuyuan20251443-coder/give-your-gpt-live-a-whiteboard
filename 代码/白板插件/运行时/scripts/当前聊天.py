"""将指定聊天的可见助手输出送到白板。原生流只加入已在该服务器运行的同一线程。"""
from contextlib import closing
import datetime
import json
import os
import pathlib
import re
import select
import socket
import sys
import time
import uuid

sys.dont_write_bytecode=True
import whiteboard as board
import 演示文稿 as deck

def source_file(thread):
    thread=str(uuid.UUID(thread))
    root=pathlib.Path(os.environ.get('CODEX_HOME',pathlib.Path.home()/'.codex'))/'sessions'
    paths=list(root.glob('*/*/*/*-'+thread+'.jsonl'))
    if len(paths)!=1:raise ValueError('本机没有唯一匹配的当前聊天记录')
    with paths[0].open('rb') as f:
        meta=json.loads(f.readline())
    if meta.get('type')!='session_meta' or meta['payload'].get('id')!=thread:
        raise ValueError('聊天记录与线程不匹配')
    return paths[0]

def source_offset(path):
    # The writer may still be appending one JSON line when the board opens.
    with path.open('rb') as f:
        end=f.seek(0,os.SEEK_END)
        while end:
            start=max(0,end-8192)
            f.seek(start)
            last=f.read(end-start).rfind(b'\n')
            if last>=0:return start+last+1
            end=start
    return 0

def phrases(text):
    text=text.split('<oai-mem-citation>',1)[0]
    text=re.sub(r'!?\[([^\]]*)\]\((?:<[^>]+>|[^)]+)\)',r'\1',text)
    text=re.sub(r'(?m)^\s*(?:#{1,6} |[-*] |\d+[.)] |\x60\x60\x60[^\n]*)','',text)
    text=text.replace('**','').replace('\x60','')
    for line in re.findall(r'[^\n。！？!?]+[。！？!?]*|[。！？!?]+',text):
        line=line.strip()
        while line:
            if len(line)<=26 or (line.isascii() and len(line)<=80):yield line;break
            width=74 if line[:26].isascii() else 26
            region=line[:width];cuts=list(re.finditer(r'[，、：；,;:。]\s*|\s+',region))
            n=cuts[-1].end() if cuts and cuts[-1].end()>width//3 else width
            part=line[:n].strip()
            if part:yield part
            line=line[n:].strip()

def chat_page(title):
    scene={'layout':'editorial','motion':'rise','accent':'ink'}
    if title.endswith(('？','?')):
        scene={'layout':'focus','motion':'breathe','accent':'rose','decoration':'rings'}
    elif len(title)<=12:
        scene={'layout':'focus','motion':'slide','accent':'orange'}
    return {'id':uuid.uuid4().hex,'title':title,'interaction':{},'scene':scene}

class Closed(Exception):
    pass

class Output:
    def __init__(self,session,thread):
        self.session=session;self.thread=thread;self.started=time.monotonic()
    def check(self,state):
        status=board.read(board.DATA/'status.json')
        if state.get('showID')!=self.session or state.get('action')=='close':raise Closed()
        if status.get('showID')==self.session:
            if status.get('visibility')=='dismissed' or not board.visible():raise Closed()
        elif time.monotonic()-self.started>8:raise Closed()
    def write(self,titles,source,stamp=None,new_turn=False):
        with deck.lock():
            state=board.read(board.DATA/'content.json');self.check(state)
            if not titles and state.get('outputSource')==source:return
            state['outputSource']=source
            if stamp is not None:state['sourceMessageAt']=stamp
            if titles:
                pages=state['document']['pages'];pages.extend(state.pop('followBacklog',[]));idx=state['pageIndex']
                event=board.read(board.DATA/'pending-reply.json')
                waiting=event.get('turnID')==state['turnID'] and (event.get('kind')=='continue' or event.get('id') in (state.get('deliveredEvent'),state.get('queuedEvent')))
                incoming=[chat_page(t) for t in titles]
                editing=board.read(board.DATA/'status.json').get('editing')
                fresh=new_turn and not editing and (event.get('turnID')!=state['turnID'] or waiting)
                if fresh or (waiting and event.get('kind')!='continue'):del pages[idx+1:]
                waiting=waiting or fresh
                first=pages[idx]['id']=='waiting' and not editing and (event.get('turnID')!=state['turnID'] or waiting)
                if first:pages[idx:idx+1]=incoming
                elif waiting:pages[idx+1:idx+1]=incoming;idx+=1
                else:pages.extend(incoming)
                # Bound past pages once read. Pending pages stay available for Space.
                idx=deck.fit_live_window(state,idx)
                state['documentRevision']+=1
                deck.activate(state,idx,'reply' if first or waiting else 'catalog',new_turn=first or waiting)
            else:state.update(action='catalog',writtenAt=time.time())
            board.write(board.DATA/'content.json',state)
    def alive(self):
        self.check(board.read(board.DATA/'content.json'))

def visible_text(msg):
    if msg.get('type')!='response_item':return ''
    item=msg.get('payload',{})
    if (item.get('type')!='message' or item.get('role')!='assistant'
        or item.get('phase') not in ('commentary','final_answer') or item.get('recipient') not in (None,'all')):return ''
    return ''.join(c.get('text','') for c in item.get('content',[]) if c.get('type')=='output_text')

def tail(path,offset,out,omit=None):
    out.write([],'message');fresh=False;idle=False
    with path.open('rb') as f, closing(select.kqueue()) as q:
        f.seek(offset)
        flags=select.KQ_NOTE_WRITE|select.KQ_NOTE_EXTEND|select.KQ_NOTE_RENAME|select.KQ_NOTE_DELETE
        q.control([select.kevent(f,filter=select.KQ_FILTER_VNODE,flags=select.KQ_EV_ADD|select.KQ_EV_CLEAR,fflags=flags)],0,0)
        while True:
            out.alive();pos=f.tell();line=f.readline()
            if not line.endswith(b'\n'):
                f.seek(pos)
                if idle:queue_if_idle(out)
                q.control(None,1,0.5 if idle else 1);continue
            obj=json.loads(line);text=visible_text(obj);ident=obj.get('payload',{}).get('id')
            payload=obj.get('payload',{})
            if obj.get('type')=='event_msg' and payload.get('type')=='task_started':fresh=True;idle=False
            if obj.get('type')=='event_msg' and payload.get('type')=='task_complete':idle=True
            if text:
                if omit and ident in omit:
                    text=text[omit.pop(ident):]
                stamp=datetime.datetime.fromisoformat(obj['timestamp'].replace('Z','+00:00')).timestamp()
                out.write(list(phrases(text)),'message',stamp,new_turn=fresh);fresh=False

def connect_daemon(address=None):
    import websocket
    root=pathlib.Path(os.environ.get('CODEX_HOME',pathlib.Path.home()/'.codex'))
    addr=address or root/'app-server-control/app-server-control.sock'
    sock=socket.socket(socket.AF_UNIX);sock.settimeout(1)
    try:
        sock.connect(str(addr))
        ws=websocket.create_connection('ws://localhost/',socket=sock,timeout=1,suppress_origin=True)
    except BaseException:sock.close();raise
    def rpc(i,method,args):
        ws.send(json.dumps({'id':i,'method':method,'params':args}))
        while True:
            v=json.loads(ws.recv())
            if v.get('id')==i:
                if 'error' in v:raise ValueError('本机线程接口不可用')
                return v['result']
    try:
        rpc(1,'initialize',{'clientInfo':{'name':'whiteboard_output','version':'1'},'capabilities':{'experimentalApi':True}})
        ws.send(json.dumps({'method':'initialized','params':{}}))
    except BaseException:ws.close();raise
    return ws,rpc

def queue_if_idle(out):
    # Queue only after a completed turn. Active chats receive their actions through wait_answer.
    state=board.read(board.DATA/'content.json')
    event=board.read(board.DATA/'pending-reply.json')
    eid=event.get('id')
    if not eid or event.get('turnID')!=state.get('turnID') or eid in (state.get('deliveredEvent'),state.get('queueAttempt')):return
    with deck.lock():
        state=board.read(board.DATA/'content.json');out.check(state)
        if event.get('turnID')!=state.get('turnID') or eid in (state.get('deliveredEvent'),state.get('queueAttempt')):return
        state['queueAttempt']=eid;board.write(board.DATA/'content.json',state)
    body=event.get('text') if event.get('kind')!='continue' else '【白板翻页】继续下一句；本页问题已跳过。'
    result='unavailable'
    try:
        ws,rpc=connect_daemon()
        try:
            rpc(2,'thread/queue/add',{'threadId':out.thread,'clientUserMessageId':eid,'input':[{'type':'text','text':body}]})
            result='queued'
        finally:ws.close()
    except (OSError,ImportError,ValueError):pass
    except Exception as exc:
        if type(exc).__module__.split('.')[0]!='websocket':raise
    with deck.lock():
        state=board.read(board.DATA/'content.json');out.check(state)
        if state['turnID']!=event['turnID']:return
        state.update(action='catalog',followDelivery=result,writtenAt=time.time())
        if result=='queued':state['queuedEvent']=eid
        board.write(board.DATA/'content.json',state)

def native(out,seen,address=None):
    import websocket
    ws,rpc=connect_daemon(address)
    try:
        ids=rpc(2,'thread/loaded/list',{'limit':1000})['data']
        if out.thread not in ids:return
        rpc(3,'thread/resume',{'threadId':out.thread,'excludeTurns':True})
        out.write([],'delta');buffers={};hidden=set();idle=False;fresh=False
        while True:
            out.alive()
            try:m=json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                if idle:queue_if_idle(out)
                continue
            p=m.get('params',{});method=m.get('method')
            if p.get('threadId')!=out.thread:continue
            if method=='turn/started':idle=False;fresh=True
            if method=='turn/completed':idle=True
            item=p.get('item',{});key=p.get('itemId',item.get('id'))
            if method=='item/started' and item.get('type')=='agentMessage' and item.get('phase') not in (None,'commentary','final_answer'):
                hidden.add(key)
            elif method=='item/agentMessage/delta' and key and key not in hidden:
                buf=buffers.get(key,'')+p.get('delta','')
                # Emit completed clauses while the same message is still generating.
                match=re.search(r'[。！？!?\n]|[，；：,;:]\s*',buf)
                while match:
                    part=buf[:match.end()];buf=buf[match.end():];out.write(list(phrases(part)),'delta',new_turn=fresh);fresh=False
                    seen[key]=seen.get(key,0)+len(part)
                    match=re.search(r'[。！？!?\n]|[，；：,;:]\s*',buf)
                buffers[key]=buf
            elif method=='item/completed' and item.get('type')=='agentMessage' and item.get('phase') in (None,'commentary','final_answer') and key not in hidden:
                full=item.get('text','');out.write(list(phrases(full[seen.get(key,0):])),'delta',new_turn=fresh);fresh=False
                seen[key]=len(full);buffers.pop(key,None)
    finally:ws.close()

def main():
    session,thread,raw_offset=sys.argv[1:];path=source_file(thread);offset=int(raw_offset)
    out=Output(session,thread);seen={}
    try:
        try:native(out,seen)
        except (OSError,ImportError,ValueError,KeyError):pass
        except Exception as exc:
            if isinstance(exc,Closed):raise
            if type(exc).__module__.split('.')[0]!='websocket':raise
        tail(path,offset,out,seen)
    except Closed:pass

if __name__=='__main__':main()
