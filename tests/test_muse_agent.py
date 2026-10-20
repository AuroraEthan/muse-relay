import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import muse_agent
import server
from runtime import check_server_url


class MuseAgent(unittest.TestCase):
    def test_muse_prefix_is_valid_but_other_paths_and_credentials_rejected(self):
        prefix='https://example.com/api/muses/m_'+'a'*32
        self.assertEqual(check_server_url(prefix),prefix)
        for url in ['https://example.com/api/muses/../admin','https://example.com/other','https://user:pw@example.com','https://example.com/api/muses/m_'+'a'*32+'?token=secret']:
            with self.assertRaises(ValueError):check_server_url(url)

    def test_pair_connect_deliver_ack_and_private_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); relay=server.make_server('127.0.0.1',0,str(root/'q.db'),'p','c')
            thread=threading.Thread(target=relay.serve_forever,daemon=True);thread.start()
            seen=[]
            class Receiver(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    seen.append((json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers.get('Idempotency-Key')))
                    self.send_response(200);self.end_headers();self.wfile.write(b'{"ok":true}')
                def log_message(self,*args):pass
            local=__import__('http.server',fromlist=['HTTPServer']).HTTPServer(('127.0.0.1',0),Receiver)
            t=threading.Thread(target=local.serve_forever,daemon=True);t.start()
            try:
                user=relay.registry.signup('owner','a-long-safe-password');muse=relay.registry.create(user['id'],'Agent Muse',True)
                mid=muse['id'];code=relay.registry.pairing(mid,user['id'])['code']
                config=root/'connection.json'; origin=f'http://127.0.0.1:{relay.server_port}'
                muse_agent.connect(origin,code,f'http://127.0.0.1:{local.server_port}/inbox',str(config))
                self.assertEqual(config.stat().st_mode & 0o777,0o600)
                with self.assertRaises(FileExistsError):muse_agent.connect(origin,code,'http://127.0.0.1:1234',str(config))
                message_id,_=relay.registry.queue(mid).put_text('hello Muse')
                agent=muse_agent.agent_from_config(str(config))
                self.assertTrue(agent.poll_once());self.assertFalse(agent.poll_once())
                self.assertEqual(seen,[({'message':'hello Muse'},message_id)])
                self.assertEqual(relay.registry.queue(mid).status(message_id)['status'],'acked')
                self.assertEqual(json.loads(config.read_text())['server_url'],origin+'/api/muses/'+mid)
                # Status checks and retries must use the same source prefix and persistent ledger.
                self.assertTrue(muse_agent.agent_from_config(str(config)).known(message_id))
            finally:
                local.shutdown();local.server_close();t.join();relay.shutdown();relay.server_close();thread.join()

    def test_pair_error_does_not_leave_partial_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'connection.json'
            with patch('muse_agent.json_request',side_effect=ValueError('invalid')):
                with self.assertRaises(ValueError):muse_agent.connect('https://example.com','bad','http://127.0.0.1:8000/inbox',str(file))
            self.assertFalse(file.exists())
