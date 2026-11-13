#!/usr/bin/env python3
"""Nagi: owner-only agents/limits APIs and a public, metadata-free glance shell."""
import argparse
import json
import re
import mimetypes
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from loopback_peer import same_user
from owner_auth import OwnerAuth
from runtime_paths import data_directory
from agents_service import AgentsService,DEFAULTS
from jsonio import strict_json_loads
from sources_service import SourcesService
from sources_transport import SourceError

ROOT=Path(__file__).resolve().parent
FILES={'/glance':'glance-v2.html','/overview':'glance-v2.html','/nagi-glance.js':'glance-v2.js',
       '/nagi-model.js':'glance-model.js','/nagi-motion.js':'glance-motion.js','/nagi-icons.js':'project-icons.js','/nagi-setup.js':'glance-setup.js','/nagi-sheet.css':'glance-sheet.css','/nagi-glance.css':'glance-v2.css','/nagi-auth.js':'nagi-auth.js','/favicon.svg':'favicon.svg',
       '/fonts/inter-opsz.woff2':'fonts/inter-opsz.woff2','/fonts/nagi-glyph-serif.woff2':'fonts/nagi-glyph-serif.woff2'}
TYPES={'.woff2':'font/woff2','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.html':'text/html; charset=utf-8'}
API={'/api/health','/api/glance','/api/limits','/api/settings','/api/notifications','/api/notifications/claim','/api/notifications/reserve','/api/notifications/release'}
AUTH={'/auth/challenge','/auth/launch','/auth/redeem'}
SOURCES='/api/sources/v1'
SOURCE_GET={SOURCES,SOURCES+'/glance',SOURCES+'/catalog',SOURCES+'/notifications'}
SOURCE_POST={SOURCES+'/'+route for route in ('discover','test','connect','disconnect','notifications/reserve','notifications/claim','notifications/release')}
SOURCE_SCHEMA=re.compile(re.escape(SOURCES)+r'/schema/([a-z0-9]+)')
SOURCES_INIT=threading.Lock()
ICON_PATH=re.compile(r'/api/project-icon/([0-9a-f]{32})')

def platform():return {'linux':'linux','darwin':'macos'}.get(sys.platform,'unsupported')

