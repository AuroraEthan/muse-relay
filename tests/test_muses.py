import concurrent.futures
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import server


class Muses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'queue.db')
        self.http = server.make_server('127.0.0.1', 0, self.db, 'producer', 'consumer', public_send=True)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.http.server_port)
        self.a = self.client(); self.b = self.client(); self.anon = self.client()

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(); self.tmp.cleanup()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, path, body=None, client=None, method=None, headers=None):
        headers = dict(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body).encode(); headers.setdefault('Content-Type', 'application/json')
        elif isinstance(body, str):
            body = body.encode(); headers.setdefault('Content-Type', 'text/plain; charset=utf-8')
        headers.setdefault('Origin', self.url)
        request = urllib.request.Request(self.url + path, data=body, headers=headers, method=method)
        try: r = (client or self.anon).open(request, timeout=10)
        except urllib.error.HTTPError as e: r = e
        raw = r.read(); content = json.loads(raw) if raw else None
        return r.status, content, r.headers

    def account(self, client, name):
        result = self.req('/api/auth/signup', {'username': name, 'password': 'a-long-safe-password'}, client)
        self.assertEqual(result[0], 201, result[1]); return result[1]

    def muse(self, client, name='My Muse', public=True):
        result = self.req('/api/muses', {'name': name, 'public_send': public}, client)
        self.assertEqual(result[0], 201, result[1]); return result[1]['muse']['id']

    def pair(self, mid, client):
        code = self.req(f'/api/muses/{mid}/pairing', {}, client)[1]['code']
        result = self.req('/api/pair', {'code': code})
        self.assertEqual(result[0], 200, result[1]); return result[1]['device_token']

    def test_accounts_cookie_logout_and_login(self):
        self.account(self.a, 'alice')
        self.assertEqual(self.req('/api/auth/me', client=self.a)[1]['user']['username'], 'alice')
        self.assertEqual(self.req('/api/auth/me')[0], 401)
        self.assertEqual(self.req('/api/auth/logout', {}, self.a)[0], 200)
        self.assertEqual(self.req('/api/auth/me', client=self.a)[0], 401)
        self.assertEqual(self.req('/api/auth/login', {'username':'alice','password':'wrong-password'}, self.a)[0],401)
        self.assertEqual(self.req('/api/auth/login', {'username':'alice','password':'a-long-safe-password'}, self.a)[0],200)
        self.assertEqual(self.req('/api/auth/signup', {'username':'alice','password':'another-long-password'}, self.b)[0],409)
        self.assertEqual(self.req('/api/auth/signup', {'username':'bad user','password':'short'}, self.b)[0],400)

    def test_muse_ownership_and_legacy_isolation(self):
        self.account(self.a, 'alice'); self.account(self.b, 'bob')
        a = self.muse(self.a); b = self.muse(self.b)
        for mid, client in [(a,self.b),(b,self.a)]:
            self.assertEqual(self.req(f'/api/muses/{mid}/messages',client=client)[0],404)
            self.assertEqual(self.req(f'/api/muses/{mid}/pairing',{},client)[0],404)
            self.assertEqual(self.req(f'/api/muses/{mid}/settings',{'public_send':False},client)[0],404)
        self.assertEqual([m['id'] for m in self.req('/api/muses',client=self.a)[1]['muses']],[a])
        self.req(f'/api/muses/{a}/send','hello a',self.a)
        self.req(f'/api/muses/{b}/send','hello b',self.b)
        self.assertEqual(self.req(f'/api/muses/{a}/messages',client=self.a)[1]['stats']['total'],1)
        self.assertEqual(self.req('/messages',headers={'Authorization':'Bearer producer'})[1]['stats']['total'],0)
        self.assertEqual(self.req('/api/muses')[0],401)

    def sender_key(self, mid, client):
        result=self.req(f'/api/muses/{mid}/sender-key',{},client)
        self.assertEqual(result[0],201,result[1])
        return result[1]['key']

    def test_sender_key_routing_and_plain_text_contract(self):
        self.account(self.a,'alice'); self.account(self.b,'bob')
        a=self.muse(self.a); b=self.muse(self.b)
        ka=self.sender_key(a,self.a); kb=self.sender_key(b,self.b)
        headers={'Authorization':'Bearer '+ka,'Origin':'https://external.example','Idempotency-Key':'same'}
        result=self.req('/api/send','안녕하세요',headers=headers)
        self.assertEqual(result[0],201,result[1])
        self.assertEqual(result[2]['Access-Control-Allow-Origin'],'*')
        self.assertNotIn('Access-Control-Allow-Credentials',result[2])
        self.assertEqual(self.req('/api/send','안녕하세요',headers=headers)[1]['created'],False)
        self.assertEqual(self.req('/api/send','different',headers=headers)[0],409)
        self.assertEqual(self.req('/api/send',' ',headers=headers)[0],400)
        self.assertEqual(self.req('/api/send','x'*16385,headers=headers)[0],413)
        self.assertEqual(self.req('/api/send',{'message':'json'},headers=headers)[0],415)
        self.assertEqual(self.req('/api/send',method='OPTIONS')[0],204)
        self.assertEqual(self.req('/api/send?muse_id='+a,'other',headers={'Authorization':'Bearer '+kb})[0],201)
        self.assertEqual(self.req(f'/api/muses/{a}/messages',client=self.a)[1]['stats']['total'],1)
        self.assertEqual(self.req(f'/api/muses/{b}/messages',client=self.b)[1]['stats']['total'],1)

    def test_no_public_sending_metadata_or_keyless_fallback(self):
        self.account(self.a,'alice'); mid=self.muse(self.a)
        self.assertFalse(self.req('/api/muses',client=self.a)[1]['muses'][0]['public_send'])
        # Even a pre-migration row set public must not grant anonymous access.
        with self.http.registry.connection() as db: db.execute('UPDATE muses SET public_send=1 WHERE id=?',(mid,))
        base=f'/api/muses/{mid}'
        for headers in ({},{'Authorization':'Bearer bad'}):
            self.assertEqual(self.req('/api/send','blocked',headers=headers)[0],401)
            self.assertEqual(self.req(base+'/send','blocked',headers=headers)[0],401)
        self.assertEqual(self.req('/api/send','cookie is not API key',self.a)[0],401)
        self.assertEqual(self.req(base)[0],401)
        self.assertEqual(self.req(base+'/send','owner',self.a)[0],201)
        self.assertEqual(self.req(base+'/send','csrf',self.a,headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.req(base+'/settings',{'public_send':True},self.a)[0],400)
        from muse_store import Registry
        registry=Registry(self.db)
        self.assertFalse(registry.info(mid)['public_send'])

    def test_sender_key_lifecycle_role_separation_and_hash_persistence(self):
        self.account(self.a,'alice'); self.account(self.b,'bob')
        mid=self.muse(self.a); base=f'/api/muses/{mid}'
        token=self.pair(mid,self.a); key=self.sender_key(mid,self.a)
        auth={'Authorization':'Bearer '+key}
        self.assertEqual(self.req('/api/send','device key',headers={'Authorization':'Bearer '+token})[0],401)
        for tail,body in [('claim',{}),('pairing',{}),('sender-key',{}),('sender-key/revoke',{}),('device/revoke',{})]:
            self.assertEqual(self.req(base+'/'+tail,body,headers=auth)[0],401)
        self.assertEqual(self.req(base+'/messages',headers=auth)[0],401)
        self.assertEqual(self.req(base+'/sender-key',{},self.b)[0],404)
        self.assertEqual(self.req(base+'/sender-key/revoke',{},self.b)[0],404)
        for tail in ('sender-key','sender-key/revoke'):
            self.assertEqual(self.req(base+'/'+tail,{},self.a,headers={'Origin':'https://evil.example'})[0],403)
        from muse_store import Registry
        registry=Registry(self.db)
        self.assertEqual(registry.sender(key),mid)
        with registry.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM muse_sender_keys')]
        self.assertNotIn(key,str(rows))
        view=self.req(base,client=self.a)[1]['muse']
        self.assertTrue(view['sender_key']['active']); self.assertNotIn(key,str(view))
        self.assertNotIn('token_hash',str(view))
        new=self.sender_key(mid,self.a); self.assertNotEqual(key,new)
        self.assertEqual(self.req('/api/send','old',headers=auth)[0],401)
        ident=self.req('/api/send','new',headers={'Authorization':'Bearer '+new})[1]['id']
        claim=self.req(base+'/claim',{},headers={'Authorization':'Bearer '+token})[1]['message']
        self.assertEqual(claim['id'],ident)
        self.assertEqual(self.req(base+'/messages/'+ident+'/ack',{'lease_token':claim['lease_token']},headers={'Authorization':'Bearer '+token})[0],200)
        self.assertEqual(self.req(base+'/sender-key/revoke',{},self.a)[0],200)
        self.assertEqual(self.req('/api/send','revoked',headers={'Authorization':'Bearer '+new})[0],401)
        self.assertFalse(self.req(base,client=self.a)[1]['muse']['sender_key']['active'])
        self.assertTrue(registry.device(mid,token))

    def test_concurrent_key_rotation_leaves_one_active_and_restart_keeps_device(self):
        self.account(self.a,'alice');mid=self.muse(self.a);device=self.pair(mid,self.a)
        owner=self.req('/api/auth/me',client=self.a)[1]['user']['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            keys=list(pool.map(lambda _:self.http.registry.rotate_sender_key(mid,owner)['key'],range(2)))
        from muse_store import Registry
        registry=Registry(self.db)
        self.assertEqual(sum(registry.sender(k)==mid for k in keys),1)
        self.assertTrue(registry.device(mid,device))
        self.assertEqual(registry.queue(mid).list_messages()['stats']['total'],0)
        registry.revoke_sender_key(mid,owner)
        self.assertTrue(all(Registry(self.db).sender(k) is None for k in keys))

    def test_pairing_one_use_rotates_device_and_scoped_delivery(self):
        self.account(self.a,'alice'); mid=self.muse(self.a); other=self.muse(self.a,'Other'); base=f'/api/muses/{mid}'
        code=self.req(base+'/pairing',{},self.a)[1]['code']
        token=self.req('/api/pair',{'code':code})[1]['device_token']; headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.req('/api/pair',{'code':code})[0],401)
        ident=self.req(base+'/send','hello',self.a)[1]['id']
        claim=self.req(base+'/claim',{},headers=headers)[1]['message']
        self.assertEqual(claim['id'],ident); self.assertEqual(claim['payload'],{'message':'hello'})
        self.assertEqual(self.req(f'/api/muses/{other}/claim',{},headers=headers)[0],401)
        self.assertEqual(self.req('/claim',{},headers=headers)[0],401)
        self.assertEqual(self.req(base+'/messages',headers=headers)[0],401)
        self.assertEqual(self.req(base+'/messages/'+ident+'/ack',{'lease_token':claim['lease_token']},headers=headers)[0],200)
        self.assertEqual(self.req(base+'/messages/'+ident,client=self.a)[1]['status'],'acked')
        self.assertEqual(self.req(base,client=self.a)[1]['muse']['device_connected'],True)
        new=self.pair(mid,self.a); self.assertNotEqual(new,token)
        self.assertEqual(self.req(base+'/claim',{},headers=headers)[0],401)
        self.assertEqual(self.req(base+'/device/revoke',{},self.a)[0],200)
        self.assertEqual(self.req(base+'/claim',{},headers={'Authorization':'Bearer '+new})[0],401)

    def test_pair_expiry_race_and_revoke_pending_code(self):
        self.account(self.a,'alice'); mid=self.muse(self.a); base=f'/api/muses/{mid}'
        code=self.req(base+'/pairing',{},self.a)[1]['code']
        with self.http.registry.connection() as db: db.execute('UPDATE muses SET pair_expires=0 WHERE id=?',(mid,))
        self.assertEqual(self.req('/api/pair',{'code':code})[0],401)
        code=self.req(base+'/pairing',{},self.a)[1]['code']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.req('/api/pair',{'code':code})[0],range(2)))
        self.assertEqual(sorted(results),[200,401])
        code=self.req(base+'/pairing',{},self.a)[1]['code']
        self.req(base+'/device/revoke',{},self.a)
        self.assertEqual(self.req('/api/pair',{'code':code})[0],401)

    def test_csrf_json_boundary_and_session_expiry(self):
        self.account(self.a,'alice'); mid=self.muse(self.a)
        foreign={'Origin':'https://evil.example'}
        for path, data in [('/api/muses',{'name':'bad','public_send':True}),(f'/api/muses/{mid}/pairing',{}),('/api/auth/logout',{}),('/api/auth/login',{'username':'alice','password':'a-long-safe-password'})]:
            self.assertEqual(self.req(path,data,self.a,headers=foreign)[0],403)
        self.assertEqual(self.req('/api/auth/signup','{}')[0],415)
        with self.http.registry.connection() as db: db.execute('UPDATE muse_sessions SET expires=0')
        self.assertEqual(self.req('/api/auth/me',client=self.a)[0],401)

    def test_muse_limits_pending_quota_and_rate_limit(self):
        self.account(self.a,'alice'); mid=self.muse(self.a)
        self.muse(self.a,'two'); self.muse(self.a,'three')
        self.assertEqual(self.req('/api/muses',{'name':'four','public_send':True},self.a)[0],429)
        q=self.http.registry.queue(mid)
        q.pending_limit=1
        self.assertEqual(q.put_text('first')[1],True)
        with self.assertRaises(Exception) as caught: q.put_text('second')
        self.assertEqual(getattr(caught.exception,'status',None),429)
        # Replayed accepted requests remain safe even when a quota is full.
        msg=q.claim(); q.ack(msg['id'],msg['lease_token'])
        self.assertEqual(q.put_text('third','key')[1],True)
        self.assertEqual(q.put_text('third','key')[1],False)
        self.http.registry.rate('test',2)
        self.http.registry.rate('test',2)
        with self.assertRaises(Exception) as caught:self.http.registry.rate('test',2)
        self.assertEqual(getattr(caught.exception,'status',None),429)

    def test_persistence_and_no_plaintext_credentials(self):
        self.account(self.a,'alice'); mid=self.muse(self.a); token=self.pair(mid,self.a)
        from muse_store import Registry
        registry=Registry(self.db)
        self.assertEqual(registry.owned(mid,self.req('/api/auth/me',client=self.a)[1]['user']['id'])['id'],mid)
        self.assertTrue(registry.device(mid,token))
        with registry.connection() as db:
            account=dict(db.execute('SELECT * FROM muse_users').fetchone())
            muse=dict(db.execute('SELECT * FROM muses').fetchone())
        self.assertNotIn('a-long-safe-password',str(account)); self.assertNotIn(token,str(muse))

    def test_delivered_retention_without_another_send(self):
        self.account(self.a,'alice'); mid=self.muse(self.a)
        q=self.http.registry.queue(mid); ident,_=q.put_text('old payload','old-key')
        message=q.claim();q.ack(ident,message['lease_token'])
        db=q.connect()
        with db: db.execute('UPDATE messages SET acked=?',(time.time()-31*86400,))
        db.close()
        self.http.registry.maintenance()
        self.assertIsNone(q.status(ident))
        self.assertEqual(q.list_messages()['stats']['total'],0)
        db=q.connect(); self.assertEqual(db.execute('SELECT count(*) FROM send_requests').fetchone()[0],0);db.close()

    def test_surrogate_unicode_rejected_without_server_disconnect(self):
        bad=chr(0xD800)
        self.assertEqual(self.req('/api/auth/signup',{'username':'alice','password':'long-password-'+bad})[0],400)
        self.account(self.a,'alice')
        self.assertEqual(self.req('/api/auth/login',{'username':'alice','password':bad})[0],400)
        self.assertEqual(self.req('/api/muses',{'name':'name'+bad,'public_send':True},self.a)[0],400)

    def test_agent_download_contains_only_public_source(self):
        # Anonymous installation download must never contain live credentials.
        request=urllib.request.Request(self.url+'/downloads/muse-agent.zip')
        with self.anon.open(request) as response: raw=response.read()
        import io,zipfile
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertTrue({'muse_agent.py','vm_agent.py','runtime.py','START.md','LICENSE'} <= set(z.namelist()))
            self.assertFalse(any(n.endswith('.env') for n in z.namelist()))
            self.assertIn('connect --server ' + self.url, z.read('START.md').decode())

if __name__=='__main__':unittest.main()
