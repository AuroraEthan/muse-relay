"""Connect this computer to a Muse, then poll and forward to a localhost receiver."""
import argparse
import getpass
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import urllib.error
from urllib.parse import urlsplit
from runtime import check_server_url, json_request
from vm_agent import Agent

DEFAULT_SERVER = 'https://vm-https-check-production.up.railway.app'


def connect(server, code, local_url, config_path, local_token=''):
    origin=check_server_url(server)
    if urlsplit(origin).path: raise ValueError('Connection server must be an origin without a path')
    config_path=Path(config_path).resolve()
    config_path.parent.mkdir(parents=True,exist_ok=True)
    # Validate local receiver before consuming a one-time code.
    with tempfile.TemporaryDirectory() as tmp:
        Agent(origin,'validate',local_url,str(Path(tmp)/'validation.db'),local_token=local_token)
    fd=os.open(config_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        result=json_request(origin+'/api/pair',{'code':code},'')
        mid=result.get('muse_id','');token=result.get('device_token','')
        if not re.fullmatch(r'm_[a-f0-9]{32}',mid) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
            raise ValueError('Invalid pairing response')
        config=dict(server_url=origin+'/api/muses/'+mid,device_token=token,
                    local_url=local_url,local_token=local_token,
                    state_path=str(config_path.with_suffix('.delivered.db')))
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            fd=None;json.dump(config,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
    except BaseException:
        if fd is not None:os.close(fd)
        config_path.unlink(missing_ok=True)
        raise
    return mid


def agent_from_config(path):
    config=json.loads(Path(path).read_text())
    return Agent(config['server_url'],config['device_token'],config['local_url'],
                 config['state_path'],local_token=config.get('local_token',''))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['connect','run'])
    parser.add_argument('--server',default=DEFAULT_SERVER)
    parser.add_argument('--config',default='./muse-connection.json')
    parser.add_argument('--local-url')
    parser.add_argument('--local-auth',action='store_true',help='Prompt for localhost HTTP Bearer token')
    parser.add_argument('--poll-interval',type=float,default=5)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.action=='connect':
        code=getpass.getpass('10분 연결 코드: ').strip()
        local_url=args.local_url or input('Muse localhost URL (예: http://127.0.0.1:18765/inbox): ').strip()
        local_token=getpass.getpass('localhost Bearer token: ') if args.local_auth else ''
        mid=connect(args.server,code,local_url,args.config,local_token)
        print('연결 완료:',mid)
        print('실행: python3 muse_agent.py run --config '+str(args.config))
        return
    if not math.isfinite(args.poll_interval) or args.poll_interval<1:
        raise ValueError('Poll interval must be at least 1 second')
    agent=agent_from_config(args.config)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    logging.info('Muse worker started; poll interval %ss',args.poll_interval)
    while True:
        try:agent.poll_once()
        except urllib.error.HTTPError as error:
            logging.error('HTTP %s; not acknowledged',error.code)
            if error.code==401:
                raise ValueError('Device disconnected. Generate a new code on the website and connect using a new --config path.')
            if args.once:raise SystemExit(1)
        except (OSError,ValueError,sqlite3.Error) as error:
            logging.error('%s; not acknowledged, will retry',type(error).__name__)
            if args.once:raise SystemExit(1)
        if args.once:return
        time.sleep(args.poll_interval)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except urllib.error.HTTPError as error:raise SystemExit('Connection failed: HTTP '+str(error.code)+'. Generate a new pairing code and retry.')
    except (OSError,ValueError,KeyError) as error:raise SystemExit('Setup error: '+str(error))