class Handler(BaseHTTPRequestHandler):
    server_version='Nagi/2'
    def log_message(self,*args):pass
    def allowed(self,write=False):
        expected=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get_all('Host', []) != [expected]: return False
        origin=self.headers.get('Origin')
        if len(self.headers.get_all('Origin', [])) > 1 or ((origin is not None if self.path.startswith(SOURCES) else bool(origin)) and origin!='http://'+expected): return False
        if len(self.headers.get_all('Sec-Fetch-Site', [])) > 1 or self.headers.get('Sec-Fetch-Site')=='cross-site': return False
        try:
            if not same_user(self.client_address, self.connection.getsockname()): return False
        except (AttributeError, OSError, TypeError):
            return False
        return not write or (self.headers.get('Content-Type')=='application/json' and self.headers.get('X-Progress-Desk')=='1')
    def send(self,status,body,kind='application/json',ordering_headers=None,*,glasswork=False,csp=None):
        if kind=='application/json': body=json.dumps(body,ensure_ascii=False,separators=(',',':') if self.path.startswith(SOURCES) else None).encode()
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        # Only the two Glasswork documents can load generated lens tiles.
        lens_images = ' blob:' if glasswork else ''
        self.send_header('Content-Security-Policy',csp or f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'{lens_images}; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for name,value in (ordering_headers or {}).items(): self.send_header(name,value)
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(body)
    def do_HEAD(self):self.do_GET()
    def authenticate(self,body=b''):
        self.server.owner_auth.bind(self.server.server_port)
        return self.server.owner_auth.authenticated(self.headers,self.command,self.path,body)
    def sources(self):
        with SOURCES_INIT:
            if not hasattr(self.server,'sources'):
                self.server.sources=SourcesService(self.server.service)
            return self.server.sources
    def source_owner(self):
        # Native one-use proofs share the reader instance; browser tests remain
        # bound to precisely the session which submitted them. Never log headers.
        import hashlib
        session=self.headers.get('X-Nagi-Session')
        return hashlib.sha256(session.encode()).hexdigest() if session else self.server.owner_auth.instance
    def source_get(self,path):
        if not self.authenticate():return self.send(401,{'error':'owner_required'})
        if self.path!=path:return self.send(404,{'error':'not_found'})
        try:
            service=self.sources()
            if path==SOURCES:return self.send(200,service.read_sources())
            if path==SOURCES+'/glance':return self.send(200,service.glance(platform()))
            if path==SOURCES+'/catalog':return self.send(200,service.catalog())
            if path==SOURCES+'/notifications':return self.send(200,service.notifications())
            schema=SOURCE_SCHEMA.fullmatch(path)
            if schema:return self.send(200,service.schema(schema.group(1)))
            return self.send(405 if path in SOURCE_POST else 404,{'error':'method_not_allowed' if path in SOURCE_POST else 'not_found'})
        except SourceError as error:return self.send(error.status,{'error':error.code})
        except Exception:return self.send(503,{'error':'storage_unavailable'})
    def source_post(self,value):
        service=self.sources();action=self.path[len(SOURCES)+1:]
        if action in ('discover','test','connect'):
            return getattr(service,action)(value,self.source_owner())
        if action=='disconnect':return service.disconnect(value)
        if action.startswith('notifications/'):
            return service.notification_action(action.split('/')[1],value)
        raise SourceError('method_not_allowed',405)
    def do_GET(self):
        if not self.allowed():return self.send(403,{'error':'origin_denied' if self.path.startswith(SOURCES) else 'Local same-origin access only'})
        path=urlsplit(self.path).path
        if path==SOURCES or path.startswith(SOURCES+'/'):return self.source_get(path)
        if path in FILES:
            file=ROOT/'web'/FILES[path]
            # The glance shows project favicons from blob: URLs it made from owner-authenticated fetches.
            return self.send(200,file.read_bytes(),TYPES.get(file.suffix) or mimetypes.guess_type(file)[0] or 'application/octet-stream',glasswork=file.name=='glance-v2.html')
        icon=ICON_PATH.fullmatch(path)
        if self.path!=path or (path not in API and not icon):return self.send(404,{'error':'Not found'})
        if not self.authenticate():return self.send(401,{'error':'Owner authentication required'})
        service=self.server.service
        try:
            if path=='/api/health':return self.send(200,{'app':'nagi','schemaVersion':2})
            if path=='/api/settings':return self.send(200,service.settings_resource())
            if icon:
                found=self.sources().project_icon(icon.group(1)) if hasattr(self.server,'sources') else service.project_icon(icon.group(1))
                if not found:return self.send(404,{'error':'No project icon'})
                body,kind=found
                # Image bytes only: sniffed and typed upstream; an SVG is sandboxed, never a document.
                return self.send(200,body,kind,csp="default-src 'none'; style-src 'unsafe-inline'; sandbox")
            self.server.sources.poll_legacy() if hasattr(self.server,'sources') else service.poll()
            common={'version':2,'platform':platform(),'checkedAt':service.clock().isoformat()}
            if path=='/api/glance':return self.send(200,{**common,'agents':service.agents,'settings':service.settings(),'warnings':service.warnings()})
            if path=='/api/limits':return self.send(200,{**common,'providers':service.providers,'machine':service.machine})
            if path=='/api/notifications':return self.send(200,{'version':2,'checkedAt':common['checkedAt'],'events':service.notifications(),'warnings':service.warnings()})
            return self.send(405,{'error':'Method not allowed'})
        except (OSError,ValueError,TypeError,KeyError,RecursionError,SourceError):return self.send(503,{'error':'Local display state unavailable'})
    def do_POST(self):
        source_route=self.path.startswith(SOURCES)
        if not self.allowed(True):return self.send(403,{'error':'origin_denied' if source_route else 'Local same-origin JSON access only'})
        if not source_route and self.path not in AUTH|{'/api/settings','/api/notifications/claim','/api/notifications/reserve','/api/notifications/release'}:return self.send(404,{'error':'Not found'})
        try:
            if source_route and (self.headers.get_all('Transfer-Encoding',[]) or
                    any(len(self.headers.get_all(key,[]))!=1 for key in ('Content-Length','Content-Type','X-Progress-Desk'))):
                raise SourceError('invalid_request')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:return self.send(413,{'error':'request_too_large' if source_route else 'Request must be 1–4096 bytes'})
            raw=self.rfile.read(size)
            auth=self.server.owner_auth;auth.bind(self.server.server_port)
            public=self.path in ('/auth/challenge','/auth/redeem')
            if not public and not self.authenticate(raw):return self.send(401,{'error':'owner_required' if source_route else 'Owner authentication required'})
            value=strict_json_loads(raw,4096)
            if source_route:
                if self.path not in SOURCE_POST:
                    known=self.path in SOURCE_GET or SOURCE_SCHEMA.fullmatch(self.path)
                    return self.send(405 if known else 404,{'error':'method_not_allowed' if known else 'not_found'})
                return self.send(200,self.source_post(value))
            if self.path=='/auth/challenge':return self.send(200,auth.challenge(value))
            if self.path=='/auth/redeem':
                if not isinstance(value,dict) or set(value)!={'ticket','path'}:raise ValueError()
                session=auth.redeem(value['ticket'],value['path'])
                return self.send(200,session) if session else self.send(401,{'error':'Owner authentication required'})
            if self.path=='/auth/launch':
                if not self.headers.get('Authorization','').startswith('NagiProof '):return self.send(401,{'error':'Native owner proof required'})
                if not isinstance(value,dict) or set(value)!={'path'} or value['path'] not in ('/glance','/overview'):raise ValueError()
                token=auth.issue(value['path'])
                return self.send(200,{'url':f"http://127.0.0.1:{self.server.server_port}{value['path']}#nagi-launch={token}"})
            if self.path=='/api/settings':
                settings=self.server.service.save_settings(value)
                return self.send(200,self.server.service.settings_resource())
            service=self.server.service
            if self.path=='/api/notifications/reserve':
                if not isinstance(value,dict) or set(value)!={'id'}:raise ValueError()
                lease=service.reserve(value['id'])
                return self.send(200,{'version':2,'reserved':lease is not None,'lease':lease})
            if not isinstance(value,dict) or set(value)!={'id','reservation'}:raise ValueError()
            release=self.path=='/api/notifications/release'
            event=service.claim(value['id'],value['reservation'],release=release)
            return self.send(200,{'version':2,'released' if release else 'claimed':event is not None,'event':event})
        except SourceError as error:return self.send(error.status,{'error':error.code})
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return self.send(400,{'error':'invalid_request' if source_route else 'Invalid request'})
        except (OSError,RuntimeError):return self.send(503,{'error':'storage_unavailable' if source_route else 'Local state unavailable'})
        except Exception:
            if source_route:return self.send(503,{'error':'storage_unavailable'})
            raise
    def do_PUT(self):
        source_route=self.path.startswith(SOURCES)
        if not self.allowed():return self.send(403,{'error':'origin_denied' if source_route else 'Local same-origin access only'})
        if not self.authenticate():return self.send(401,{'error':'owner_required' if source_route else 'Owner authentication required'})
        return self.send(405,{'error':'method_not_allowed' if source_route else 'Method not allowed'})
    do_PATCH=do_DELETE=do_OPTIONS=do_PUT

def refresh_loop(service,stop):
    while not stop.is_set():
        try:service.poll()
        except Exception:pass # A malformed source or local file must never kill refresh.
        stop.wait(20)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=47831);parser.add_argument('--data-dir',type=Path)
    args=parser.parse_args();directory=data_directory(args.data_dir)
    auth=OwnerAuth(directory);service=AgentsService(directory);sources=SourcesService(service)
    with ThreadingHTTPServer(('127.0.0.1',args.port),Handler) as reader:
        reader.owner_auth=auth;reader.service=service;reader.sources=sources
        stop=threading.Event()
        worker=threading.Thread(target=refresh_loop,args=(sources,stop),daemon=True);worker.start()
        print(f'Nagi local reader: 127.0.0.1:{reader.server_port}',flush=True)
        try:reader.serve_forever()
        except KeyboardInterrupt:pass
        finally:stop.set();worker.join(timeout=5);sources.close(wait=False)

if __name__=='__main__':main()
