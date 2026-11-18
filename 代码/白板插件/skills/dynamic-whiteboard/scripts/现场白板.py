"""Live visual turns for a calling skill. The caller owns the dialogue and authors every page."""
import time
import uuid


def make_pages(values, deck, limit=4):
    deck.check(isinstance(values, list) and 1 <= len(values) <= limit, '一次发送 1–%d 页' % limit)
    pages = []
    for value in values:
        deck.check(isinstance(value, dict) and not set(value) - {'id', 'text', 'choices', 'drawing', 'canvas'}, '未知现场页字段')
        deck.check(not ('drawing' in value and 'canvas' in value), '请选择配图或自由画布')
        page = {'id': value.get('id'), 'title': value.get('text'), 'interaction': {},
                'visualStyle': 'live-full' if 'canvas' in value else 'live-side'}
        if 'choices' in value:
            page['interaction']['choices'] = value['choices']
        if 'drawing' in value or 'canvas' in value:
            page['canvas'] = value.get('drawing', value.get('canvas'))
            deck.check(isinstance(page['canvas'], dict), '需要有效的画布')
        deck.validate_page(page)
        pages.append(page)
    deck.check(len({p['id'] for p in pages}) == len(pages), '每页需要不同的 id')
    return pages


def listen(args, deck):
    session = args.get('session')
    seconds = args.get('seconds', 45)
    deck.check(type(seconds) in (int, float) and 0 <= seconds <= 120, '等待时间应为 0–120 秒')
    end = time.monotonic() + seconds
    while True:
        state = deck.board.read(deck.board.DATA / 'content.json')
        if state.get('showID') != session or state.get('outputSource') != 'live-tool':
            return {'status': 'closed'}
        try:
            deck.check_session(state, {'session': session})
        except ValueError:
            return {'status': 'closed'}
        turn = state['turnID']
        event = deck.board.receive_event(max(0, end - time.monotonic()), (session, turn))
        if event:
            return {'status': event.get('kind', 'answer'), 'event': event, 'page': state['pageID'],
                    'question': state['title'], 'generation': state['liveGeneration']}
        after = deck.board.read(deck.board.DATA / 'status.json')
        if after.get('showID') == session and after.get('visibility') == 'dismissed':
            return {'status': 'closed'}
        if time.monotonic() >= end:
            return {'status': 'timeout'}


def publish(args, deck, limit=4):
    pages = make_pages(args.get('pages'), deck, limit)
    session = args.get('session')
    show_now = args.get('show_now', False)
    deck.check(type(show_now) is bool, 'show_now 应为布尔值')
    with deck.lock():
        state = deck.board.read(deck.board.DATA / 'content.json')
        if session is None:
            deck.check(not any(k in args for k in ('generation', 'eventID')), '续讲需要原 session')
            status = deck.board.read(deck.board.DATA / 'status.json')
            opening = (state.get('action') == 'show' and state.get('showID') != status.get('showID')
                       and time.time() - state.get('writtenAt', 0) < 8)
            deck.check(not opening and not deck.board.visible(), '白板正在使用，请在原会话继续')
            state = {'showID': str(uuid.uuid4()), 'outputSource': 'live-tool', 'documentRevision': 1,
                     'liveGeneration': uuid.uuid4().hex,
                     'document': {'version': 1, 'title': '动态白板', 'pages': pages}}
            deck.validate_document(state['document'])
            deck.activate(state, 0, 'show')
            deck.board.write(deck.board.DATA / 'content.json', state)
            deck.board.open_app('--external', state['showID'])
        else:
            deck.check_session(state, {'session': session})
            deck.check(state.get('outputSource') == 'live-tool', '需要现场会话')
            deck.check(args.get('generation') == state.get('liveGeneration'), '上一轮已结束')
            catalog = state['document']['pages']
            index = state['pageIndex']
            event = deck.board.read(deck.board.DATA / 'pending-reply.json')
            pending = (event.get('showID'), event.get('turnID')) == (session, state['turnID'])
            replying = args.get('eventID') is not None
            if show_now and not replying:
                if deck.board.read(deck.board.DATA / 'status.json').get('editing'):
                    return {**deck.state_summary(state), 'generation': state['liveGeneration'], 'status': 'editing'}
                deck.check(args.get('fromPage') == state['pageID'], '观众已翻页，请读取当前页')
            if replying:
                deck.check(pending and args['eventID'] == event.get('id'), '请关联刚刚收到的回答或跳过事件')
                del catalog[index+1:]
            elif pending:
                return {**deck.state_summary(state), 'generation': state['liveGeneration'], 'status': 'interrupted', 'event': event}
            known = {page['id']: page for page in catalog}
            additions = [p for p in pages if p['id'] not in known]
            deck.check(all(known.get(p['id'], p) == p for p in pages), '相同 id 的内容不一致')
            if additions:
                catalog.extend(additions)
                if replying:
                    index += 1
                    state['liveGeneration'] = uuid.uuid4().hex
                elif show_now:
                    index = catalog.index(additions[0])
                while (len(catalog) > 80 or deck.document_size(state['document']) > 512*1024) and index:
                    del catalog[0]
                    index -= 1
                deck.validate_document(state['document'])
                state['documentRevision'] += 1
                deck.activate(state, index, 'reply' if replying or show_now else 'catalog', new_turn=replying or show_now)
                deck.board.write(deck.board.DATA / 'content.json', state)
            else:
                deck.check(not replying, '回答后的新页需要新 id')
        return {**deck.state_summary(state), 'generation': state['liveGeneration'], 'status': 'shown'}

