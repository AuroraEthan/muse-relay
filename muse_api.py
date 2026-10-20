"""HTTP interface for self-service Muse accounts, devices and public senders."""
import io
import json
from pathlib import Path
import re
import zipfile
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs, urlsplit
from muse_store import MUSE_ID, ServiceError, SESSION_TTL

SEND_PATH = re.compile(r'/api/muses/(' + MUSE_ID + r')/send')
SOURCE = Path(__file__).parent


def cookie_token(h):
    try:
        cookies=SimpleCookie(h.headers.get('Cookie',''))
        return cookies['muse_session'].value if 'muse_session' in cookies else ''
    except CookieError: return ''


def cookie(h, token, ttl):
    secure='; Secure' if h.request_origin().startswith('https://') else ''
    return f'muse_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}{secure}'


def user(h):
    result=h.server.registry.user(cookie_token(h))
    if not result: raise ServiceError(401,'login_required')
    return result


def owner(h, mid):
    return h.server.registry.owned(mid,user(h)['id'])


def json_body(h):
    if h.headers.get('Origin') != h.request_origin():
        raise ServiceError(403,'same_origin_required')
    if h.headers.get_content_type() != 'application/json':
        raise ServiceError(415,'expected_application_json')
    return h.read_json()


def source_rate(h, action, limit):
    # Railway is the trusted front proxy; use its last appended client hop.
    forwarded=h.headers.get('X-Forwarded-For','').split(',')[-1].strip()
    ip=forwarded or h.client_address[0]
    h.server.registry.rate(action+':'+ip,limit)
    h.server.registry.rate('global:'+action, max(100,limit*20))


def text_body(h):
    if h.headers.get_content_type()!='text/plain' or h.headers.get_content_charset('utf-8') not in ('utf-8','utf8'):
        raise ServiceError(415,'expected_utf8_text_plain')
    raw=h.read_body()
    if len(raw)>16384: raise ServiceError(413,'message_limit_16384_bytes')
    try: text=raw.decode('utf-8')
    except UnicodeError: raise ServiceError(400,'invalid_utf8')
    if not text.strip(): raise ServiceError(400,'message_text_required')
    key=h.headers.get('Idempotency-Key')
    if key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',key):
        raise ServiceError(400,'invalid_retry_key')
    return text,key


def dispatch(h):
    path=urlsplit(h.path).path
    if path=='/downloads/muse-agent.zip' and h.command=='GET':
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            for name in ('muse_agent.py','vm_agent.py','runtime.py'):
                z.write(SOURCE/name,name)
            z.writestr('START.md', '''# Muse 연결\nPython 3.10 이상. 키는 자동으로 발급·저장합니다.\n1. 웹에서 계정을 만들고 Muse를 등록하세요.\n2. 이 폴더에서 python3 muse_agent.py connect 실행 후 웹의 10분 연결 코드와 localhost URL을 입력하세요.\n3. python3 muse_agent.py run 으로 실행하세요.\n환경별로 --config 파일경로를 지정할 수 있습니다. 설정 파일에 기기키가 저장되므로 공유하지 마세요.\n수신기는 메시지ID(Idempotency-Key / X-Message-ID) 중복을 방지하고 성공 시 HTTP2xx를 반환해야 합니다. TCP는 {"id":"받은ID","ok":true} 한줄 응답이 필요합니다.\n연결기기는 하나이며 새 연결은 이전 연결을 교체합니다. 웹의 연결 해제로 폐기할 수 있습니다.\n''')
        h.reply_bytes(200,stream.getvalue(),'application/zip',{'Content-Disposition':'attachment; filename="muse-agent.zip"'})
        return True
    if not path.startswith('/api/'): return False
    _dispatch(h,path)
    return True


