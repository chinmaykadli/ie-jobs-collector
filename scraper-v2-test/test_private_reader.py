import unittest,tempfile,threading,base64,json,pathlib,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
from private_reader import handler
from generation_runner import run
from test_sqlite_parity import S,payload
import ingest
class Reader(unittest.TestCase):
 def test_auth_allpaths_and_query_override_fail_closed(self):
  with tempfile.TemporaryDirectory()as d:
   run(d,[S],ingest.ingest,lambda _:payload([1]),policy={'verified':True,'blocked_companies':[]})
   s=ThreadingHTTPServer(('127.0.0.1',0),handler(d,'fixture:synthetic-only',__import__('screen_policy').validate({'verified':True,'blocked_companies':[]})['sha256']));t=threading.Thread(target=s.serve_forever,daemon=True);t.start();base='http://127.0.0.1:'+str(s.server_port)
   try:
    for path in ['/','/api/jobs','/state.json','/generations','/../state.sqlite']:
     with self.assertRaises(urllib.error.HTTPError)as cm:urllib.request.urlopen(base+path)
     self.assertEqual(cm.exception.code,401)
    for path,want in [('/',200),('/api/jobs',200),('/api/jobs?include=blocked',400),('/state.json',404),('/generations',404),('/%2e%2e/state.sqlite',404),('/.netlify/functions/heartbeat',404)]:
     req=urllib.request.Request(base+path,headers={'Authorization':'Basic '+base64.b64encode(b'fixture:synthetic-only').decode()})
     try:r=urllib.request.urlopen(req)
     except urllib.error.HTTPError as e:r=e
     self.assertEqual(r.code,want);self.assertIn('no-store',r.headers['Cache-Control'])
     if path=='/api/jobs':self.assertNotIn('block_reason',r.read().decode())
   finally:s.shutdown();s.server_close();t.join()
if __name__=='__main__':unittest.main()
