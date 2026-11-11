"""Local-only prototype. Explicit file allowlist; never serves state directories.
Production use requires separately approved TLS reverse proxy and credentials.
"""
import os,base64,hmac,json,pathlib,threading,time,hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from generation_runner import reader,sha
import sys,math
UI=pathlib.Path(__file__).parent/'private-ui'
ALLOWED={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
def handler(store,credential,expected_policy_sha256=None,max_age_seconds=7200):
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,status,body,typ='application/json',extra=None):
   self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Cache-Control','private, no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
   for k,v in (extra or{}).items():self.send_header(k,v)
   self.end_headers();self.wfile.write(body)
  def do_GET(self):
   allowed_hosts={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
   if self.headers.get('Host','')not in allowed_hosts:return self.reply(400,b'{"ok":false,"error":"Invalid host"}')
   expected='Basic '+base64.b64encode(credential.encode()).decode()if credential and':'in credential else None
   if not expected or not hmac.compare_digest(self.headers.get('Authorization','').encode('latin-1',errors='replace'),expected.encode('ascii')):return self.reply(401,b'{"ok":false,"error":"Authentication required"}',extra={'WWW-Authenticate':'Basic realm="Private jobs", charset="UTF-8"'})
   url=urlsplit(self.path)
   if url.query:return self.reply(400,b'{"ok":false,"error":"Query parameters are not supported"}')
   if url.path=='/api/jobs':
    try:
     with reader(store)as generation:
      if generation is None:return self.reply(503,b'{"ok":false,"error":"Feed not ready"}')
      manifest=json.loads((generation/'manifest.json').read_text(encoding='utf-8'))
      body=(generation/'display.json').read_bytes()
      if hashlib.sha256(body).hexdigest()!=manifest['files']['display.json']['sha256']:raise ValueError('Display integrity mismatch')
      data=json.loads(body)
      if not expected_policy_sha256 or manifest.get('policy_sha256')!=expected_policy_sha256:raise ValueError('Current approved policy mismatch')
      stamp=float(data['feed_as_of']);now=time.time()
      if not math.isfinite(stamp)or stamp>now+300:raise ValueError('Invalid future source timestamp')
      age=max(0,now-stamp);data['age_seconds']=int(age);data['stale']=age>max_age_seconds;data['max_age_seconds']=max_age_seconds;data['served_at']=now
      if data.get('policy_sha256')!=manifest.get('policy_sha256'):raise ValueError('Policy integrity mismatch')
      if data.get('schema_version')!=1 or not data.get('policy_available'):return self.reply(503,b'{"ok":false,"error":"Verified screening policy unavailable"}')
      return self.reply(200,json.dumps(data,ensure_ascii=True,allow_nan=False).encode())
    except Exception as e:
     print('Private feed error: '+type(e).__name__,file=sys.stderr)
     return self.reply(503,b'{"ok":false,"error":"Feed unavailable"}')
   if url.path not in ALLOWED:return self.reply(404,b'{"ok":false,"error":"Not found"}')
   p=UI/ALLOWED[url.path];typ='text/html; charset=utf-8'if p.suffix=='.html'else'text/css; charset=utf-8'if p.suffix=='.css'else'text/javascript; charset=utf-8'
   return self.reply(200,p.read_bytes(),typ)
  def do_POST(self):self.reply(405,b'{"ok":false,"error":"Read only"}')
 return Handler
if __name__=='__main__':
 from candidate_cli import check_runtime
 check_runtime()
 store=os.environ.get('JOB_STORE')
 if not store:raise SystemExit('JOB_STORE required')
 server=ThreadingHTTPServer(('127.0.0.1',8765),handler(store,os.environ.get('DASHBOARD_READ_CREDENTIAL',''),os.environ.get('APPROVED_POLICY_SHA256')));server.serve_forever()