def _dispatch(h,path):
    registry=h.server.registry; method=h.command
    if path in ('/api/auth/signup','/api/auth/login') and method=='POST':
        data=json_body(h); action=path.rsplit('/',1)[-1]
        source_rate(h,action,5 if action=='signup' else 20)
        result=getattr(registry,action)(data.get('username'),data.get('password'))
        token=registry.issue_session(result['id'])
        return h.reply(201 if action=='signup' else 200,dict(user=result),{'Set-Cookie':cookie(h,token,SESSION_TTL)})
    if path=='/api/auth/me' and method=='GET':
        return h.reply(200,dict(user=user(h)))
    if path=='/api/auth/logout' and method=='POST':
        json_body(h); user(h); registry.logout(cookie_token(h))
        return h.reply(200,dict(ok=True),{'Set-Cookie':cookie(h,'',0)})
    if path=='/api/muses' and method=='GET':
        return h.reply(200,dict(muses=registry.list(user(h)['id'])))
    if path=='/api/muses' and method=='POST':
        data=json_body(h); account=user(h)
        return h.reply(201,dict(muse=registry.create(account['id'],data.get('name'),data.get('public_send',True))))
    if path=='/api/pair' and method=='POST':
        # Pairing runs in the device CLI without browser cookies, not an owner mutation.
        if h.headers.get_content_type()!='application/json': raise ServiceError(415,'expected_application_json')
        source_rate(h,'pair',20)
        return h.reply(200,registry.pair(h.read_json().get('code')))
    match=re.fullmatch(r'/api/muses/('+MUSE_ID+r')(?:/(.*))?',path)
    if not match: raise ServiceError(404,'not_found')
    mid,tail=match[1],match[2] or ''
    if tail=='send' and method=='OPTIONS':
        return h.reply_bytes(204,b'','text/plain')
    info=registry.info(mid)
    if not info: raise ServiceError(404,'muse_not_found')
    if not tail and method=='GET':
        account=registry.user(cookie_token(h))
        if account:
            try: info=registry.owned(mid,account['id'])
            except ServiceError: pass
        return h.reply(200,dict(muse=info))
    if tail=='send' and method=='POST':
        if not info['public_send']:
            owner(h,mid)
            if h.headers.get('Origin')!=h.request_origin(): raise ServiceError(403,'same_origin_required')
        registry.rate('send:'+mid,60)
        text,key=text_body(h)
        ident,created=registry.queue(mid).put_text(text,key)
        return h.reply(201 if created else 200,dict(id=ident,created=created))
    if tail in ('settings','pairing','device/revoke') and method=='POST':
        data=json_body(h); account=user(h); current=registry.owned(mid,account['id'])
        if tail=='settings': return h.reply(200,dict(muse=registry.settings(mid,account['id'],data.get('name',current['name']),data.get('public_send',current['public_send']))))
        if tail=='pairing': return h.reply(200,registry.pairing(mid,account['id']))
        registry.revoke(mid,account['id']); return h.reply(200,dict(ok=True))
    if tail=='claim' and method=='POST' or re.fullmatch(r'messages/[A-Za-z0-9_-]{1,128}/ack',tail) and method=='POST':
        auth=h.headers.get('Authorization',''); token=auth[7:] if auth.startswith('Bearer ') else ''
        if not registry.device(mid,token): raise ServiceError(401,'invalid_device_token')
        data=h.read_json(); queue=registry.queue(mid)
        if tail=='claim':
            registry.seen(mid)
            return h.reply(200,dict(message=queue.claim()))
        lease=data.get('lease_token')
        if not isinstance(lease,str): raise ServiceError(400,'lease_token_required')
        queue.ack(tail.split('/')[1],lease)
        return h.reply(200,dict(ok=True))
    if tail=='messages' and method=='GET':
        owner(h,mid); query=parse_qs(urlsplit(h.path).query,keep_blank_values=True)
        try:
            limit=int(query.get('limit',['25'])[0]); before=int(query['before'][0]) if 'before' in query else None
            if not 1<=limit<=100 or before is not None and not 1<=before<=9223372036854775807: raise ValueError()
        except ValueError: raise ServiceError(400,'invalid_pagination')
        return h.reply(200,registry.queue(mid).list_messages(limit,before))
    match=re.fullmatch(r'messages/([A-Za-z0-9_-]{1,128})',tail)
    if match and method=='GET':
        owner(h,mid); result=registry.queue(mid).status(match[1])
        return h.reply(200 if result else 404,result or dict(error='not_found'))
    raise ServiceError(404,'not_found')
